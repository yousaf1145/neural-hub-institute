"""The evidence behind a certificate request, worked out on the server from what really happened.

video course:  every video watched (really played, not skipped) to WATCH_PCT %
live course:   classes with one tutor for one course (the student's study plan, or the request topic);
               attendance >= ATTENDANCE_PCT % of the classes held, and the course finished
               (every lecture of the teacher's course marked done, or no syllabus: at least MIN_CLASSES classes)

Each builder returns a plain dict (saved with the request as its report) with "eligible", "missing" (what is left,
in words) and the numbers the tutor / admin see. flags() lists things a reviewer should look at (never blocks).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select

from core import public_ids
from modules.portal import models as pm


def watch_pct() -> int:
    return int(os.getenv("CERT_VIDEO_WATCH_PCT", "90"))


def attendance_pct() -> int:
    return int(os.getenv("CERT_LIVE_ATTENDANCE_PCT", "70"))


def min_classes() -> int:
    return int(os.getenv("CERT_TUTOR_MIN_CLASSES", "3"))


WATCH_SLACK_S = 10  # the last save can be a few seconds before the real end


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: Optional[datetime]) -> Optional[datetime]:
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def _iso(d: Optional[datetime]) -> Optional[str]:
    d = _aware(d)
    return d.isoformat() if d else None


def student_card(db, user_id: str) -> dict:
    u = db.get(pm.User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Student not found")
    profile = u.profile or {}
    return {"id": u.id, "publicId": public_ids.ensure(db, u, "student"), "name": u.name or profile.get("name") or "Student",
            "email": u.email or profile.get("email", ""), "level": profile.get("level", ""), "joinedAt": _iso(u.created_at)}


def tutor_card(db, tutor_id: str) -> dict:
    from modules.tutor.models import Tutor

    t = db.get(Tutor, tutor_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    return {"id": t.id, "publicId": public_ids.ensure(db, t, "tutor"), "name": t.name, "email": t.email,
            "subject": t.subject, "verified": bool(t.verified), "rating": round(t.rating or 0, 1)}


# ---------------------------------------------------------------- video course

def video(db, user_id: str, course_id: str) -> dict:
    from modules.lectures import courses as vc
    from modules.lectures.models import Lecture, LectureProgress, VideoCourse
    from modules.payments.models import Purchase

    c = db.get(VideoCourse, course_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Course not found")
    is_open = vc.course_open(db, c, user_id)
    need = watch_pct()
    videos, seconds, watched_total, starts, lasts = [], 0.0, 0.0, [], []
    for it in vc._items(db, c.id):
        lec = db.get(Lecture, it.lecture_id)
        if lec is None:
            continue
        p = db.get(LectureProgress, (lec.id, user_id))
        dur = float(lec.duration_s or 0)
        watched = float(p.watched_s or 0) if p else 0.0
        furthest = float(p.furthest_s or 0) if p else 0.0
        done = bool(p and p.completed) and (dur <= 0 or watched + WATCH_SLACK_S >= dur * need / 100)
        seconds += dur
        watched_total += min(watched, dur) if dur else watched
        if p:
            starts.append(_aware(p.started_at))
            lasts.append(_aware(p.updated_at))
        videos.append({"id": lec.id, "title": lec.title, "duration": round(dur),
                       "watched": round(watched), "watchedPct": round(min(100, 100 * watched / dur)) if dur else 0,
                       "furthestPct": round(min(100, 100 * furthest / dur)) if dur else 0,
                       "completed": bool(p and p.completed), "done": done,
                       "startedAt": _iso(p.started_at) if p else None, "lastWatchedAt": _iso(p.updated_at) if p else None})
    buy = db.scalars(select(Purchase).where(Purchase.user_id == user_id, Purchase.kind == "course", Purchase.item_id == c.id,
                                            Purchase.status == "paid").order_by(Purchase.created_at)).first()
    left = [v["title"] for v in videos if not v["done"]]
    missing = []
    if not is_open:
        missing.append("Buy the course first.")
    if not videos:
        missing.append("This course has no videos yet.")
    if left:
        missing.append(f"Watch {len(left)} more {'video' if len(left) == 1 else 'videos'} to the end: " + ", ".join(left[:4])
                       + (" …" if len(left) > 4 else ""))
    return {
        "kind": "video", "rule": {"watchPct": need},
        "course": {"id": c.id, "title": c.title, "level": c.level, "subject": c.subject, "videos": len(videos),
                   "seconds": round(seconds), "price": c.price or 0, "currency": c.currency, "status": c.status},
        "tutor": tutor_card(db, c.tutor_id), "student": student_card(db, user_id),
        "access": {"open": is_open, "free": (c.price or 0) <= 0,
                   "purchase": {"at": _iso(buy.created_at), "amount": buy.amount, "currency": buy.currency,
                                "method": buy.method} if buy else None},
        "videos": videos, "done": sum(1 for v in videos if v["done"]), "total": len(videos),
        "watchedSeconds": round(watched_total), "courseSeconds": round(seconds),
        "progressPct": round(100 * sum(1 for v in videos if v["done"]) / len(videos)) if videos else 0,
        "startedAt": _iso(min(starts)) if starts else None, "lastActivityAt": _iso(max(lasts)) if lasts else None,
        "eligible": not missing, "missing": missing, "at": _iso(_now()),
    }


# ---------------------------------------------------------------- live classes with a tutor

def _topic(r: pm.TutorRequest) -> str:
    d = r.data or {}
    return str(d.get("studySetTopic") or d.get("topic") or "Course").strip()[:300] or "Course"


def course_key(r: pm.TutorRequest) -> str:
    """One course = the student's study plan sent to the tutor, or (no plan) the request topic."""
    return f"set:{r.study_set_id}" if r.study_set_id else "topic:" + _topic(r).lower()[:150]


def live_courses(db, user_id: str, tutor_id: Optional[str] = None) -> list[dict]:
    """The student's live courses: accepted requests grouped by (tutor, course)."""
    q = select(pm.TutorRequest).where(pm.TutorRequest.user_id == user_id, pm.TutorRequest.status == "accepted")
    if tutor_id:
        q = q.where(pm.TutorRequest.tutor_id == tutor_id)
    out: dict = {}
    for r in db.scalars(q.order_by(pm.TutorRequest.pos)).all():
        if not r.tutor_id:
            continue
        k = (r.tutor_id, course_key(r))
        if k not in out:
            s = db.get(pm.StudySet, (user_id, r.study_set_id)) if r.study_set_id else None
            out[k] = {"tutorId": r.tutor_id, "key": k[1], "title": (s.topic if s else "") or _topic(r), "requests": []}
        out[k]["requests"].append(r.id)
    return list(out.values())


def _requests_of(db, user_id: str, tutor_id: str, key: str) -> list[pm.TutorRequest]:
    rows = db.scalars(select(pm.TutorRequest).where(pm.TutorRequest.user_id == user_id, pm.TutorRequest.tutor_id == tutor_id,
                                                    pm.TutorRequest.status == "accepted")).all()
    return [r for r in rows if course_key(r) == key]


def _class(db, s: pm.LiveSession, user_id: str, now: datetime) -> dict:
    from modules.meet.models import MeetingAttendance, MeetingRoom
    from modules.tutor.models import SessionOutcome, SessionSummary

    dur = s.duration_min or 60
    start = _aware(s.starts_at)
    end = start + timedelta(minutes=dur) if start else None
    out = {"id": s.id, "topic": (s.data or {}).get("topic", ""), "startsAt": _iso(start), "durationMin": dur,
           "status": "cancelled", "minutes": None, "outcome": None, "notes": "", "summary": "", "joins": 0}
    if s.status in ("cancelled", "missed"):
        return out
    oc = db.get(SessionOutcome, (user_id, s.id))
    sm = db.get(SessionSummary, (user_id, s.id))
    rooms = db.scalars(select(MeetingRoom).where(MeetingRoom.session_id == s.id, MeetingRoom.user_id == user_id)).all()
    joins = db.scalars(select(MeetingAttendance).where(MeetingAttendance.room.in_([r.room for r in rooms]),
                                                       MeetingAttendance.role == "student",
                                                       MeetingAttendance.person_id == user_id)
                       .order_by(MeetingAttendance.joined_at)).all() if rooms else []
    minutes = None
    if joins and start:
        ended = min([x for x in (_aware(r.ended_at) for r in rooms) if x] + [end])
        spans = []
        for j in joins:  # merge overlapping joins (a rejoin after a drop)
            a = max(_aware(j.joined_at), start - timedelta(minutes=10))
            b = min(_aware(j.left_at) or ended, end)
            if b > a:
                spans.append((a, b))
        spans.sort()
        total, cur = 0.0, None
        for a, b in spans:
            if cur and a <= cur[1]:
                cur = (cur[0], max(cur[1], b))
            else:
                if cur:
                    total += (cur[1] - cur[0]).total_seconds()
                cur = (a, b)
        if cur:
            total += (cur[1] - cur[0]).total_seconds()
        minutes = min(dur, round(total / 60))
    attended = bool(joins) or (oc is not None and oc.outcome == "completed")
    if attended:
        status = "attended"
    elif (oc is not None and oc.outcome == "no_show") or (end and end <= now):
        status = "missed"
    else:
        status = "upcoming"
    out.update(status=status, minutes=minutes, outcome=oc.outcome if oc else None, notes=(oc.notes if oc else "")[:600],
               summary=(sm.summary if sm else "")[:600], joins=len(joins))
    return out


def _syllabus(db, user_id: str, reqs: list[pm.TutorRequest]) -> Optional[dict]:
    """The teacher's course(s) made for these requests: lectures marked done and lecture quizzes."""
    try:
        from modules.courses.models import CourseEnrollment, CourseQuizAttempt
        from modules.courses.requests import course_for
    except Exception:  # noqa: BLE001
        return None
    courses = []

    def candidates():
        found = [course_for(db, user_id, r.id) for r in reqs]
        found = [c for c in found if c is not None]
        if found or not reqs:
            return found
        # no course made for these requests: the teacher's course the student studies with this tutor
        # (e.g. a course the tutor shared), same topic first, else the only one
        from modules.courses.models import TeacherCourse

        mine = db.scalars(select(TeacherCourse).join(CourseEnrollment, CourseEnrollment.course_id == TeacherCourse.id).where(
            CourseEnrollment.user_id == user_id, TeacherCourse.tutor_id == reqs[0].tutor_id,
            TeacherCourse.archived.is_(False))).all()
        topics = {_topic(r).strip().lower() for r in reqs}
        same = [c for c in mine if (c.title or "").strip().lower() in topics or (c.topic or "").strip().lower() in topics]
        return same or (mine if len(mine) == 1 else [])

    try:
        with db.begin_nested():
            found = candidates()
    except Exception:  # noqa: BLE001 - courses tables missing (old database / tests)
        found = []
    for c in found:
        try:
            with db.begin_nested():
                if any(x["id"] == c.id for x in courses):
                    continue
                total = len(c.plan or []) or int(c.lectures or 0)
                e = db.get(CourseEnrollment, (c.id, user_id))
                done = len({int(x) for x in (e.lectures_done if e else []) if str(x).isdigit()})
                quizzes: dict = {}
                for a in db.scalars(select(CourseQuizAttempt).where(CourseQuizAttempt.course_id == c.id,
                                                                    CourseQuizAttempt.user_id == user_id)).all():
                    q = quizzes.setdefault(a.lecture, {"lecture": a.lecture, "attempts": 0, "best": 0.0, "passed": False})
                    q["attempts"] += 1
                    q["best"] = max(q["best"], round(a.score_pct or 0))
                    q["passed"] = q["passed"] or bool(a.passed)
                # quizzes the tutor sent from a live class: each must be taken and passed
                sent = sorted({int(x) for x in (e.quizzes_open if e else []) if str(x).isdigit()})
                for no in sent:
                    quizzes.setdefault(no, {"lecture": no, "attempts": 0, "best": 0.0, "passed": False})
                    quizzes[no]["sent"] = True
                courses.append({"id": c.id, "title": c.title or c.topic, "done": min(done, total) if total else done,
                                "total": total, "quizzes": sorted(quizzes.values(), key=lambda x: x["lecture"])})
        except Exception:  # noqa: BLE001 - courses tables missing (old database / tests)
            continue
    if not courses:
        return None
    done, total = sum(c["done"] for c in courses), sum(c["total"] for c in courses)
    sent = [q for c in courses for q in c["quizzes"] if q.get("sent")]
    passed = [q for q in sent if q["passed"]]
    taken = [q for q in sent if q["attempts"]]
    steps, steps_done = total + len(sent), done + len(passed)
    return {"courses": courses, "lecturesDone": done, "lecturesTotal": total,
            "quizzesSent": len(sent), "quizzesPassed": len(passed), "quizzesTaken": len(taken),
            "quizAvg": round(sum(q["best"] for q in taken) / len(taken)) if taken else None,
            "quizzesLeft": [q["lecture"] for q in sent if not q["passed"]],
            # progress = lectures done + class quizzes passed
            "pct": round(100 * steps_done / steps) if steps else 0}


def live(db, user_id: str, tutor_id: str, key: str) -> dict:
    reqs = _requests_of(db, user_id, tutor_id, key)
    if not reqs:
        raise HTTPException(status_code=404, detail="No accepted course with this tutor.")
    req_ids = {r.id for r in reqs}
    set_id = key[4:] if key.startswith("set:") else ""
    now = _now()
    rows = db.scalars(select(pm.LiveSession).where(pm.LiveSession.user_id == user_id, pm.LiveSession.tutor_id == tutor_id)
                      .order_by(pm.LiveSession.starts_at)).all()
    rows = [s for s in rows if (s.data or {}).get("requestId") in req_ids
            or (set_id and s.study_set_id == set_id and not (s.data or {}).get("requestId"))]
    classes = [_class(db, s, user_id, now) for s in rows]
    n = {k: sum(1 for c in classes if c["status"] == k) for k in ("attended", "missed", "cancelled", "upcoming")}
    held = n["attended"] + n["missed"]
    pct = round(100 * n["attended"] / held) if held else 0
    minutes = sum((c["minutes"] if c["minutes"] is not None else c["durationMin"]) for c in classes if c["status"] == "attended")
    syl = _syllabus(db, user_id, reqs)
    s = db.get(pm.StudySet, (user_id, set_id)) if set_id else None
    title = (s.topic if s else "") or _topic(reqs[0])
    need = attendance_pct()
    # the rule: the teacher finishes every lecture with the student + every class quiz is passed (no attendance %)
    if syl and syl["lecturesTotal"]:
        finished = syl["lecturesDone"] >= syl["lecturesTotal"]
        left_text = f"Your teacher has marked {syl['lecturesDone']} of {syl['lecturesTotal']} lectures done."
    else:
        finished = n["attended"] >= min_classes() and n["upcoming"] == 0
        left_text = (f"Attend at least {min_classes()} classes (now {n['attended']})." if n["attended"] < min_classes()
                     else "Finish your booked classes first.")
    missing = []
    if not finished:
        missing.append(left_text)
    if syl and syl.get("quizzesLeft"):
        left = syl["quizzesLeft"]
        missing.append(f"Pass your class quizzes: {syl['quizzesPassed']} of {syl['quizzesSent']} passed "
                       f"(lecture {', '.join(str(x) for x in left)} still to pass, in Quizzes).")
    dates = [c["startsAt"] for c in classes if c["status"] in ("attended", "missed") and c["startsAt"]]
    return {
        "kind": "live", "rule": {"attendancePct": need, "minClasses": min_classes()},
        "course": {"key": key, "title": title, "studySetId": set_id, "requests": sorted(req_ids)},
        "tutor": tutor_card(db, tutor_id), "student": student_card(db, user_id),
        "classes": classes, "counts": {**n, "booked": len(classes), "held": held}, "attendancePct": pct,
        "hours": round(minutes / 60, 1), "syllabus": syl, "courseFinished": finished,
        "progressPct": syl["pct"] if syl and syl["lecturesTotal"] else min(100, round(100 * n["attended"] / max(min_classes(), 1))),
        "quizAvg": syl.get("quizAvg") if syl else None,
        "startedAt": min(dates) if dates else None, "lastClassAt": max(dates) if dates else None,
        "eligible": not missing, "missing": missing, "at": _iso(now),
    }


# ---------------------------------------------------------------- things to look at

def flags(ev: dict) -> list[dict]:
    out = []
    if ev.get("kind") == "video":
        secs = ev.get("courseSeconds") or 0
        a, b = ev.get("startedAt"), ev.get("lastActivityAt")
        if secs >= 1800 and a and b:
            span = (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
            if span < secs * 0.5:
                out.append({"code": "fast", "text": f"Finished a {round(secs / 3600, 1)} h course in {max(1, round(span / 60))} minutes."})
        skipped = [v["title"] for v in ev.get("videos", []) if v["completed"] and not v["done"]]
        if skipped:
            out.append({"code": "skipped", "text": f"{len(skipped)} video(s) reached the end by skipping ahead."})
    else:
        att = [c for c in ev.get("classes", []) if c["status"] == "attended"]
        short = [c for c in att if c["minutes"] is not None and c["minutes"] < c["durationMin"] / 2]
        if short:
            out.append({"code": "short", "text": f"Stayed less than half the class in {len(short)} class(es)."})
        marked = [c for c in att if not c["joins"]]
        if att and len(marked) == len(att):
            out.append({"code": "no_join", "text": "No join record: attendance comes only from the tutor's marks."})
        missed = (ev.get("counts") or {}).get("missed", 0)
        if missed >= 2:
            out.append({"code": "missed", "text": f"Missed {missed} classes."})
    return out
