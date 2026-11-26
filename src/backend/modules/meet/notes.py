"""AI class notes: after a live class, the transcript + chat (+ whiteboard) become study notes.

During the class each participant's browser sends ~30 s pieces of its OWN microphone (only while the mic is on and
the tutor has "AI class notes" on); Groq Whisper turns them into text (MeetingTranscript). Without a Groq key the
browser's captions are saved instead. When the class ends (or someone opens the notes later) the LLM gateway writes:
summary, key points, biology terms, questions asked + answers, homework and a 5-question quiz (MeetingNotes).
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import select

from core import db as core_db
from modules.meet import access
from modules.meet.models import MeetingMessage, MeetingNotes, MeetingTranscript

log = logging.getLogger("neuralhub.meet.notes")

MAX_CHARS = 14_000          # transcript sent to the model in one go; longer classes are summarised in parts first
MIN_WORDS = 25              # less than this was said: no notes ("empty")
# Whisper sometimes "hears" these in silence or noise
JUNK = re.compile(r"^\W*(thank(s| you)( (so much|for watching))?|you|bye|okay|subtitles by.*|\.+)\W*$", re.I)


class Term(BaseModel):
    term: str
    meaning: str


class QA(BaseModel):
    question: str
    answer: str = ""


class Mcq(BaseModel):
    question: str
    options: list[str] = Field(min_length=2, max_length=5)
    answer_index: int = 0
    explanation: str = ""


class NotesOut(BaseModel):
    title: str = ""
    summary: str
    key_points: list[str] = []
    terms: list[Term] = []
    questions: list[QA] = []
    homework: list[str] = []
    quiz: list[Mcq] = []


def clean_piece(text: str) -> str:
    t = (text or "").strip()
    return "" if not t or JUNK.match(t) else t[:4000]


def transcript_text(db, room: str) -> tuple[str, int]:
    """'[mm:ss] Name (role): text' lines, oldest first, with the class chat mixed in by time."""
    rows = db.scalars(select(MeetingTranscript).where(MeetingTranscript.room == room).order_by(MeetingTranscript.id)).all()
    chat = db.scalars(select(MeetingMessage).where(MeetingMessage.room == room).order_by(MeetingMessage.id)).all()
    items = [(r.created_at, f"{r.name or r.role} ({r.role}): {r.text}") for r in rows]
    items += [(m.created_at, f"{m.sender_name or m.sender_role} ({m.sender_role}, chat): {m.body}") for m in chat]
    items.sort(key=lambda x: x[0] or access.now())
    t0 = items[0][0] if items else None

    def stamp(t):
        if not t or not t0:
            return ""
        s = int((t - t0).total_seconds())
        return f"[{s // 60:02d}:{s % 60:02d}] "
    return "\n".join(stamp(t) + line for t, line in items), len(rows)


PROMPT = """You are writing study notes for students after a live online BIOLOGY class.
Class topic: {topic}

Below is the transcript of what was said (speech recognised automatically, so expect small mistakes) and the class
chat. People may speak English, Urdu or a mix; write the notes in clear, simple English and keep biology terms exact.
Use ONLY what was taught in this class; do not invent facts that were not discussed. If something in the transcript
is clearly a recognition error, ignore it.

Write:
- title: a short title for this class
- summary: 4-6 sentences on what the class covered
- key_points: the 5-10 most important things to remember
- terms: biology terms that came up, each with a one-line meaning
- questions: questions students asked (in speech or chat) with the tutor's answer (or a correct short answer)
- homework: tasks or reading the tutor gave, or what comes next class (empty if none)
- quiz: 5 multiple-choice questions on this class (4 options, answer_index 0-3, one-line explanation)

TRANSCRIPT:
{transcript}
"""

PART_PROMPT = """Summarise this part of a live biology class transcript as detailed bullet points (facts taught,
terms, questions and answers, homework). Keep everything that was taught; skip greetings and small talk.

{part}
"""


def _gateway():
    from modules.professor.llm.gateway import gateway
    return gateway


def write_notes(topic: str, transcript: str) -> dict:
    gw = _gateway()
    text = transcript
    if len(text) > MAX_CHARS:  # long class: condense part by part first
        parts = [text[i:i + MAX_CHARS] for i in range(0, len(text), MAX_CHARS)]
        text = "\n\n".join(gw.generate_text("meet_notes_part", PART_PROMPT.format(part=p), max_tokens=1200,
                                            timeout_s=60).data for p in parts)[:MAX_CHARS]
    out = gw.generate_json("meet_notes", PROMPT.format(topic=topic or "Live class", transcript=text), NotesOut,
                           temperature=0.3, max_tokens=3000, timeout_s=90).data
    quiz = [q.model_dump() for q in out.quiz if 0 <= q.answer_index < len(q.options)][:5]
    return {"title": out.title, "summary": out.summary, "keyPoints": out.key_points[:12],
            "terms": [t.model_dump() for t in out.terms][:20], "questions": [q.model_dump() for q in out.questions][:15],
            "homework": out.homework[:8],
            "quiz": [{"question": q["question"], "options": q["options"], "answerIndex": q["answer_index"],
                      "explanation": q["explanation"]} for q in quiz]}


_running: set[str] = set()
_lock = threading.Lock()


def generate(room: str, topic: str) -> None:
    """Make (or remake) the notes of one class. Safe to call twice: the second call does nothing while one runs."""
    with _lock:
        if room in _running:
            return
        _running.add(room)
    try:
        with core_db.session_scope() as db:
            n = db.get(MeetingNotes, room) or MeetingNotes(room=room, board=[])
            n.status, n.error, n.updated_at = "working", "", access.now()
            db.add(n)
            transcript, lines = transcript_text(db, room)
        if len(transcript.split()) < MIN_WORDS:
            content, status, err = {}, "empty", ""
        else:
            try:
                content, status, err = write_notes(topic, transcript), "ready", ""
            except Exception as e:  # noqa: BLE001 - shown as "failed", the tutor can try again
                log.warning("class notes failed for %s: %s", room, e)
                content, status, err = {}, "failed", str(e)[:300]
        with core_db.session_scope() as db:
            n = db.get(MeetingNotes, room) or MeetingNotes(room=room, board=[])
            n.status, n.content, n.lines, n.error, n.updated_at = status, content, lines, err, access.now()
            db.add(n)
    finally:
        with _lock:
            _running.discard(room)


def generate_later(room: str, topic: str, delay: float = 0.0) -> None:
    def run():
        if delay:
            import time
            time.sleep(delay)
        generate(room, topic)
    threading.Thread(target=run, daemon=True, name=f"notes-{room}").start()


def view(n: Optional[MeetingNotes]) -> dict:
    if n is None:
        return {"status": "none"}
    return {"status": n.status, "notes": n.content or {}, "board": n.board or [], "lines": n.lines,
            "updatedAt": n.updated_at.isoformat() if n.updated_at else None}
