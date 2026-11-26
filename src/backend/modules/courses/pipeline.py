"""How a teacher's course is made (all AI work runs in the background; the API answers at once).

    plan      the course generator writes the lecture plan (roadmap) for the topic, the teacher's instructions and
              material → parsed into lectures → stage "plan_ready" (or straight on when `auto`, the request flow)
    approve   the teacher accepts (or edits) the plan → "building":
              1. notes: the generator writes the deep notes of every lecture from the plan (skipped for lectures
                 whose notes the teacher already wrote)
              2. material: the AI Professor's course builder turns each lecture into concepts, examples and a
                 checked question bank, and the lesson compiler writes the lecture flow (intro, explanation points
                 for the board, FAQ, true/false, match the terms, summary)
              3. one quiz draft per lecture (from the checked questions), waiting for the teacher's approval
              → "ready"
    rebuild   one lecture again (after the teacher changed its notes)
    stop      the teacher stops the AI while it works (see stop()): nothing new starts, results that arrive later are
              thrown away, and everything already saved stays ("Stop and keep what's made") — or the course is deleted

Everything is stored as soon as it is ready, so the teacher can open Lecture 1 while Lecture 4 is still being made.
`hooks` can be replaced in tests (no AI, no threads).
"""
from __future__ import annotations

import logging
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy import delete, select

from modules.courses import parse
from modules.courses.models import OWNER, CourseMaterial, CourseQuiz, TeacherCourse

log = logging.getLogger("neuralhub.courses")

PLAN_MATERIAL_CHARS = 12_000
NOTES_MATERIAL_CHARS = 30_000
QUIZ_SIZE = 8
NOTES_BATCH = 2  # lectures per notes-writing call (small batches written at the same time = a faster course)


def notes_workers() -> int:
    """How many notes-writing calls run at the same time (COURSE_NOTES_WORKERS, 1–8, default 4)."""
    import os

    try:
        return max(1, min(8, int(os.getenv("COURSE_NOTES_WORKERS", "4"))))
    except ValueError:
        return 4


def _default_generate(**kw):
    from modules.syllabus.generator import generate_ai_syllabus

    return generate_ai_syllabus(**kw)


def _default_gateway():
    from modules.professor.llm.gateway import gateway

    return gateway


def _default_session():
    from core import db as core_db

    return core_db.session_scope()


@dataclass
class Hooks:
    generate: Callable[..., dict] = _default_generate
    gateway: Callable[[], object] = _default_gateway
    session: Callable[[], object] = _default_session
    background: bool = True


hooks = Hooks()

class Stopped(Exception):
    """The teacher stopped the AI: the job ends quietly (the stop request already set the course's state)."""


@dataclass
class _Job:
    what: str                      # "plan" | "build" | "lecture 3"
    stop: threading.Event


_lock = threading.Lock()
_jobs: dict[str, _Job] = {}  # course id -> the job running for it
_notes_lock = threading.Lock()  # notes batches finish at the same time: one read-modify-write at a time


def running(course_id: str) -> str:
    with _lock:
        job = _jobs.get(course_id)
        return job.what if job else ""


def stop(course_id: str) -> str:
    """Stop the AI work for this course. Returns what was running ("" = nothing). The course is free at once
    (a new job may start); the old thread notices the stop at its next step and saves nothing more."""
    with _lock:
        job = _jobs.pop(course_id, None)
    if job is None:
        return ""
    job.stop.set()
    try:  # the course builder's slot too, so "Continue" can start a new build right away
        from modules.professor.content.builder import forget_build

        forget_build(OWNER, course_id)
    except Exception:  # noqa: BLE001
        log.exception("Course %s: could not free the builder slot", course_id)
    return job.what


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _start(course_id: str, what: str, fn: Callable[[threading.Event], None]) -> bool:
    """Run fn(stop) for this course unless something already runs for it. False = busy.
    fn checks `stop.is_set()` between its steps (or raises Stopped)."""
    job = _Job(what, threading.Event())
    with _lock:
        if course_id in _jobs:
            return False
        _jobs[course_id] = job

    def run():
        try:
            fn(job.stop)
        except Stopped:
            log.info("Course %s: %s stopped by the teacher", course_id, what)
        except Exception as e:  # noqa: BLE001 - the course shows "failed" with the reason; the teacher can retry
            if job.stop.is_set():
                log.info("Course %s: %s stopped (%s)", course_id, what, e)
                return
            log.exception("Course %s: %s failed", course_id, what)
            with hooks.session() as db:
                c = db.get(TeacherCourse, course_id)
                if c is not None:
                    c.stage, c.step, c.error = "failed", "Something went wrong", str(e)[:1500]
        finally:
            with _lock:
                if _jobs.get(course_id) is job:
                    _jobs.pop(course_id, None)

    if hooks.background:
        threading.Thread(target=run, name=f"course-{what}-{course_id}", daemon=True).start()
    else:
        run()
    return True


def _set(course_id: str, **values):
    with hooks.session() as db:
        c = db.get(TeacherCourse, course_id)
        for k, v in values.items():
            setattr(c, k, v)


# ------------------------------------------------------------------ what the AI is told

def context(db, c: TeacherCourse, budget: int) -> str:
    """The teacher's instructions, the student's request and the teacher's material, for the generator prompt."""
    parts = []
    if c.brief.strip():
        parts.append(f"THE TEACHER'S INSTRUCTIONS FOR THIS COURSE (follow them exactly):\n{c.brief.strip()[:2000]}")
    if c.request_user_id:
        from modules.courses import requests as rq

        req = rq.request_context(db, c.request_user_id, c.request_id)
        if req:
            parts.append("THIS COURSE IS FOR ONE STUDENT WHO ASKED FOR IT.\n" + req)
    mats = db.scalars(select(CourseMaterial).where(CourseMaterial.course_id == c.id).order_by(CourseMaterial.created_at)).all()
    if mats and c.source in ("files", "mixed"):
        left, chunks = budget, []
        for m in mats:
            if left <= 0:
                break
            take = m.text[: max(0, left)]
            chunks.append(f"--- {m.name} ---\n{take}")
            left -= len(take)
        rule = ("Use ONLY this material: every lecture, topic, fact and example must come from it. Do not add content "
                "that is not in it; if something is missing, keep the course to what the material covers."
                if c.source == "files" else
                "Build the course on this material first (its order, terms and examples); add standard textbook content "
                "only where the material is missing something.")
        parts.append(f"THE TEACHER'S OWN MATERIAL. {rule}\n" + "\n\n".join(chunks))
    return "\n\n".join(parts)


def _call(c: TeacherCourse, mode: str, extra: str, roadmap: str = "", days: Optional[int] = None,
          part: str = "full") -> str:
    from core import subject_catalog
    from modules.professor.content.builder import subject_id_for

    # the subject's own prompt (Accounting → the Accounting professor); "Other" → the general one
    name = "" if subject_catalog.subject_id(c.subject) == "general" and c.subject == subject_catalog.OTHER else c.subject
    res = hooks.generate(subject=c.topic, level=c.level, custom_topic=c.topic, mode=mode, approved_roadmap=roadmap,
                         subject_id=subject_id_for(c.subject), days=days or c.lectures, extra=extra,
                         subject_name=name, part=part)
    if not res or res.get("status") != "success" or not (res.get("syllabus") or "").strip():
        raise RuntimeError((res or {}).get("message") or "The AI could not write this part. Please try again.")
    return res["syllabus"]


def _generate(db, c: TeacherCourse, mode: str, roadmap: str = "") -> str:
    return _call(c, mode, context(db, c, PLAN_MATERIAL_CHARS if mode == "roadmap" else NOTES_MATERIAL_CHARS), roadmap)


def write_notes(db, c: TeacherCourse, lectures: list[int], with_guide: bool = True,
                stop: Optional[threading.Event] = None,
                on_batch: Optional[Callable[[dict], None]] = None) -> tuple[dict, str]:
    """Deep notes for these lectures, fast: NOTES_BATCH lectures per AI call (lecture sections only, with the course's
    own lecture numbers), all calls at the same time, plus — when `with_guide` — one more call for the course guide
    (introduction, wrap-up, videos, final exam) at the same time. A batch that fails is tried once more alone.
    `on_batch(notes)`: each batch's notes the moment they are written (saved at once: kept if the teacher stops).
    `stop`: once set, no new call starts and late answers are dropped."""
    halted = (lambda: stop.is_set()) if stop is not None else (lambda: False)
    from concurrent.futures import ThreadPoolExecutor

    extra = context(db, c, NOTES_MATERIAL_CHARS)
    by_no = {d["no"]: d for d in c.plan}
    wanted = [n for n in lectures if n in by_no]
    batches = [wanted[i:i + NOTES_BATCH] for i in range(0, len(wanted), NOTES_BATCH)]
    title = c.title or c.topic

    def one(batch):
        sub = [by_no[n] for n in batch]
        book = ""
        for attempt in (1, 2):  # one retry (a busy model); then these lectures stay without notes ("write again")
            if halted():
                return {}
            try:
                book = _call(c, "content", extra, parse.plan_markdown(title, sub), days=len(sub), part="lectures")
                break
            except Exception as e:  # noqa: BLE001
                log.warning("Course %s: notes for lectures %s failed (try %s): %s", c.id, batch, attempt, e)
        if not book or halted():
            return {}
        notes, _ = parse.split_notes(book)
        if not set(notes) & {str(n) for n in batch}:  # the writer numbered the days 1..k: map them in order
            notes = {str(n): v for n, v in zip(batch, notes.values())}
        # teachers see "Lecture n"
        out = {str(n): re.sub(r"^(#{2,3})\s*\**\s*Day\s*\d+", rf"\g<1> Lecture {n}", notes.get(str(n), ""), count=1, flags=re.M)
               for n in batch}
        out = {k: v for k, v in out.items() if v.strip()}
        if out and on_batch and not halted():
            on_batch(out)
        return out

    def guide_job():
        if halted():
            return ""
        try:
            book = _call(c, "content", extra, parse.plan_markdown(title, c.plan), days=len(c.plan), part="guide")
            # the guide has no "## Day" sections (split_notes would take it all as lecture 1)
            return parse.split_notes(book)[1] if re.search(r"^##\s*Day\s*\d", book, re.M) else book.strip()
        except Exception as e:  # noqa: BLE001 - the guide is extra; the lectures matter
            log.warning("Course %s: the course guide could not be written: %s", c.id, e)
            return ""

    with ThreadPoolExecutor(max_workers=1) as side, \
            ThreadPoolExecutor(max_workers=max(1, min(notes_workers(), len(batches)))) as ex:
        guide_f = side.submit(guide_job) if with_guide and batches else None  # its own thread, next to the lectures
        results = list(ex.map(one, batches))
        guide = guide_f.result() if guide_f else ""
    if halted():
        return {}, ""
    notes = {k: v for r in results for k, v in r.items() if v.strip()}
    return notes, guide


# ------------------------------------------------------------------ 1. plan

def make_plan(course_id: str) -> bool:
    return _start(course_id, "plan", lambda stop: _plan(course_id, stop))


def _plan(course_id: str, stop: threading.Event) -> None:
    """Write the lecture plan (inside a started job); with `auto` go straight on to the notes and material."""
    _set(course_id, stage="planning", step="Writing the lecture plan…", error="", progress={})
    with hooks.session() as db:
        c = db.get(TeacherCourse, course_id)
        text = _generate(db, c, "roadmap")
        if stop.is_set():
            raise Stopped()
        title, plan = parse.parse_plan(text)
        if not plan:
            raise RuntimeError("The AI's plan had no lectures. Please try again.")
        c.plan_md, c.plan = text, plan
        c.lectures = len(plan)
        if not c.title:
            c.title = title or c.topic
        c.stage, c.step = "plan_ready", "Plan ready: check it and approve"
        auto = c.auto
    if auto:
        _build(course_id, stop)


# ------------------------------------------------------------------ 1b. a course from the teacher's uploaded files

# the uploaded files whose text can be read (videos, audio and spreadsheets are only shown as they are)
READABLE_FILES = {"pdf", "docx", "pptx", "txt", "jpg", "png", "webp"}


def _material_id(file_id: str) -> str:
    return ("mf_" + file_id)[:40]


def readable_files(db, course_id: str) -> list:
    from modules.courses.files import files_of

    return [f for f in files_of(db, course_id) if f.kind in READABLE_FILES]


def name_from_material(mats) -> str:
    """The course topic for files the teacher did not name: a short title written by the AI from the start of the
    material; else the first heading of a file, else its file name (never empty)."""
    from modules.courses import sources

    text = "\n\n".join(m.text[:3000] for m in mats)[:6000]
    try:
        res = hooks.gateway().generate_text(
            "general",
            "Here is the start of a teacher's course material. Write the topic of the course as a short title "
            "(3 to 8 words, no quotes, no emoji, no words like 'Course' or 'Overview'). Answer with the title only.\n\n"
            + text, max_tokens=40, timeout_s=30)
        title = re.sub(r"[\"'*#`]|^title\s*:\s*", "", str(res.data or "").strip().splitlines()[0] if str(res.data or "").strip() else "", flags=re.I).strip()
        if 3 <= len(title) <= 120:
            return title
    except Exception as e:  # noqa: BLE001 - no AI right now: a heading or the file name
        log.info("naming the course from its files failed: %s", e)
    for m in mats:
        t = sources.suggest_topic(m.text, m.name)
        if t:
            return t
    return (mats[0].name.rsplit(".", 1)[0] if mats else "")[:120] or "My course"


def from_files(course_id: str) -> bool:
    """A course the teacher made with "Upload your material" (files shown as they are) becomes a full course:
    the text of the teacher's files is read (Word, PDF, PowerPoint, text, photos of notes), then — only from
    that material — the lecture plan with proper headings, the notes and course guide, live examples, quiz
    drafts and suggested YouTube videos are made, as for a "from your files" course. The teacher's files stay
    attached to their lectures (students can still download them). False = the AI is busy with this course."""

    def job(stop: threading.Event):
        from modules.courses import files as cf
        from modules.courses import sources

        _set(course_id, stage="planning", step="Reading your files…", error="", progress={})
        with hooks.session() as db:
            todo = [(f.id, f.filename or f.title or f"file.{f.kind}", f.kind, cf._path(course_id, f.stored_as))
                    for f in readable_files(db, course_id) if db.get(CourseMaterial, _material_id(f.id)) is None]
        for i, (fid, name, kind, path) in enumerate(todo, 1):
            if stop.is_set():
                raise Stopped()
            _set(course_id, step=f"Reading your files… ({i} of {len(todo)})")
            fname = name if name.lower().endswith("." + kind) else f"{name}.{kind}"
            try:
                k, text = sources.extract(fname, path.read_bytes())
            except Exception as e:  # noqa: BLE001 - one unreadable file does not stop the others
                log.warning("Course %s: could not read %s: %s", course_id, fname, e)
                continue
            with hooks.session() as db:
                db.add(CourseMaterial(id=_material_id(fid), course_id=course_id, name=name[:200], kind=k,
                                      size=path.stat().st_size, text=text, chars=len(text)))
        with hooks.session() as db:
            c = db.get(TeacherCourse, course_id)
            if not db.scalars(select(CourseMaterial.id).where(CourseMaterial.course_id == course_id)).first():
                raise RuntimeError("No text could be read from your files. Add a Word, PDF, PowerPoint or text file.")
            # from now on it is a "from your files" course: the AI uses only the teacher's material
            c.source, c.auto = "files", True
            c.notes, c.guide = {}, ""
            if not (c.topic or "").strip():  # the teacher did not name it: the AI names it from the files
                c.step = "Naming your course…"
                mats = db.scalars(select(CourseMaterial).where(CourseMaterial.course_id == course_id)
                                  .order_by(CourseMaterial.created_at)).all()
                c.topic = name_from_material(mats)
                c.title = c.title or c.topic
        _plan(course_id, stop)

    return _start(course_id, "plan", job)


# ------------------------------------------------------------------ 2. notes + material

def course_input(c: TeacherCourse, only: Optional[int] = None):
    from modules.professor.content.builder import CourseInput, DayInput, clean_topic

    days = []
    for d in c.plan or []:
        if only is not None and d["no"] != only:
            continue
        topics = [clean_topic(t) for t in d.get("topics") or [] if clean_topic(t)] or [clean_topic(d["title"])]
        days.append(DayInput(day=d["no"], title=d["title"], objective=d.get("objective", ""), topics=topics,
                             notes=(c.notes or {}).get(str(d["no"]), "")))
    return CourseInput(user_id=OWNER, study_set_id=c.id, topic=c.title or c.topic, subject=c.subject, level=c.level,
                       days=days)


def default_quizzes(db, course_id: str, lectures: Optional[list[int]] = None) -> None:
    """A quiz draft for every lecture that has none (or for `lectures`, replacing their drafts):
    checked questions, easy to hard, at most QUIZ_SIZE, not approved."""
    from modules.professor.models import Concept, QuestionItem

    concepts = db.scalars(select(Concept).where(Concept.user_id == OWNER, Concept.study_set_id == course_id)
                          .order_by(Concept.order_index)).all()
    by_day: dict = {}
    for k in concepts:
        by_day.setdefault(k.day, []).append(k.id)
    for day, ids in by_day.items():
        q = db.get(CourseQuiz, (course_id, day))
        if q is not None and (lectures is None or day not in lectures):
            continue
        qs = db.scalars(select(QuestionItem).where(QuestionItem.concept_id.in_(ids), QuestionItem.verified.is_(True))).all()
        order = {cid: i for i, cid in enumerate(ids)}
        # one question per topic first (easy ones), then the rest, so every topic is asked
        qs = sorted(qs, key=lambda x: (x.difficulty, order.get(x.concept_id, 0)))
        picked, seen = [], set()
        for x in qs:
            if x.concept_id not in seen:
                picked.append(x.id)
                seen.add(x.concept_id)
        for x in qs:
            if x.id not in picked:
                picked.append(x.id)
        if q is None:
            q = CourseQuiz(course_id=course_id, lecture=day)
            db.add(q)
        q.question_ids, q.approved = picked[:QUIZ_SIZE], False


def lectures_with_material(db, course_id: str) -> set[int]:
    from modules.professor.models import Concept

    return set(db.scalars(select(Concept.day).where(Concept.user_id == OWNER, Concept.study_set_id == course_id)
                          .distinct()).all())


def _build(course_id: str, stop: Optional[threading.Event] = None) -> None:
    """Notes for lectures without them, then the material for lectures without it (runs inside a started job).
    Each lecture's notes and material are saved the moment they are ready, so a stopped course keeps them and
    "Continue" only makes what is still missing."""
    from modules.courses import videos
    from modules.professor.content.builder import start_build

    stop = stop or threading.Event()
    # suggested YouTube videos for every lecture, found while the notes and material are written
    side = threading.Thread(target=videos.fill_course, args=(hooks.session, course_id, stop), daemon=True,
                            name=f"course-videos-{course_id}")
    side.start()
    try:
        _build_steps(course_id, stop, start_build)
    finally:
        side.join(timeout=60)


def _build_steps(course_id: str, stop: threading.Event, start_build) -> None:

    with hooks.session() as db:
        c = db.get(TeacherCourse, course_id)
        c.stage, c.error, c.plan_approved_at = "building", "", c.plan_approved_at or _now()
        missing = [d["no"] for d in c.plan if not (c.notes or {}).get(str(d["no"]), "").strip()]
        c.step = "Writing the lecture notes…" if missing and c.source != "manual" else "Preparing examples and quizzes…"
        c.progress = {"done": 0, "total": len(c.plan)}
    if missing and (c.source != "manual"):
        total = len(c.plan)

        def save_batch(batch: dict):  # each batch's notes are saved as soon as they are written
            with _notes_lock, hooks.session() as db2:
                cc = db2.get(TeacherCourse, course_id)
                if cc is None or stop.is_set():
                    return
                cc.notes = {**(cc.notes or {}), **batch}
                done = sum(1 for d in cc.plan if (cc.notes or {}).get(str(d["no"]), "").strip())
                cc.step, cc.progress = f"Writing the lecture notes… ({done} of {total})", {"done": done, "total": total}

        with hooks.session() as db:
            c = db.get(TeacherCourse, course_id)
            notes, guide = write_notes(db, c, missing, with_guide=not (c.guide or "").strip(), stop=stop,
                                       on_batch=save_batch)
            if stop.is_set():
                raise Stopped()
            if not notes:
                raise RuntimeError("The AI could not write the lecture notes. Please try again.")
            c.notes, c.guide = {**(c.notes or {}), **notes}, guide or c.guide
            c.step, c.progress = "Preparing examples and quizzes…", {"done": 0, "total": len(c.plan)}
    if stop.is_set():
        raise Stopped()
    with hooks.session() as db:
        c = db.get(TeacherCourse, course_id)
        course = course_input(c)
        have = lectures_with_material(db, course_id)
        todo = {d.day for d in course.days if d.day not in have} or {d.day for d in course.days}

    def finished(status: str):
        with hooks.session() as db:
            c = db.get(TeacherCourse, course_id)
            if c is None:
                return
            if stop.is_set():  # stopped: keep what is ready (with quiz drafts); the stop request set the stage
                default_quizzes(db, course_id)
                return
            if status == "done":
                default_quizzes(db, course_id)
                c.stage, c.step = "ready", "Ready"
                c.progress = {"done": len(c.plan), "total": len(c.plan)}
            else:
                c.stage, c.step = "failed", "Could not prepare the lectures"
                from modules.professor.content.builder import latest_build

                b = latest_build(db, OWNER, course_id)
                c.error = (b.error if b else "") or "The AI is not available right now. Please try again."

    start_build(hooks.session, hooks.gateway(), OWNER, course_id, background=False, course=course, on_finish=finished,
                should_stop=stop.is_set, only_days=todo)


def approve(course_id: str) -> bool:
    return _start(course_id, "build", lambda stop: _build(course_id, stop))


# ------------------------------------------------------------------ 3. one lecture again

def clear_lecture(db, course_id: str, lecture: int) -> None:
    from modules.professor.models import Concept, ExampleItem, LessonStep, QuestionItem

    ids = db.scalars(select(Concept.id).where(Concept.user_id == OWNER, Concept.study_set_id == course_id,
                                              Concept.day == lecture)).all()
    if ids:
        db.execute(delete(ExampleItem).where(ExampleItem.concept_id.in_(ids)))
        db.execute(delete(QuestionItem).where(QuestionItem.concept_id.in_(ids)))
        db.execute(delete(Concept).where(Concept.id.in_(ids)))
    db.execute(delete(LessonStep).where(LessonStep.user_id == OWNER, LessonStep.study_set_id == course_id,
                                        LessonStep.day == lecture))


def rebuild_lecture(course_id: str, lecture: int) -> bool:
    def job(stop: threading.Event):
        from modules.professor.content.builder import CourseBuilder, pack_for, save_concepts, subject_id_for
        from modules.professor.content.lessons import compile_day

        _set(course_id, step=f"Preparing lecture {lecture} again…", error="")
        with hooks.session() as db:
            c = db.get(TeacherCourse, course_id)
            course = course_input(c, only=lecture)
            if not course.days:
                raise RuntimeError("This lecture is not in the plan.")
            if not course.days[0].notes and c.source != "manual":
                notes, _ = write_notes(db, c, [lecture], with_guide=False)
                if notes.get(str(lecture)):
                    c.notes = {**(c.notes or {}), str(lecture): notes[str(lecture)]}
                    course.days[0].notes = notes[str(lecture)]
        gw = hooks.gateway()
        pack = pack_for(course.subject)
        build_id = f"build_{uuid.uuid4().hex[:16]}"
        concepts, _ = CourseBuilder(gw, should_stop=stop.is_set).build(course)
        if stop.is_set():  # stopped: the lecture keeps its old material
            raise Stopped()
        with hooks.session() as db:
            clear_lecture(db, course_id, lecture)
            # keep the course order: the lecture's topics go where the lecture is
            for i, k in enumerate(concepts):  # views order by (lecture, order_index)
                k.order_index = lecture * 1000 + i
            save_concepts(db, course, build_id, concepts, subject_id_for(course.subject))
        with hooks.session() as db:
            compile_day(db, gw, pack, course, course.days[0], concepts, course.days[0].notes, course.topic)
            default_quizzes(db, course_id, [lecture])
            c = db.get(TeacherCourse, course_id)
            c.step = "Ready" if c.stage == "ready" else c.step

    return _start(course_id, f"lecture {lecture}", job)
