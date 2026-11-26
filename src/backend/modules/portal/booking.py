"""Booking live classes by slot: no double booking.

The tutor's weekly hours (tutor_availability, in the tutor's time zone) are cut into one-hour slots.
A slot is free only when nothing else uses that hour: another student's class with the tutor, one of the
tutor's group or instant classes, or a day off. A student also cannot book two classes at the same time.

Rules (agreed with the product owner):
- one accepted request = one class; a class cancelled before it starts gives the request back
- a class whose time has passed without the student joining can be reset (status "missed"): the request is free again
- every class is one hour; a class can be cancelled only before it starts
- the server is the only place a class is created (POST /api/portal/book/...), under a per-tutor lock,
  so two students pressing the same slot at once cannot both get it.

    GET    /api/portal/slots/{tutor_id}?user=…&days=14     the tutor's slots for a student (free / booked / …)
    POST   /api/portal/book/{user_id}                       book one slot with an accepted request
    POST   /api/portal/cancel/{user_id}/{session_id}        cancel a class (only before it starts)
    POST   /api/portal/release/{user_id}/{session_id}       reset a missed class (time passed, student never joined)
    GET    /api/tutor/{tutor_id}/slots?days=7               the tutor's own day plan (who is in which slot)
    GET    /api/tutor/{tutor_id}/time-off                   days off
    POST   /api/tutor/{tutor_id}/time-off                   add a day off   {day: "YYYY-MM-DD", note}
    DELETE /api/tutor/{tutor_id}/time-off/{day}             remove a day off
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from core import db as dbmod
from core.db import session_scope
from modules.meet.models import MeetingAttendance, MeetingCode, MeetingRoom, MeetingSeat
from modules.tutor import models as tm

from . import models as m

router = APIRouter(tags=["Class booking"])

SLOT_MIN = 60          # every class is one hour
MIN_NOTICE_MIN = 60    # a slot must start at least this long from now
MAX_DAYS = 28          # how far ahead students can book
DEFAULT_HOURS = {d: ("17:00", "21:00") for d in range(5)}  # tutor without weekly hours: Mon–Fri 5–9 PM


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _tz(t: tm.Tutor) -> ZoneInfo:
    try:
        return ZoneInfo(t.timezone or "Asia/Karachi")
    except Exception:  # noqa: BLE001 - unknown zone name
        return ZoneInfo("UTC")


def _hm(s: str) -> time:
    h, mm = (int(x) for x in s.split(":"))
    return time(min(h, 23), min(mm, 59))


def _overlap(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> bool:
    return a0 < b1 and b0 < a1


def _require_db():
    if not dbmod.status["connected"]:
        raise HTTPException(status_code=503, detail="Database not connected")


# ------------------------------------------------------------------ what is busy

def _weekly(db, tutor_id: str) -> dict[int, tuple[str, str]]:
    rows = list(db.scalars(select(tm.TutorAvailability).where(tm.TutorAvailability.tutor_id == tutor_id)))
    if not rows:
        return dict(DEFAULT_HOURS)
    return {r.weekday: (r.start_time, r.end_time) for r in rows if r.active and r.start_time < r.end_time}


def _days_off(db, tutor_id: str) -> dict[date, str]:
    return {r.day: r.note for r in db.scalars(select(tm.TutorTimeOff).where(tm.TutorTimeOff.tutor_id == tutor_id))}


def _tutor_busy(db, tutor_id: str, start: datetime, end: datetime) -> list[dict]:
    """The tutor's classes between start and end: booked one-to-one classes and his group / instant classes."""
    out = []
    for s in db.scalars(select(m.LiveSession).where(
            m.LiveSession.tutor_id == tutor_id, m.LiveSession.status == "scheduled",
            m.LiveSession.starts_at >= start - timedelta(hours=6), m.LiveSession.starts_at < end)):
        st = _aware(s.starts_at)
        out.append({"kind": "class", "start": st, "end": st + timedelta(minutes=s.duration_min or SLOT_MIN),
                    "userId": s.user_id, "sessionId": s.id, "topic": (s.data or {}).get("topic", "")})
    for c in db.scalars(select(MeetingCode).where(
            MeetingCode.tutor_id == tutor_id, MeetingCode.kind.in_(("group", "instant")),
            MeetingCode.cancelled_at.is_(None), MeetingCode.starts_at.is_not(None),
            MeetingCode.starts_at >= start - timedelta(hours=6), MeetingCode.starts_at < end)):
        st = _aware(c.starts_at)
        out.append({"kind": "group" if c.kind == "group" else "instant", "start": st,
                    "end": st + timedelta(minutes=c.duration_min or SLOT_MIN), "topic": c.topic or ""})
    return out


def _student_busy(db, user_id: str, start: datetime, end: datetime) -> list[dict]:
    """The student's own classes (with any tutor) and group classes he holds a seat in."""
    out = []
    for s in db.scalars(select(m.LiveSession).where(
            m.LiveSession.user_id == user_id, m.LiveSession.status == "scheduled",
            m.LiveSession.starts_at >= start - timedelta(hours=6), m.LiveSession.starts_at < end)):
        st = _aware(s.starts_at)
        out.append({"start": st, "end": st + timedelta(minutes=s.duration_min or SLOT_MIN), "tutorId": s.tutor_id})
    seats = select(MeetingSeat.code).where(MeetingSeat.user_id == user_id, MeetingSeat.cancelled.is_(False),
                                           MeetingSeat.status == "reserved")
    for c in db.scalars(select(MeetingCode).where(MeetingCode.code.in_(seats), MeetingCode.cancelled_at.is_(None),
                                                  MeetingCode.starts_at.is_not(None),
                                                  MeetingCode.starts_at >= start - timedelta(hours=6),
                                                  MeetingCode.starts_at < end)):
        st = _aware(c.starts_at)
        out.append({"start": st, "end": st + timedelta(minutes=c.duration_min or SLOT_MIN), "tutorId": c.tutor_id})
    return out


# ------------------------------------------------------------------ slots

def plan(db, t: tm.Tutor, user_id: Optional[str], days: int, names: Optional[dict] = None) -> list[dict]:
    """Day by day, the tutor's one-hour slots and their state.

    state: free | mine (this student's class with this tutor) | booked (another student) | group (the tutor's group
    or instant class) | busy (the student has another class then) | past (too soon or over) | off (day off)
    With `names` (tutor view) a booked slot also says who.
    """
    tz = _tz(t)
    weekly, off = _weekly(db, t.id), _days_off(db, t.id)
    today = now().astimezone(tz).date()
    first = datetime.combine(today, time(0), tz)
    last = first + timedelta(days=days + 1)
    tutor_busy = _tutor_busy(db, t.id, first, last)
    mine_busy = _student_busy(db, user_id, first, last) if user_id else []
    t_now = now()
    soon = t_now + timedelta(minutes=MIN_NOTICE_MIN)
    out = []
    for i in range(days):
        d = today + timedelta(days=i)
        hours = weekly.get(d.weekday())
        day = {"date": d.isoformat(), "weekday": d.weekday(), "off": d in off, "note": off.get(d, ""), "slots": [],
               "teaches": bool(hours), "closed": False}
        if hours:
            cur = datetime.combine(d, _hm(hours[0]), tz)
            stop = datetime.combine(d, _hm(hours[1]), tz)
            while cur + timedelta(minutes=SLOT_MIN) <= stop:
                s0, s1 = cur.astimezone(timezone.utc), (cur + timedelta(minutes=SLOT_MIN)).astimezone(timezone.utc)
                slot = {"start": s0.isoformat().replace("+00:00", "Z"), "end": s1.isoformat().replace("+00:00", "Z"),
                        "label": cur.strftime("%I:%M %p").lstrip("0"), "state": "free"}
                hit = next((b for b in tutor_busy if _overlap(s0, s1, b["start"], b["end"])), None)
                if hit and hit["kind"] == "class":
                    slot["state"] = "mine" if user_id and hit["userId"] == user_id else "booked"
                    if names is not None:
                        slot.update(student=names.get(hit["userId"], "A student"), userId=hit["userId"],
                                    sessionId=hit["sessionId"], topic=hit["topic"])
                elif hit:
                    slot["state"] = "group"
                    if names is not None:
                        slot["topic"] = hit["topic"]
                elif day["off"]:
                    slot["state"] = "off"
                elif s0 < soon:
                    slot["state"] = "past"
                elif any(_overlap(s0, s1, b["start"], b["end"]) for b in mine_busy):
                    slot["state"] = "busy"
                cur += timedelta(minutes=SLOT_MIN)
                # times that are over (or too close to book) are left out; the tutor still sees classes that happened today
                if s0 < (t_now if names is not None else soon) and slot["state"] not in ("mine", "booked", "group"):
                    continue
                if names is None and s1 <= t_now:
                    continue
                day["slots"].append(slot)
        # the tutor teaches this day but no time is left today
        day["closed"] = bool(hours) and not day["off"] and not day["slots"]
        out.append(day)
    return out


WHY = {
    "booked": "Another student has just booked this time. Please pick another slot.",
    "mine": "You already have a class with this tutor at this time.",
    "group": "The tutor has a group class at this time. Please pick another slot.",
    "busy": "You have another class at this time. Please pick another slot.",
    "past": f"Classes must be booked at least {MIN_NOTICE_MIN} minutes before they start. Please pick a later time.",
    "off": "The tutor is not teaching on this day. Please pick another day.",
}


# ------------------------------------------------------------------ one request = one class

def _accepted_request(db, user_id: str, request_id: str) -> m.TutorRequest:
    r = db.get(m.TutorRequest, (user_id, request_id))
    if r is None or r.status != "accepted":
        raise HTTPException(status_code=409, detail="This request is not accepted yet. You can book after the tutor accepts it.")
    return r


def request_is_free(db, user_id: str, r: m.TutorRequest) -> bool:
    """A request gives one class. Classes that name their request use it; older ones use any request of the
    same tutor and study plan. Cancelled classes give it back."""
    active = list(db.scalars(select(m.LiveSession).where(m.LiveSession.user_id == user_id,
                                                         m.LiveSession.tutor_id == r.tutor_id,
                                                         m.LiveSession.status == "scheduled")))
    if any((s.data or {}).get("requestId") == r.id for s in active):
        return False
    pair = [s for s in active if (s.study_set_id or "") == (r.study_set_id or "")]
    accepted = db.scalars(select(m.TutorRequest).where(
        m.TutorRequest.user_id == user_id, m.TutorRequest.tutor_id == r.tutor_id,
        m.TutorRequest.study_set_id == r.study_set_id, m.TutorRequest.status == "accepted")).all()
    return len(pair) < len(accepted)


# ------------------------------------------------------------------ endpoints

@router.get("/api/portal/slots/{tutor_id}")
def slots(tutor_id: str, user: str = "", days: int = 14):
    _require_db()
    with session_scope() as db:
        t = db.get(tm.Tutor, tutor_id)
        if t is None:
            raise HTTPException(status_code=404, detail="Tutor not found")
        from modules.payments import service as pay

        return {"tutorId": t.id, "timezone": t.timezone, "slotMin": SLOT_MIN,
                "price": round(float(t.hourly_rate or 0) * SLOT_MIN / 60, 2), "currency": t.currency or "USD", "payMode": pay.mode(),
                "days": plan(db, t, user or None, max(1, min(days, MAX_DAYS)))}


class PayIn(BaseModel):
    """Checkout details. Card: only brand + last 4 digits are sent (never the full number or CVV)."""
    method: str = Field(max_length=20)
    holder: str = Field(default="", max_length=120)
    account: str = Field(default="", max_length=40)
    brand: str = Field(default="", max_length=20)


class BookIn(BaseModel):
    requestId: str = Field(min_length=1, max_length=120)
    startsAt: str = Field(min_length=10, max_length=40)
    payment: Optional[PayIn] = None


@router.post("/api/portal/book/{user_id}")
def book(user_id: str, body: BookIn):
    """Book one slot. 409 with a clear reason when the slot or the request cannot be used."""
    _require_db()
    try:
        at = _aware(datetime.fromisoformat(body.startsAt.replace("Z", "+00:00"))).astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid time")
    with session_scope() as db:
        r = _accepted_request(db, user_id, body.requestId)
        # one booking at a time per tutor and per student (the transaction holds the locks until commit)
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"book:tutor:{r.tutor_id}"})
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"book:user:{user_id}"})
        t = db.get(tm.Tutor, r.tutor_id)
        if t is None:
            raise HTTPException(status_code=404, detail="Tutor not found")
        if not request_is_free(db, user_id, r):
            raise HTTPException(status_code=409, detail="You already have a class from this request. Send a new request for another class.")
        days = (at.astimezone(_tz(t)).date() - now().astimezone(_tz(t)).date()).days + 1
        if days < 1 or days > MAX_DAYS:
            raise HTTPException(status_code=409, detail=WHY["past"] if days < 1 else "You can book up to 4 weeks ahead.")
        if at < now() + timedelta(minutes=MIN_NOTICE_MIN):
            raise HTTPException(status_code=409, detail=WHY["past"])
        slot = next((s for d in plan(db, t, user_id, days) for s in d["slots"]
                     if datetime.fromisoformat(s["start"].replace("Z", "+00:00")) == at), None)
        if slot is None:
            raise HTTPException(status_code=409, detail="This time is not one of the tutor's slots. Please pick a slot from the list.")
        if slot["state"] != "free":
            raise HTTPException(status_code=409, detail=WHY.get(slot["state"], "This slot is not free."))
        user = db.get(m.User, user_id)
        sid = f"sess_{uuid.uuid4().hex[:12]}"
        rd = r.data or {}
        data = {"id": sid, "tutorId": t.id, "tutorName": t.name, "studySetId": r.study_set_id or "",
                "topic": rd.get("studySetTopic") or rd.get("topic") or "Class", "startsAt": slot["start"],
                "durationMin": SLOT_MIN, "meetingUrl": "", "status": "scheduled", "requestId": r.id}
        last = db.scalar(select(m.LiveSession.pos).where(m.LiveSession.user_id == user_id).order_by(m.LiveSession.pos.desc()).limit(1))
        db.add(m.LiveSession(user_id=user_id, id=sid, tutor_id=t.id, study_set_id=r.study_set_id or "", starts_at=at,
                             duration_min=SLOT_MIN, status="scheduled", pos=(last or 0) + 1, data=data))
        db.flush()
        from modules.payments import wallet

        paid = wallet.charge_class(db, user_id, t, sid, SLOT_MIN, data["topic"],
                                   body.payment.model_dump() if body.payment else None)  # test mode: no real money
        if paid is not None:
            data["purchaseId"], data["price"], data["currency"] = paid.id, paid.amount, paid.currency
            db.get(m.LiveSession, (user_id, sid)).data = dict(data)
            try:  # the student's receipt notification
                from modules.tutor.router import _notify_student

                _notify_student(db, user_id, "system", f"Payment successful: {paid.currency} {paid.amount:g}",
                                f"Live class with {t.name} · {wallet.pay_label(paid)}"
                                f" · receipt {paid.id}" + (" · test payment" if paid.ref.startswith("TEST-") else ""),
                                "/student/payments")
            except Exception:  # noqa: BLE001 - the booking stands either way
                pass
        from modules.tutor.comms import notify_tutor

        notify_tutor(db, t.id, "booking", f"{(user.name if user else '') or 'A student'} booked a class", data["topic"],
                     "/tutor/schedule", at=at)
        return {"session": data}


@router.get("/api/tutor/{tutor_id}/slots")
def tutor_slots(tutor_id: str, days: int = 7):
    _require_db()
    with session_scope() as db:
        t = db.get(tm.Tutor, tutor_id)
        if t is None:
            raise HTTPException(status_code=404, detail="Tutor not found")
        names = {u.id: u.name for u in db.scalars(select(m.User).where(m.User.id.in_(
            select(m.LiveSession.user_id).where(m.LiveSession.tutor_id == tutor_id))))}
        return {"timezone": t.timezone, "days": plan(db, t, None, max(1, min(days, MAX_DAYS)), names=names)}


class TimeOffIn(BaseModel):
    day: date
    note: str = Field("", max_length=200)


def _time_off_view(db, tutor_id: str) -> list[dict]:
    rows = db.scalars(select(tm.TutorTimeOff).where(tm.TutorTimeOff.tutor_id == tutor_id).order_by(tm.TutorTimeOff.day))
    return [{"day": r.day.isoformat(), "note": r.note} for r in rows]


@router.get("/api/tutor/{tutor_id}/time-off")
def get_time_off(tutor_id: str):
    _require_db()
    with session_scope() as db:
        return {"daysOff": _time_off_view(db, tutor_id)}


@router.post("/api/tutor/{tutor_id}/time-off")
def add_time_off(tutor_id: str, body: TimeOffIn):
    """Block a day. Classes already booked that day stay (the tutor can cancel them from the schedule)."""
    _require_db()
    with session_scope() as db:
        t = db.get(tm.Tutor, tutor_id)
        if t is None:
            raise HTTPException(status_code=404, detail="Tutor not found")
        if body.day < now().astimezone(_tz(t)).date():
            raise HTTPException(status_code=422, detail="Pick today or a later day.")
        row = db.get(tm.TutorTimeOff, (tutor_id, body.day)) or tm.TutorTimeOff(tutor_id=tutor_id, day=body.day)
        row.note = body.note.strip()
        db.add(row)
        db.flush()
        tz = _tz(t)
        start = datetime.combine(body.day, time(0), tz)
        booked = sum(1 for b in _tutor_busy(db, tutor_id, start, start + timedelta(days=1))
                     if b["kind"] == "class" and b["start"] >= start)
        return {"daysOff": _time_off_view(db, tutor_id), "bookedThatDay": booked}


@router.delete("/api/tutor/{tutor_id}/time-off/{day}")
def remove_time_off(tutor_id: str, day: date):
    _require_db()
    with session_scope() as db:
        row = db.get(tm.TutorTimeOff, (tutor_id, day))
        if row is not None:
            db.delete(row)
            db.flush()
        return {"daysOff": _time_off_view(db, tutor_id)}


@router.post("/api/portal/cancel/{user_id}/{session_id}")
def cancel(user_id: str, session_id: str):
    """The student cancels a class. Only before it starts; the slot and the request become free again."""
    _require_db()
    with session_scope() as db:
        s = db.get(m.LiveSession, (user_id, session_id))
        if s is None:
            raise HTTPException(status_code=404, detail="Class not found")
        if s.status == "cancelled":
            return {"session": s.data}
        if s.starts_at is not None and _aware(s.starts_at) <= now():
            raise HTTPException(status_code=409, detail="This class has started, so it can't be cancelled. It counts as used.")
        s.status = "cancelled"
        s.data = {**(s.data or {}), "status": "cancelled"}
        from modules.payments import wallet

        topic = (s.data or {}).get("topic", "Your class")
        paid = wallet.class_purchase(db, user_id, session_id)
        rq = wallet.request_cancel_refund(db, paid, "class_cancel", "Live class", topic, s.starts_at)  # the admin decides
        user = db.get(m.User, user_id)
        try:  # tell the student what happens to the money
            from modules.tutor.router import _notify_student

            if rq is not None:
                _notify_student(db, user_id, "session", f"Class cancelled · refund requested ({rq.currency} {rq.amount:g})",
                                f"{topic}: your refund request {rq.id} went to NeuralHub. You get a message when it is approved.",
                                "/student/payments")
            else:
                _notify_student(db, user_id, "session", "Class cancelled", f"{topic}. You can book another time.", "/student/sessions")
        except Exception:  # noqa: BLE001 - the cancel stands either way
            pass
        from modules.tutor.comms import notify_tutor

        notify_tutor(db, s.tutor_id, "cancel", f"{(user.name if user else '') or 'A student'} cancelled a class",
                     (s.data or {}).get("topic", ""), "/tutor/schedule", at=_aware(s.starts_at) if s.starts_at else None)
        out = {"session": s.data}
        if rq is not None:
            out["refund"] = {"id": rq.id, "status": "requested", "amount": rq.amount, "currency": rq.currency,
                             "to": wallet.pay_label(paid)}
        return out


def classes_taken(db, user_id: str) -> set[str]:
    """Session ids the student really had: joined the class room, or the tutor marked it done / wrote a summary."""
    rooms = {r.room: r.session_id for r in db.scalars(select(MeetingRoom).where(MeetingRoom.user_id == user_id))}
    taken: set[str] = set()
    if rooms:
        for a in db.scalars(select(MeetingAttendance).where(MeetingAttendance.room.in_(list(rooms)),
                                                            MeetingAttendance.role == "student",
                                                            MeetingAttendance.person_id == user_id)):
            taken.add(rooms[a.room])
    taken |= set(db.scalars(select(tm.SessionOutcome.session_id).where(tm.SessionOutcome.user_id == user_id,
                                                                      tm.SessionOutcome.outcome == "completed")))
    taken |= set(db.scalars(select(tm.SessionSummary.session_id).where(tm.SessionSummary.user_id == user_id)))
    return taken


def classes_ended(db, user_id: str) -> set[str]:
    """Session ids whose live class was ended (the tutor pressed End, maybe before the booked time)."""
    return set(db.scalars(select(MeetingRoom.session_id).where(MeetingRoom.user_id == user_id, MeetingRoom.status == "ended")))


@router.post("/api/portal/release/{user_id}/{session_id}")
def release(user_id: str, session_id: str):
    """The class time has passed and the student never joined: mark it "missed" so the request can be booked again."""
    _require_db()
    with session_scope() as db:
        s = db.get(m.LiveSession, (user_id, session_id))
        if s is None:
            raise HTTPException(status_code=404, detail="Class not found")
        if s.status == "missed":
            return {"session": s.data}
        if s.status != "scheduled":
            raise HTTPException(status_code=409, detail="Only a booked class can be reset.")
        if s.starts_at is None or _aware(s.starts_at) + timedelta(minutes=int(s.duration_min or SLOT_MIN)) > now():
            raise HTTPException(status_code=409, detail="This class has not ended yet. You can cancel it before it starts instead.")
        if session_id in classes_taken(db, user_id):
            raise HTTPException(status_code=409, detail="You joined this class, so it counts as used. Send the tutor a new request for another class.")
        s.status = "missed"
        s.data = {**(s.data or {}), "status": "missed", "missedAt": now().isoformat()}
        try:
            from modules.tutor.comms import notify_tutor

            user = db.get(m.User, user_id)
            notify_tutor(db, s.tutor_id, "cancel", f"{(user.name if user else '') or 'A student'} missed a class",
                         (s.data or {}).get("topic", ""), "/tutor/schedule", at=_aware(s.starts_at))
        except Exception:  # noqa: BLE001 - the reset stands either way
            pass
        return {"session": s.data}


# ------------------------------------------------------------------ AI booking assistant (Live Sessions)

class AssistIn(BaseModel):
    requestId: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    tz: str = Field(default="", max_length=60)


@router.post("/api/portal/booking-assistant/{user_id}")
def booking_assistant(user_id: str, body: AssistIn):
    """The student asks about free times in plain words; the answer is built from the live slots (never booked here)."""
    from . import booking_ai

    _require_db()
    with session_scope() as db:
        r = _accepted_request(db, user_id, body.requestId)
        t = db.get(tm.Tutor, r.tutor_id)
        if t is None:
            raise HTTPException(status_code=404, detail="Tutor not found")

        def take():
            from modules.settings import store, usage

            try:
                limit = store.get("limits.aiQuestionsPerDay")
                allowed, _ = usage.take(user_id, "ai_question", limit)
            except Exception:  # noqa: BLE001 - no limits configured
                return
            if not allowed:
                raise HTTPException(status_code=429, detail=f"You have used today's {limit} AI questions. They come back tomorrow.")

        return {**booking_ai.answer(db, t, user_id, body.message, body.tz, take_ai=take), "tutorName": t.name}
