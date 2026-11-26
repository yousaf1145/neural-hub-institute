"""Owl helps a student study a course they made themselves (their own syllabus): a short general explanation of a day,
a practice quiz Owl makes from that day's notes, marking of the answers, and questions about the lesson.

Owl gives the idea and a first understanding; the full course is taught by a live teacher (the student can send the
course to one). No certificate comes from these practice quizzes.

    POST /api/owl/lesson/explain              {lesson}                  → {reply}
    POST /api/owl/lesson/ask                  {lesson, question, history} → {reply}
    POST /api/owl/lesson/quiz                 {lesson}                  → {quiz: {id, questions (no answers)}}
    POST /api/owl/lesson/quiz/{id}/check      {userId, answers}         → {scorePct, results}
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from core import db as core_db
from core.db import Base
from modules.professor.models import JSONType

router = APIRouter(prefix="/lesson", tags=["Owl"])

QUESTIONS = 5          # 3 multiple choice + 2 short answers
NOTES_CHARS = 7000     # how much of the day's notes goes into a prompt


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OwlQuiz(Base):
    """A practice quiz Owl made from one day of the student's own course (answers stay on the server)."""
    __tablename__ = "owl_quizzes"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True, default="")
    course: Mapped[str] = mapped_column(String(300), default="")   # topic of the course
    lesson: Mapped[str] = mapped_column(String(300), default="")   # day title
    questions: Mapped[list] = mapped_column(JSONType, default=list)
    attempts: Mapped[list] = mapped_column(JSONType, default=list)  # [{at, scorePct}]
    best: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# the AI calls (tests replace these)
def _text(prompt: str, **kw) -> str:
    from core.llm import generate_text

    return generate_text(prompt, **kw)


def _json(prompt: str, **kw):
    from core.llm import generate_json

    return generate_json(prompt, **kw)


hooks: Dict[str, Any] = {"text": _text, "json": _json}


def _db():
    if not core_db.SessionLocal:
        raise HTTPException(status_code=503, detail="Database is not configured")
    return core_db.session_scope()


def _take(user_id: str, what: str):
    """The admin's daily AI limit for students (same counter as Ask AI)."""
    try:
        from modules.settings import store, usage

        limit = store.get("limits.aiQuestionsPerDay")
        allowed, _ = usage.take(user_id, "ai_question", limit)
        if not allowed:
            raise HTTPException(status_code=429, detail=f"You have used today's {limit} AI questions. They come back tomorrow.")
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - no limits configured
        pass


class LessonIn(BaseModel):
    userId: str = Field("", max_length=120)
    course: str = Field(..., min_length=1, max_length=300)      # the course topic
    subject: str = Field("", max_length=120)
    level: str = Field("New to this", max_length=80)
    title: str = Field(..., min_length=1, max_length=300)       # the day's title
    objective: str = Field("", max_length=600)
    topics: List[str] = Field(default_factory=list, max_length=30)
    notes: str = Field("", max_length=60000)
    language: str = Field("English", max_length=40)


def _clean_notes(md: str) -> str:
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md or "")          # pictures
    md = re.sub(r"<[^>]+>", " ", md)                             # html
    return re.sub(r"\n{3,}", "\n\n", md).strip()[:NOTES_CHARS]


def _context(x: LessonIn) -> str:
    topics = "; ".join(t.strip() for t in x.topics if t.strip())[:800]
    notes = _clean_notes(x.notes)
    return (f"Course: {x.course}\nSubject: {x.subject or 'not given'}\nStudent level: {x.level}\n"
            f"Today's lesson: {x.title}\nObjective: {x.objective or '-'}\nTopics: {topics or '-'}\n"
            f"Lesson notes (the student's own course):\n{notes or '(no notes saved for this day yet)'}")


def _language(x: LessonIn) -> str:
    lang = (x.language or "English").strip()
    return "Roman Urdu (Urdu in English letters)" if lang.lower() in ("urdu", "roman urdu") else lang


OWL = ("You are Owl, NeuralHub's friendly AI teaching assistant. The student made this course themselves and is "
       "reading it on their own. You give them the idea and a first understanding; the full course is taught by a live "
       "teacher on NeuralHub.")


@router.post("/explain")
def explain(body: LessonIn):
    """A short, general explanation of one day."""
    _take(body.userId, "explain")
    prompt = f"""{OWL}

{_context(body)}

Explain this lesson to the student in {_language(body)}.
- Markdown, short paragraphs, under about 350 words.
- Start with **What this lesson is about** (2-3 lines), then **Key ideas** (3-5 bullets in simple words), then
  **An everyday example** (one example from daily life in Pakistan if it fits), then **Check yourself**: 3 short
  questions WITHOUT answers.
- Stay inside this lesson; if the notes are empty, explain the title and topics in general.
- End with one line: for the full lesson with practice, the student can send this course to a teacher."""
    from core.errors import ai_errors

    with ai_errors():
        return {"reply": hooks["text"](prompt, max_tokens=1400, temperature=0.3)}


class AskIn(LessonIn):
    question: str = Field(..., min_length=1, max_length=2000)
    history: List[Dict[str, str]] = Field(default_factory=list, max_length=12)


@router.post("/ask")
def ask(body: AskIn):
    """A question about this lesson (answered with the lesson as context)."""
    _take(body.userId, "ask")
    turns = "\n".join(f"{'Student' if m.get('role') == 'student' else 'Owl'}: {str(m.get('content', ''))[:600]}"
                      for m in body.history[-6:])
    prompt = f"""{OWL}

{_context(body)}

Conversation so far:
{turns or '(new)'}

The student asks: {body.question}

Answer in {_language(body)} (if the student wrote in Urdu or Roman Urdu, use the same). Be clear and short (under about
250 words), use Markdown, use the lesson notes when they help, and if the question is outside this lesson answer
briefly and say it belongs to another lesson."""
    from core.errors import ai_errors

    with ai_errors():
        return {"reply": hooks["text"](prompt, max_tokens=1000, temperature=0.3)}


# ------------------------------------------------------------------ practice quiz

def _valid(q: dict) -> Optional[dict]:
    kind = q.get("type")
    text = str(q.get("question", "")).strip()
    if not text:
        return None
    if kind == "mcq":
        opts = [str(o).strip() for o in q.get("options") or [] if str(o).strip()]
        try:
            idx = int(q.get("answer_index"))
        except (TypeError, ValueError):
            return None
        if len(opts) < 3 or not 0 <= idx < len(opts):
            return None
        return {"type": "mcq", "question": text[:400], "options": opts[:5], "answer_index": idx,
                "explanation": str(q.get("explanation", ""))[:500]}
    if kind == "short":
        keys = [str(k).strip() for k in q.get("key_points") or [] if str(k).strip()]
        if not keys:
            return None
        return {"type": "short", "question": text[:400], "key_points": keys[:4],
                "model_answer": str(q.get("model_answer", ""))[:600], "explanation": str(q.get("explanation", ""))[:500]}
    return None


def public(q: dict) -> dict:
    out = {"id": q["id"], "type": q["type"], "question": q["question"]}
    if q["type"] == "mcq":
        out["options"] = q["options"]
    return out


@router.post("/quiz")
def make_quiz(body: LessonIn):
    _take(body.userId, "quiz")
    prompt = f"""{OWL}

{_context(body)}

Make a practice quiz of {QUESTIONS} questions on THIS lesson only, for a student at level "{body.level}", written in
{_language(body)}: 3 multiple choice and 2 short answer, easy to medium, each testing a different idea from the notes.
JSON: {{"questions": [
 {{"type": "mcq", "question": "...", "options": ["A", "B", "C", "D"], "answer_index": 0, "explanation": "why"}},
 {{"type": "short", "question": "...", "key_points": ["point the answer must contain", "..."], "model_answer": "...",
   "explanation": "..."}}
]}}"""
    from core.errors import ai_errors

    with ai_errors():
        data = hooks["json"](prompt, max_tokens=2500, temperature=0.4)
    raw = data.get("questions") if isinstance(data, dict) else data
    qs = [v for v in (_valid(q) for q in (raw or []) if isinstance(q, dict)) if v][:QUESTIONS]
    if len(qs) < 2:
        raise HTTPException(status_code=502, detail="Owl could not make a good quiz this time. Please try again.")
    for i, q in enumerate(qs):
        q["id"] = f"q{i + 1}"
    quiz = OwlQuiz(id=f"owq_{uuid.uuid4().hex[:16]}", user_id=body.userId, course=body.course[:300],
                   lesson=body.title[:300], questions=qs, attempts=[])
    with _db() as db:
        db.add(quiz)
    return {"quiz": {"id": quiz.id, "course": quiz.course, "lesson": quiz.lesson, "questions": [public(q) for q in qs]}}


class CheckIn(BaseModel):
    userId: str = Field("", max_length=120)
    answers: Dict[str, Any] = Field(default_factory=dict)


def _words(s: str) -> set:
    return {w for w in re.findall(r"[a-z]{3,}", (s or "").lower())}


def _fallback_short(q: dict, answer: str) -> dict:
    """No AI: count the key points whose main words appear in the answer."""
    have = _words(answer)
    hit = sum(1 for k in q["key_points"] if _words(k) and len(_words(k) & have) >= max(1, len(_words(k)) // 2))
    score = hit / len(q["key_points"])
    verdict = "correct" if score >= 0.75 else "partial" if score > 0 else "wrong"
    return {"verdict": verdict, "score": round(score, 2), "feedback": ""}


def _mark_short(items: list[tuple[dict, str]], language: str) -> dict:
    if not items:
        return {}
    todo = [{"id": q["id"], "question": q["question"], "key_points": q["key_points"], "model_answer": q["model_answer"],
             "student_answer": a[:1500]} for q, a in items if a.strip()]
    out = {q["id"]: {"verdict": "wrong", "score": 0.0, "feedback": ""} for q, a in items if not a.strip()}
    if not todo:
        return out
    prompt = f"""You are Owl, marking a student's short answers fairly, like a kind teacher. The student may write in
English, Urdu or Roman Urdu; judge the meaning, not spelling or grammar. For each answer decide how many key points it
covers. verdict: correct (all or nearly all), partial (some), wrong (none or incorrect). score 0..1.
feedback: one short helpful sentence in {language} saying what was right or missing.
Answers: {json.dumps(todo, ensure_ascii=False)}
JSON: {{"results": [{{"id": "q4", "verdict": "partial", "score": 0.5, "feedback": "..."}}]}}"""
    try:
        data = hooks["json"](prompt, max_tokens=1200, temperature=0.1)
        got = {r.get("id"): r for r in (data.get("results") or []) if isinstance(r, dict)}
    except Exception:  # noqa: BLE001 - the AI is down: mark by key words
        got = {}
    for q, a in items:
        if q["id"] in out:
            continue
        r = got.get(q["id"])
        if r and r.get("verdict") in ("correct", "partial", "wrong"):
            try:
                score = max(0.0, min(1.0, float(r.get("score", 0))))
            except (TypeError, ValueError):
                score = {"correct": 1.0, "partial": 0.5, "wrong": 0.0}[r["verdict"]]
            out[q["id"]] = {"verdict": r["verdict"], "score": score, "feedback": str(r.get("feedback", ""))[:300]}
        else:
            out[q["id"]] = _fallback_short(q, a)
    return out


@router.post("/quiz/{quiz_id}/check")
def check(quiz_id: str, body: CheckIn):
    with _db() as db:
        quiz = db.get(OwlQuiz, quiz_id)
        if quiz is None or (quiz.user_id and body.userId and quiz.user_id != body.userId):
            raise HTTPException(status_code=404, detail="Quiz not found")
        qs = list(quiz.questions or [])
    shorts = [(q, str(body.answers.get(q["id"], "") or "")) for q in qs if q["type"] == "short"]
    marked = _mark_short(shorts, "English")
    results, total = [], 0.0
    for q in qs:
        a = body.answers.get(q["id"])
        if q["type"] == "mcq":
            try:
                chosen = int(a) if a is not None and a != "" else None
            except (TypeError, ValueError):
                chosen = None
            ok = chosen == q["answer_index"]
            r = {"verdict": "correct" if ok else "wrong", "score": 1.0 if ok else 0.0, "feedback": "",
                 "your": q["options"][chosen] if chosen is not None and 0 <= chosen < len(q["options"]) else None,
                 "correct": q["options"][q["answer_index"]]}
        else:
            r = {**marked[q["id"]], "your": str(a or "") or None, "correct": q["model_answer"] or "; ".join(q["key_points"])}
        total += r["score"]
        results.append({"id": q["id"], "type": q["type"], "question": q["question"], **r, "explanation": q.get("explanation", "")})
    pct = round(total / len(qs) * 100, 1) if qs else 0.0
    with _db() as db:
        quiz = db.get(OwlQuiz, quiz_id)
        quiz.attempts = [*(quiz.attempts or []), {"at": _now().isoformat(), "scorePct": pct}]
        quiz.best = max(quiz.best or 0, pct)
    return {"scorePct": pct, "results": results}
