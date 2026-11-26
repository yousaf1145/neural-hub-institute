"""Tutor portal Phase 2: the AI teaching assistant.

Every AI output is a DRAFT for the tutor (brief, lesson plan, summary, feedback, practice);
nothing reaches a student until the tutor approves it.
Uses the same Gemini -> Groq -> Ollama chain as the rest of NeuralHub (core/llm.py).
When the AI is unavailable, the brief, risk and fit features fall back to clear rule-based results.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from core.errors import ai_errors
from core.llm import generate_json
from core.db import session_scope
from modules.assessments.router import (
    CasePart,
    CaseRequest,
    PromptRequest,
    QuizRequest,
    ShortGradeRequest,
    _case_prompt,
    generate_quiz,
    grade_case,
    grade_short,
)
from modules.portal import models as pm

from . import models as m
from .router import (
    WEAK,
    _availability,
    _course,
    _get_tutor,
    _iso,
    _notify_student,
    _now,
    _require_db,
    _require_link,
    _student_brief,
    _topic_strengths,
    tutor_requests,
    tutor_sessions,
    tutor_students,
)

ai_router = APIRouter(tags=["Tutor AI assistant"])


# ------------------------------------------------------------------ helpers

def _cache_get(db, key: str, max_age: Optional[timedelta] = None) -> Optional[dict]:
    row = db.get(m.AiCache, key)
    if not row:
        return None
    if max_age and row.created_at and _now() - row.created_at > max_age:
        return None
    return row.content


def _cache_put(db, key: str, tutor_id: str, kind: str, content: dict):
    """Upsert, so two requests generating the same item at once don't clash."""
    from sqlalchemy.dialects.postgresql import insert

    stmt = insert(m.AiCache).values(key=key, tutor_id=tutor_id, kind=kind, content=content, created_at=_now())
    db.execute(stmt.on_conflict_do_update(index_elements=[m.AiCache.key],
                                          set_={"content": stmt.excluded.content, "created_at": stmt.excluded.created_at}))


def _try_ai(prompt: str, max_tokens: int = 1500) -> Optional[dict]:
    """AI JSON or None (used where a rule-based fallback exists)."""
    try:
        data = generate_json(prompt, max_tokens=max_tokens)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _strs(value, limit: int = 8) -> List[str]:
    return [str(x).strip() for x in (value or []) if str(x).strip()][:limit] if isinstance(value, list) else []


def signals(db, tutor_id: str, user_id: str) -> dict:
    """Facts behind the risk level: score trend, inactivity, no-shows, overdue practice."""
    scores = [a.score_pct for a in db.scalars(select(pm.QuizAttempt).where(pm.QuizAttempt.user_id == user_id).order_by(pm.QuizAttempt.completed_at))]
    trend = 0.0
    if len(scores) >= 3:
        recent, earlier = scores[-2:], scores[:-2]
        trend = round(sum(recent) / len(recent) - sum(earlier) / len(earlier), 1)
    no_shows = db.scalar(select(func.count()).select_from(m.SessionOutcome).where(
        m.SessionOutcome.user_id == user_id, m.SessionOutcome.tutor_id == tutor_id, m.SessionOutcome.outcome == "no_show")) or 0
    overdue = db.scalar(select(func.count()).select_from(m.AssignedPractice).where(
        m.AssignedPractice.user_id == user_id, m.AssignedPractice.tutor_id == tutor_id,
        m.AssignedPractice.status == "assigned", m.AssignedPractice.due_at < _now())) or 0
    return {"scores": scores[-8:], "trend": trend, "noShows": no_shows, "overduePractice": overdue}


# ------------------------------------------------------------------ 1. daily brief

@ai_router.get("/api/tutor/{tutor_id}/ai/daily-brief")
def daily_brief(tutor_id: str, refresh: bool = False):
    _require_db()
    key = f"brief:{tutor_id}:{date.today().isoformat()}"
    with session_scope() as db:
        t = _get_tutor(db, tutor_id)
        if not refresh and (cached := _cache_get(db, key, timedelta(hours=6))):
            return cached
    reqs = [r for r in tutor_requests(tutor_id)["requests"] if r["status"] == "pending"]
    students = tutor_students(tutor_id)["students"]
    now = _now()
    today = [s for s in tutor_sessions(tutor_id)["sessions"]
             if s["status"] == "scheduled" and s["startsAt"] and now <= datetime.fromisoformat(s["startsAt"]) <= now + timedelta(hours=24)]
    weak_counter: dict = {}
    with session_scope() as db:
        for s in students:
            for ts in _topic_strengths(db, s["userId"]):
                if ts["pct"] < WEAK:
                    weak_counter.setdefault(ts["topic"], []).append(s["name"])
    common_weak = sorted(weak_counter.items(), key=lambda kv: -len(kv[1]))[:5]
    at_risk = [s for s in students if s["risk"]["level"] != "low"]

    # Rule-based priorities (always available, and the AI's raw material)
    priorities = []
    for s in today:
        priorities.append({"title": f"Session with {s['studentName']}", "detail": f"{s['topic']} · starts {s['startsAt']}", "action": "schedule", "urgency": "high"})
    for r in reqs[:3]:
        priorities.append({"title": f"Reply to {r['student']['name']}", "detail": f"New request for {r['studySetTopic']}", "action": "requests", "urgency": "medium"})
    for s in at_risk[:3]:
        priorities.append({"title": f"Check in with {s['name']}", "detail": ", ".join(s["risk"]["reasons"]), "action": f"student:{s['userId']}", "urgency": "medium"})

    # Short factual lines for the brief card (the AI never invents these)
    risk_lines = [f"{s['name']} needs a check-in: {', '.join(s['risk']['reasons'])}" for s in at_risk[:3]]
    for r in reqs[:3]:
        waited = ""
        try:
            days = (now - datetime.fromisoformat(r["sentAt"])).days if r.get("sentAt") else 0
            waited = f" ({days} day{'s' if days != 1 else ''})" if days >= 1 else ""
        except (TypeError, ValueError):
            pass
        risk_lines.append(f"{r['student']['name']}'s {r['studySetTopic'] or 'study'} request is waiting for your reply{waited}")
    good_lines = []
    with session_scope() as db:
        ids = [s["userId"] for s in students]
        if ids:
            best = db.scalars(select(pm.QuizAttempt).where(pm.QuizAttempt.user_id.in_(ids), pm.QuizAttempt.completed_at >= now - timedelta(days=7))
                              .order_by(pm.QuizAttempt.score_pct.desc()).limit(1)).first()
            if best and best.score_pct >= 80:
                who = next((s["name"] for s in students if s["userId"] == best.user_id), "A student")
                topic = (best.data or {}).get("lessonTitle", "")
                good_lines.append(f"{who} scored {round(best.score_pct)}%" + (f" on {topic}" if topic else "") + " this week.")
        t2 = db.get(m.Tutor, tutor_id)
        if t2 and t2.review_count and t2.rating >= 4:
            good_lines.append(f"Your rating is {t2.rating:.1f} from {t2.review_count} review{'s' if t2.review_count != 1 else ''}.")
    calm = [s for s in students if s["risk"]["level"] == "low"]
    if students and len(calm) == len(students):
        good_lines.append(f"All {len(students)} of your students are on track.")

    facts = {
        "tutor": t.name, "subject": t.subject, "sessions_next_24h": len(today), "pending_requests": len(reqs),
        "at_risk_students": [{"name": s["name"], "reasons": s["risk"]["reasons"]} for s in at_risk[:5]],
        "common_weak_topics": [{"topic": k, "students": v[:5]} for k, v in common_weak],
        "active_students": len(students),
    }
    ai = _try_ai(f"""You are an assistant for a private tutor on NeuralHub. Write today's short brief from these facts:
{facts}
Return JSON: {{"headline": "one sentence, max 14 words", "summary": "2-3 friendly sentences: what matters most today and why",
"teaching_tip": "one practical tip for today based on the weak topics (or general if none)"}}
Use only the facts given; do not invent students or numbers.""", max_tokens=600)
    brief = {
        "headline": (ai or {}).get("headline") or (f"{len(priorities)} things need your attention today." if priorities else "You're all caught up today."),
        "summary": (ai or {}).get("summary") or _rule_summary(facts),
        "tip": (ai or {}).get("teaching_tip") or (f"Several students are weak in {common_weak[0][0]}: open with a 5-minute recap of it." if common_weak else "Start each session by asking what the student found hardest since last time."),
        "priorities": priorities[:7],
        "lines": {"risk": risk_lines[:4], "good": good_lines[:3]},
        "commonWeakTopics": [{"topic": k, "count": len(v), "students": v[:5]} for k, v in common_weak],
        "generatedAt": _now().isoformat(),
        "source": "ai" if ai else "rules",
    }
    with session_scope() as db:
        _cache_put(db, key, tutor_id, "brief", brief)
    return brief


def _rule_summary(f: dict) -> str:
    parts = []
    if f["sessions_next_24h"]:
        parts.append(f"You have {f['sessions_next_24h']} session(s) in the next 24 hours.")
    if f["pending_requests"]:
        parts.append(f"{f['pending_requests']} student(s) are waiting for your reply.")
    if f["at_risk_students"]:
        parts.append(f"{len(f['at_risk_students'])} student(s) need attention.")
    return " ".join(parts) or "No urgent work. A good day to plan ahead or improve your profile."


# ------------------------------------------------------------------ 2. session prep

@ai_router.get("/api/tutor/{tutor_id}/ai/session-prep/{user_id}/{session_id}")
def session_prep(tutor_id: str, user_id: str, session_id: str, refresh: bool = False):
    _require_db()
    key = f"prep:{tutor_id}:{user_id}:{session_id}"
    with session_scope() as db:
        _get_tutor(db, tutor_id)
        _require_link(db, tutor_id, user_id)
        s = db.get(pm.LiveSession, (user_id, session_id))
        if not s or s.tutor_id != tutor_id:
            raise HTTPException(status_code=404, detail="Session not found")
        if not refresh and (cached := _cache_get(db, key)):
            return cached
        brief = _student_brief(db, user_id)
        course = _course(db, user_id, s.study_set_id)
        weak = [t for t in _topic_strengths(db, user_id) if t["pct"] < WEAK][:6]
        recent = [{"lesson": (a.data or {}).get("lessonTitle", ""), "score": a.score_pct, "weak": (a.data or {}).get("weakTopics", [])}
                  for a in db.scalars(select(pm.QuizAttempt).where(pm.QuizAttempt.user_id == user_id).order_by(pm.QuizAttempt.completed_at.desc()).limit(4))]
        last = db.scalars(select(m.SessionSummary).where(m.SessionSummary.user_id == user_id, m.SessionSummary.tutor_id == tutor_id)
                          .order_by(m.SessionSummary.created_at.desc()).limit(1)).first()
        duration = s.duration_min
    next_day = None
    if course:
        next_day = next((d for d in course["roadmap"] if d["day"] not in course["completedDays"]), None)
    prompt = f"""You are an expert teacher preparing a {duration}-minute one-to-one online session.
Student: {brief['name']}, level {brief['level'] or 'unknown'}, quiz average {brief['avgScore']}.
Course: {course['topic'] if course else 'unknown'} ({course['progress'] if course else 0}% done).
Next lesson in the course: {next_day}
Weak topics (quiz % correct): {weak}
Recent quizzes: {recent}
Last session summary: {last.summary if last else 'none'}; homework given: {last.homework if last else []}; planned next focus: {last.next_focus if last else ''}

Return JSON: {{"focus": ["2-3 things to focus on and why, one line each"],
"lesson_plan": [{{"minutes": 10, "title": "Warm-up", "activity": "what exactly to do"}}],
"questions": ["3 questions to ask the student to check understanding"],
"misconceptions": ["likely mistakes to watch for"],
"homework_idea": "one short homework suggestion"}}
The lesson_plan minutes must add up to {duration}. Be specific to this student and topic."""
    with ai_errors():
        data = generate_json(prompt, max_tokens=1500)
    plan = [{"minutes": int(p.get("minutes") or 0), "title": str(p.get("title", "")), "activity": str(p.get("activity", ""))}
            for p in (data.get("lesson_plan") or []) if isinstance(p, dict)][:8]
    prep = {
        "focus": _strs(data.get("focus"), 4), "lessonPlan": plan, "questions": _strs(data.get("questions"), 5),
        "misconceptions": _strs(data.get("misconceptions"), 5), "homeworkIdea": str(data.get("homework_idea", "")),
        "weakTopics": weak, "nextLesson": next_day, "generatedAt": _now().isoformat(),
    }
    with session_scope() as db:
        _cache_put(db, key, tutor_id, "prep", prep)
    return prep


# ------------------------------------------------------------------ 3. session wrap-up

class SummaryDraftIn(BaseModel):
    rough_notes: str = Field(min_length=3, max_length=4000)


class SummaryIn(BaseModel):
    summary: str = Field(min_length=3, max_length=4000)
    homework: List[str] = []
    next_focus: str = ""


@ai_router.post("/api/tutor/{tutor_id}/ai/session-summary/{user_id}/{session_id}")
def draft_session_summary(tutor_id: str, user_id: str, session_id: str, body: SummaryDraftIn):
    """Turn the tutor's rough notes into a clean summary + homework (a draft the tutor edits)."""
    _require_db()
    with session_scope() as db:
        _get_tutor(db, tutor_id)
        _require_link(db, tutor_id, user_id)
        s = db.get(pm.LiveSession, (user_id, session_id))
        if not s or s.tutor_id != tutor_id:
            raise HTTPException(status_code=404, detail="Session not found")
        topic = (s.data or {}).get("topic", "")
        name = _student_brief(db, user_id)["name"]
    with ai_errors():
        data = generate_json(f"""A tutor wrote these rough notes after a session with {name} on "{topic}":
\"\"\"{body.rough_notes}\"\"\"
Write a message the STUDENT will read. Return JSON:
{{"summary": "3-5 warm, clear sentences: what we covered and what went well",
"homework": ["2-4 short, specific homework tasks"], "next_focus": "what we will focus on next time, one sentence"}}
Use only what is in the notes; do not invent results.""", max_tokens=900)
    return {"summary": str(data.get("summary", "")), "homework": _strs(data.get("homework"), 5), "nextFocus": str(data.get("next_focus", ""))}


@ai_router.post("/api/tutor/{tutor_id}/sessions/{user_id}/{session_id}/summary")
def save_session_summary(tutor_id: str, user_id: str, session_id: str, body: SummaryIn):
    """Tutor approves the summary: session marked completed and the student is notified."""
    _require_db()
    with session_scope() as db:
        t = _get_tutor(db, tutor_id)
        s = db.get(pm.LiveSession, (user_id, session_id))
        if not s or s.tutor_id != tutor_id:
            raise HTTPException(status_code=404, detail="Session not found")
        row = db.get(m.SessionSummary, (user_id, session_id)) or m.SessionSummary(user_id=user_id, session_id=session_id, tutor_id=tutor_id)
        row.summary, row.homework, row.next_focus = body.summary, [h for h in body.homework if h.strip()][:8], body.next_focus
        db.add(row)
        outcome = db.get(m.SessionOutcome, (user_id, session_id))
        if not outcome or outcome.outcome != "completed":
            outcome = outcome or m.SessionOutcome(user_id=user_id, session_id=session_id, tutor_id=tutor_id)
            outcome.outcome = "completed"
            t.sessions_completed += 1
        outcome.notes = body.summary
        db.add(outcome)
        _notify_student(db, user_id, "session", f"Session summary from {t.name}",
                        body.summary[:220] + (f" Homework: {len(row.homework)} task(s)." if row.homework else ""), "/student/sessions")
    return {"ok": True}


# ------------------------------------------------------------------ 4. feedback co-pilot

class FeedbackDraftIn(BaseModel):
    score_pct: Optional[float] = None
    tone: Literal["encouraging", "direct"] = "encouraging"


@ai_router.post("/api/tutor/{tutor_id}/ai/feedback-draft/{user_id}/{submission_id}")
def feedback_draft(tutor_id: str, user_id: str, submission_id: str, body: FeedbackDraftIn):
    _require_db()
    with session_scope() as db:
        t = _get_tutor(db, tutor_id)
        _require_link(db, tutor_id, user_id, accepted_only=True)
        s = db.get(pm.Submission, (user_id, submission_id))
        if not s:
            raise HTTPException(status_code=404, detail="Submission not found")
        d = dict(s.data)
        name = _student_brief(db, user_id)["name"].split(" ")[0]
    details = d.get("details") or {}
    with ai_errors():
        data = generate_json(f"""You are {t.name}, a tutor, writing feedback to your student {name} on a {s.kind} submission.
Task: {str(d.get('prompt', ''))[:2000]}
Student's answer: \"\"\"{str(d.get('answer', ''))[:4000]}\"\"\"
AI grade: {s.score_pct}% — AI feedback: {d.get('feedback', '')}
Part marks: {details.get('parts', [])}; rubric: {details.get('rubric')}
Final score the tutor is giving: {body.score_pct if body.score_pct is not None else s.score_pct}%
Tone: {body.tone}. Return JSON: {{"feedback": "4-6 sentences in first person: one specific strength (quote their answer), the most important
mistake and how to fix it, and one next step. No headings."}}""", max_tokens=700)
    return {"feedback": str(data.get("feedback", "")).strip()}


# ------------------------------------------------------------------ 5. smart risk insight

@ai_router.get("/api/tutor/{tutor_id}/ai/risk/{user_id}")
def risk_insight(tutor_id: str, user_id: str, refresh: bool = False):
    _require_db()
    key = f"risk:{tutor_id}:{user_id}:{date.today().isoformat()}"
    with session_scope() as db:
        _get_tutor(db, tutor_id)
        _require_link(db, tutor_id, user_id)
        if not refresh and (cached := _cache_get(db, key)):
            return cached
        brief = _student_brief(db, user_id)
        sig = signals(db, tutor_id, user_id)
        weak = [t for t in _topic_strengths(db, user_id) if t["pct"] < WEAK][:5]
        reqs = db.scalars(select(pm.TutorRequest).where(pm.TutorRequest.user_id == user_id, pm.TutorRequest.tutor_id == tutor_id)).all()
        courses = [c for c in (_course(db, user_id, r.study_set_id) for r in reqs) if c]
    progress = round(sum(c["progress"] for c in courses) / len(courses)) if courses else 0
    inactive = (_now() - datetime.fromisoformat(brief["lastActive"])).days if brief["lastActive"] else None

    # Explainable score: 0 = fine, 100 = at high risk
    points, reasons = 0, []
    if brief["avgScore"] is not None and brief["avgScore"] < WEAK:
        points += 30; reasons.append(f"quiz average {brief['avgScore']}%")
    if sig["trend"] <= -10:
        points += 25; reasons.append(f"scores falling ({sig['trend']:+.0f} points recently)")
    if inactive is not None and inactive >= 5:
        points += 25; reasons.append(f"inactive for {inactive} days")
    elif inactive is None and progress == 0:
        points += 15; reasons.append("has not started")
    if sig["noShows"]:
        points += 15 * min(sig["noShows"], 2); reasons.append(f"missed {sig['noShows']} session(s)")
    if sig["overduePractice"]:
        points += 10; reasons.append(f"{sig['overduePractice']} overdue practice task(s)")
    if len(weak) >= 3:
        points += 10; reasons.append(f"{len(weak)} weak topics")
    points = min(points, 100)
    level = "high" if points >= 50 else "medium" if points >= 20 else "low"

    ai = _try_ai(f"""A tutor asks about student {brief['name']}. Facts: level {level} risk ({points}/100), reasons {reasons},
quiz scores over time {sig['scores']}, course progress {progress}%, weak topics {weak}, last active {brief['lastActive']}.
Return JSON: {{"explanation": "2 sentences on what is going on", "action": "the single best thing the tutor should do this week",
"message_to_student": "a short, kind message the tutor could send (2 sentences)"}}. Use only these facts.""", max_tokens=500)
    insight = {
        "level": level, "score": points, "reasons": reasons, "signals": sig, "progress": progress, "weakTopics": weak,
        "explanation": (ai or {}).get("explanation") or ("On track: keep the current pace." if level == "low" else f"Flagged because of: {', '.join(reasons)}."),
        "action": (ai or {}).get("action") or ("Assign a short practice quiz on the weakest topic." if weak else "Book the next session and set a small goal."),
        "messageToStudent": (ai or {}).get("message_to_student") or f"Hi {brief['name'].split(' ')[0]}, how are your studies going? Let's plan your next step together.",
        "generatedAt": _now().isoformat(), "source": "ai" if ai else "rules",
    }
    with session_scope() as db:
        _cache_put(db, key, tutor_id, "risk", insight)
    return insight


# ------------------------------------------------------------------ 6. assign practice

class PracticeIn(BaseModel):
    kind: Literal["quiz", "case"] = "quiz"
    topic: str = Field(min_length=2, max_length=300)
    study_set_id: str = ""
    due_days: int = Field(default=3, ge=1, le=30)
    note: str = Field(default="", max_length=1000)


def _practice_public(p: m.AssignedPractice, hide_answers: bool) -> dict:
    payload = dict(p.payload or {})
    if hide_answers:
        if p.kind == "quiz":
            payload = {"mcq": [{"question": q["question"], "options": q["options"], "topic": q.get("topic", "")} for q in payload.get("mcq", [])],
                       "short": [{"question": q["question"], "topic": q.get("topic", "")} for q in payload.get("short", [])]}
        else:
            payload = {"scenario": payload.get("scenario", ""), "parts": [{"question": q["question"]} for q in payload.get("parts", [])]}
    return {
        "id": p.id, "userId": p.user_id, "tutorId": p.tutor_id, "kind": p.kind, "topic": p.topic, "title": p.title, "note": p.note,
        "studySetId": p.study_set_id, "dueAt": _iso(p.due_at), "status": p.status, "createdAt": _iso(p.created_at),
        "completedAt": _iso(p.completed_at), "payload": payload, "result": p.result,
    }


@ai_router.post("/api/tutor/{tutor_id}/practice/{user_id}")
def assign_practice(tutor_id: str, user_id: str, body: PracticeIn):
    _require_db()
    with session_scope() as db:
        t = _get_tutor(db, tutor_id)
        _require_link(db, tutor_id, user_id, accepted_only=True)
        brief = _student_brief(db, user_id)
        course = _course(db, user_id, body.study_set_id) if body.study_set_id else None
    title = f"{body.topic} — {'practice quiz' if body.kind == 'quiz' else 'case study'}"
    course_title = course["topic"] if course else body.topic
    level, language = brief["level"] or "New to this", brief["language"] or "English"
    if body.kind == "quiz":
        q = generate_quiz(QuizRequest(course_title=course_title, lesson_title=body.topic, topics=[body.topic],
                                      level=level, language=language, num_mcq=5, num_short=1))
        payload = {"mcq": [x.model_dump() for x in q.mcq], "short": [x.model_dump() for x in q.short]}
    else:
        c = _case_prompt(PromptRequest(course_title=course_title, lesson_title=body.topic, kind="case", level=level, language=language))
        if not c.get("parts"):
            raise HTTPException(status_code=502, detail="The AI could not write a case study. Please try again.")
        payload = {"scenario": c["prompt"], "parts": c["parts"]}
    with session_scope() as db:
        p = m.AssignedPractice(user_id=user_id, id=f"pr_{uuid.uuid4().hex[:10]}", tutor_id=tutor_id, study_set_id=body.study_set_id,
                               kind=body.kind, topic=body.topic, title=title, note=body.note,
                               due_at=_now() + timedelta(days=body.due_days), payload=payload)
        db.add(p)
        _notify_student(db, user_id, "quiz", f"{t.name} assigned you practice", f"{title}. Due in {body.due_days} day(s)."
                        + (f" Note: {body.note}" if body.note else ""), "/student/assessments")
        db.flush()
        return {"practice": _practice_public(p, hide_answers=False)}


@ai_router.get("/api/tutor/{tutor_id}/practice")
def tutor_practice(tutor_id: str, user_id: Optional[str] = None):
    _require_db()
    with session_scope() as db:
        _get_tutor(db, tutor_id)
        q = select(m.AssignedPractice).where(m.AssignedPractice.tutor_id == tutor_id)
        if user_id:
            q = q.where(m.AssignedPractice.user_id == user_id)
        rows = db.scalars(q.order_by(m.AssignedPractice.created_at.desc())).all()
        return {"items": [_practice_public(p, hide_answers=False) for p in rows]}


# ---- student side

class PracticeAnswers(BaseModel):
    mcq: List[Optional[int]] = []
    short: List[str] = []
    parts: List[str] = []


@ai_router.get("/api/portal/practice/{user_id}")
def student_practice(user_id: str):
    _require_db()
    with session_scope() as db:
        rows = db.scalars(select(m.AssignedPractice).where(m.AssignedPractice.user_id == user_id).order_by(m.AssignedPractice.created_at.desc())).all()
        names = {t.id: t.name for t in db.scalars(select(m.Tutor).where(m.Tutor.id.in_({r.tutor_id for r in rows} or {""})))}
        return {"items": [{**_practice_public(p, hide_answers=p.status != "completed"), "tutorName": names.get(p.tutor_id, "Your tutor")} for p in rows]}


@ai_router.post("/api/portal/practice/{user_id}/{practice_id}/submit")
def submit_practice(user_id: str, practice_id: str, body: PracticeAnswers):
    _require_db()
    with session_scope() as db:
        p = db.get(m.AssignedPractice, (user_id, practice_id))
        if not p:
            raise HTTPException(status_code=404, detail="Practice not found")
        if p.status == "completed":
            raise HTTPException(status_code=409, detail="You already submitted this practice.")
        kind, payload, tutor_id = p.kind, dict(p.payload), p.tutor_id
        language = _student_brief(db, user_id)["language"] or "English"

    if kind == "quiz":
        mcq, short = payload.get("mcq", []), payload.get("short", [])
        marks, topic_results, review = 0.0, {}, []
        for i, q in enumerate(mcq):
            chosen = body.mcq[i] if i < len(body.mcq) else None
            right = chosen == q["answer_index"]
            marks += 1 if right else 0
            tr = topic_results.setdefault(q.get("topic") or "General", {"correct": 0, "total": 0})
            tr["total"] += 1
            tr["correct"] += 1 if right else 0
            review.append({"question": q["question"], "correct": right, "chosen": chosen, "answer": q["answer_index"], "explanation": q.get("explanation", "")})
        for i, q in enumerate(short):
            ans = body.short[i] if i < len(body.short) else ""
            try:
                g = grade_short(ShortGradeRequest(question=q["question"], reference_answer=q.get("reference_answer", ""), answer=ans, language=language))
                score, fb = g.score, g.feedback
            except Exception:  # noqa: BLE001 - AI down: count as not graded
                score, fb = 0.0, "Could not be graded automatically; your tutor will check it."
            marks += score / 10
            review.append({"question": q["question"], "score": score, "answer": ans, "feedback": fb, "reference": q.get("reference_answer", "")})
        total = max(len(mcq) + len(short), 1)
        result = {"scorePct": round(marks / total * 100), "review": review, "topicResults": topic_results, "answers": body.model_dump()}
    else:
        parts = payload.get("parts", [])
        graded = grade_case(CaseRequest(scenario=payload.get("scenario", ""), language=language,
                                        parts=[CasePart(question=q["question"], reference_answer=q.get("reference_answer", ""),
                                                        answer=body.parts[i] if i < len(body.parts) else "") for i, q in enumerate(parts)]))
        result = {"scorePct": round(graded.score), "feedback": graded.feedback, "parts": graded.parts, "rubric": graded.rubric,
                  "answers": body.model_dump()}

    with session_scope() as db:
        p = db.get(m.AssignedPractice, (user_id, practice_id))
        p.status, p.result, p.completed_at = "completed", result, _now()
        from .comms import notify_tutor

        notify_tutor(db, tutor_id, "practice", f"{_student_brief(db, user_id)['name']} finished practice: {result['scorePct']}%",
                     p.title, f"/tutor/students/{user_id}")
        db.flush()
        names = {tutor_id: db.get(m.Tutor, tutor_id).name}
        return {"practice": {**_practice_public(p, hide_answers=False), "tutorName": names[tutor_id]}}


# ------------------------------------------------------------------ 7. request fit score

def fit_score(db, t: m.Tutor, user_id: str, study_set_id: str) -> dict:
    """0-100 match between a request and the tutor, with the factors shown to the tutor."""
    brief = _student_brief(db, user_id)
    course = _course(db, user_id, study_set_id)
    subj = (course or {}).get("subject", "").lower()
    taught = [s.lower() for s in (t.subjects or [t.subject])]
    subject_ok = bool(subj) and any(subj in s or s in subj for s in taught)
    active_ok = (brief.get("studyMin7") or 0) > 0 or (brief.get("quizzes") or 0) > 0 or (brief.get("classesAttended") or 0) > 0
    active = db.scalar(select(func.count(func.distinct(pm.TutorRequest.user_id))).where(
        pm.TutorRequest.tutor_id == t.id, pm.TutorRequest.status == "accepted")) or 0
    seats = t.capacity - active
    avail = any(a.active for a in _availability(db, t.id))
    factors = [
        {"label": "Subject match", "ok": subject_ok, "detail": f"Course is {course['subject'] if course else 'unknown'}; you teach {', '.join(t.subjects or [t.subject])}", "weight": 45},
        {"label": "Active learner", "ok": active_ok, "detail": f"{brief.get('studyMin7') or 0} min studied this week, {brief.get('quizzes') or 0} quiz(zes), {brief.get('classesAttended') or 0} live class(es)", "weight": 20},
        {"label": "Capacity", "ok": seats > 0, "detail": f"{max(seats, 0)} open seat(s)", "weight": 20},
        {"label": "Availability", "ok": avail, "detail": "You have weekly hours set" if avail else "No weekly hours set", "weight": 15},
    ]
    score = sum(f["weight"] for f in factors if f["ok"])
    return {"score": score, "factors": factors, "label": "Great fit" if score >= 80 else "Good fit" if score >= 55 else "Weak fit"}


@ai_router.get("/api/tutor/{tutor_id}/ai/fit/{user_id}/{request_id}")
def request_fit(tutor_id: str, user_id: str, request_id: str):
    _require_db()
    with session_scope() as db:
        t = _get_tutor(db, tutor_id)
        r = db.get(pm.TutorRequest, (user_id, request_id))
        if not r or r.tutor_id != tutor_id:
            raise HTTPException(status_code=404, detail="Request not found")
        fit = fit_score(db, t, user_id, r.study_set_id)
        brief = _student_brief(db, user_id)
        course = _course(db, user_id, r.study_set_id)
        key = f"fit:{tutor_id}:{user_id}:{request_id}"
        cached = _cache_get(db, key)
    if cached:
        return {**fit, "reason": cached.get("reason", "")}
    ai = _try_ai(f"""Tutor {t.name} teaches {t.subject} ({t.experience_years} years). A student asks for help.
Student: quiz average {brief['avgScore']}, {brief.get('studyMin7') or 0} min studied this week, {brief.get('classesAttended') or 0} live classes so far, message: "{(r.data or {}).get('message', '')}".
Course: {course['topic'] if course else ''} ({course['subject'] if course else ''}), {course['progress'] if course else 0}% done.
Match factors: {fit['factors']} → score {fit['score']}/100.
Return JSON: {{"reason": "2 sentences: is this a good match and what the tutor should focus on if they accept"}}""", max_tokens=300)
    reason = (ai or {}).get("reason") or ("; ".join(f["detail"] for f in fit["factors"] if not f["ok"]) or "Matches your subject, capacity and hours, and the student is active.")
    with session_scope() as db:
        _cache_put(db, f"fit:{tutor_id}:{user_id}:{request_id}", tutor_id, "fit", {"reason": reason})
    return {**fit, "reason": reason}
