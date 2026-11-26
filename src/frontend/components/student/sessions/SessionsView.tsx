"use client";
import BookingReceipt from "./BookingReceipt";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlarmClockOff, CalendarCheck2, CalendarPlus, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, Clock, History, Loader2, RotateCcw, Send, Video, X } from "lucide-react";
import PageHeader from "@/components/student/shared/PageHeader";
import { ROUTES } from "@/lib/routes";
import { meetHref } from "@/lib/meet";
import CopyLinkButton from "@/components/meet/CopyLinkButton";
import { usePortal } from "@/lib/store/portal-store";
import { classOfRequest } from "@/lib/class-credit";
import { dayKey, formatDateTime } from "@/lib/utils";
import type { LiveSession } from "@/types/portal";
import { useSession } from "@/lib/auth/local-auth";
import { commsApi, type Rating } from "@/lib/tutor/api";
import RateSession from "./RateSession";
import SlotPicker from "./SlotPicker";
import CancelDialog from "./CancelDialog";
import { bookingApi } from "@/lib/booking";
import { ApiError } from "@/lib/api";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const inputClass =
  "w-full rounded-xl border border-[#EFE6DA] bg-white px-3 py-2.5 text-sm text-ink transition focus:border-[#B07A55] focus:outline-none focus:ring-4 focus:ring-[#B07A55]/15";

function downloadIcs(s: LiveSession) {
  const fmt = (d: Date) => d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const start = new Date(s.startsAt);
  const end = new Date(start.getTime() + s.durationMin * 60000);
  const ics = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//NeuralHub//Sessions//EN",
    "BEGIN:VEVENT",
    `UID:${s.id}@neuralhub`,
    `DTSTAMP:${fmt(new Date())}`,
    `DTSTART:${fmt(start)}`,
    `DTEND:${fmt(end)}`,
    `SUMMARY:Neural Hub Institute session: ${s.topic}`,
    `DESCRIPTION:With ${s.tutorName}. Join: ${window.location.origin}${meetHref(s.id)}`,
    `URL:${window.location.origin}${meetHref(s.id)}`,
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");
  const url = URL.createObjectURL(new Blob([ics], { type: "text/calendar" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `neuralhub-session-${dayKey(start)}.ics`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function SessionsView({ requestId }: { requestId?: string }) {
  const { state, actions } = usePortal();
  const accepted = state.requests.filter((r) => r.status === "accepted");

  // one accepted request = one class; cancelling the class frees the request again
  const booked = useMemo(() => classOfRequest(state.requests, state.sessions), [state.requests, state.sessions]);
  const [chosenRequest, setChosenRequest] = useState(requestId ?? "");
  const request = accepted.find((r) => r.id === chosenRequest) ?? accepted.find((r) => !booked[r.id]) ?? accepted[0];
  const usedBy = request ? booked[request.id] ?? null : null;
  const [justScheduled, setJustScheduled] = useState(false);
  const [openHist, setOpenHist] = useState<string | null>(null);
  const [allHistory, setAllHistory] = useState(false);
  const [allUpcoming, setAllUpcoming] = useState(false);

  const [month, setMonth] = useState(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  const { session } = useSession();
  const userId = session?.userId ?? "";
  const [ratings, setRatings] = useState<Record<string, Rating>>({});
  useEffect(() => {
    if (!userId) return;
    commsApi
      .myRatings(userId)
      .then(({ ratings }) => setRatings(Object.fromEntries(ratings.map((r) => [r.sessionId, r]))))
      .catch(() => {});
  }, [userId]);

  const now = new Date();
  // a class the tutor ended (even before its booked time) or wrapped up is over: it leaves "upcoming"
  const active = state.sessions.filter((s) => s.status === "scheduled" && !s.ended);
  const upcoming = active
    .filter((s) => !s.tutorSummary && new Date(s.startsAt).getTime() + s.durationMin * 60000 > now.getTime())
    .sort((a, b) => a.startsAt.localeCompare(b.startsAt));
  const history = state.sessions
    // a session the tutor already wrapped up counts as done, even if it ended early
    .filter((s) => s.status !== "scheduled" || !!s.ended || !!s.tutorSummary || new Date(s.startsAt).getTime() + s.durationMin * 60000 <= now.getTime())
    .sort((a, b) => b.startsAt.localeCompare(a.startsAt));

  const byDay = useMemo(() => {
    const map: Record<string, LiveSession[]> = {};
    active.forEach((s) => {
      const k = dayKey(new Date(s.startsAt));
      (map[k] = map[k] ?? []).push(s);
    });
    return map;
  }, [active]);

  const [cancelling, setCancelling] = useState("");
  const [cancelError, setCancelError] = useState("");
  const [cancelAsk, setCancelAsk] = useState<LiveSession | null>(null);
  const [cancelDone, setCancelDone] = useState("");
  const cancel = async (s: LiveSession) => {
    setCancelling(s.id);
    setCancelError("");
    setCancelDone("");
    try {
      const r = await bookingApi.cancel(userId, s.id);
      actions.cancelSession(s.id);
      setJustScheduled(false);
      setCancelDone(r.refund
        ? `Class cancelled. Refund request ${r.refund.id ?? ""} for ${new Intl.NumberFormat("en-US", { style: "currency", currency: r.refund.currency, minimumFractionDigits: r.refund.amount % 1 ? 2 : 0, maximumFractionDigits: 2 }).format(r.refund.amount)} sent to Neural Hub Institute; once approved it goes back to your ${r.refund.to}.`
        : "Class cancelled. The time is free again and you can book another one.");
    } catch (e) {
      // 404: a class that only exists in this browser (never reached the server)
      if (e instanceof ApiError && e.status === 404) actions.cancelSession(s.id);
      else setCancelError(e instanceof ApiError ? e.message : "Could not cancel. Please try again.");
    } finally {
      setCancelling("");
      setCancelAsk(null);
    }
  };

  const [resetting, setResetting] = useState(false);
  const [resetError, setResetError] = useState("");
  const resetClass = async (s: LiveSession) => {
    setResetting(true);
    setResetError("");
    try {
      await bookingApi.release(userId, s.id);
      actions.markSessionMissed(s.id);
      setJustScheduled(false);
    } catch (e) {
      setResetError(e instanceof ApiError ? e.message : "Could not reset. Please try again.");
    } finally {
      setResetting(false);
    }
  };

  const onBooked = (s: LiveSession) => {
    actions.addBookedSession(s);
    if (request) setChosenRequest(request.id);
    setJustScheduled(true);
    const start = new Date(s.startsAt);
    setMonth(new Date(start.getFullYear(), start.getMonth(), 1));
  };

  // Month grid (weeks start on Monday)
  const firstWeekday = (month.getDay() + 6) % 7;
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells: (Date | null)[] = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => new Date(month.getFullYear(), month.getMonth(), i + 1)),
  ];
  const listed = selectedDay ? upcoming.filter((s) => dayKey(new Date(s.startsAt)) === selectedDay) : upcoming;

  const tutorFirst = (n: string) => n.replace("Dr. ", "").split(" ")[0];
  const SHOW = 2; // History and Upcoming show two classes, "See more" opens the rest
  const card = "rounded-[22px] border border-[#EFE6DA] bg-white shadow-[0_1px_2px_rgba(60,40,20,.04),0_14px_34px_-24px_rgba(60,40,20,.35)]";
  const moreBtn = (n: number, open: boolean, toggle: () => void, id: string) =>
    n > SHOW ? (
      <button type="button" onClick={toggle} aria-expanded={open} data-testid={id}
        className="mx-auto mt-1 inline-flex items-center gap-1.5 rounded-full border border-dashed border-[#D9C3AE] bg-[#FFFBF6] px-3.5 py-1.5 text-[12.5px] font-bold text-[#7A4527] hover:bg-[#FBF3EA]">
        {open ? "See less" : `See more (${n - SHOW})`}
        <ChevronDown className={`h-3.5 w-3.5 transition ${open ? "rotate-180" : ""}`} />
      </button>
    ) : null;
  const mon = (iso: string) => new Date(iso).toLocaleDateString("en-US", { month: "short" }).toUpperCase();
  const dnum = (iso: string) => new Date(iso).getDate();
  const listedShown = allUpcoming ? listed : listed.slice(0, SHOW);
  const historyShown = allHistory ? history : history.slice(0, SHOW);

  return (
    <div className="space-y-5">
      <PageHeader title="Live Sessions" subtitle="Book time with tutors who accepted your request." />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        {/* ===== Schedule a session ===== */}
        <section className={`${card} flex min-w-0 flex-col overflow-hidden`}>
          <div className="relative flex items-center gap-3 overflow-hidden border-b border-[#F1E7DB] bg-[linear-gradient(150deg,#FBF3EA,#FFFBF6)] px-5 py-3.5">
            <svg viewBox="0 0 200 120" className="pointer-events-none absolute -right-5 -top-8 h-28 w-48" aria-hidden><g fill="none" stroke="#A8653F" strokeOpacity=".14"><circle cx="150" cy="40" r="34" /><circle cx="150" cy="40" r="58" /></g></svg>
            <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-[14px] bg-[linear-gradient(150deg,#B06D45,#8E5233)] text-white shadow-[0_8px_18px_-10px_rgba(90,50,30,.8)]"><CalendarCheck2 className="h-5 w-5" /></span>
            <span className="relative min-w-0 flex-1">
              <span className="block text-[19px] font-semibold tracking-[-0.01em] text-[#1E2A38]">Schedule a session</span>
              <span className="block truncate text-[13px] text-[#6B7280]">
                {request ? <>with <b className="text-[#7A4527]">{request.tutorName}</b> · {request.studySetTopic}</> : "Sessions open up once a tutor accepts your request."}
              </span>
            </span>
            {request ? (
              <span className="relative hidden shrink-0 items-center gap-1.5 rounded-full border border-[#E8D5C2] bg-white px-3 py-1.5 text-[12px] font-bold text-[#7A4527] sm:inline-flex">
                <Clock className="h-3.5 w-3.5" /> {usedBy ? "Class booked" : "1 class to book · 1 hour"}
              </span>
            ) : null}
          </div>
          <div className="flex-1 px-5 pb-4">
            {accepted.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-8 text-center">
                <p className="text-sm text-[#6B7280]">Once a tutor accepts your request, you can pick a time here.</p>
                <Link href={ROUTES.student.tutors} className="inline-flex items-center gap-1.5 rounded-xl bg-[linear-gradient(90deg,#B06D45,#8E5233)] px-4 py-2 text-sm font-semibold text-white"><Send className="h-4 w-4" /> Find a tutor</Link>
              </div>
            ) : justScheduled && usedBy ? (
              <BookingReceipt session={usedBy} />
            ) : request ? (
              <>
                {accepted.length > 1 ? (
                  <p className="mt-3 text-[12px] text-[#6B7280]">Booking for this request. To book another one, open it from <Link href={ROUTES.student.requests} className="font-semibold text-[#7A4527] underline">My Requests</Link>.</p>
                ) : null}
                {usedBy ? (
                  <ClassStatus s={usedBy} tutorId={request.tutorId} tutorFirst={tutorFirst(request.tutorName)} now={now} resetting={resetting} error={resetError} onReset={() => resetClass(usedBy)} />
                ) : userId ? (
                  <SlotPicker key={request.id} tutorId={request.tutorId} tutorName={request.tutorName} userId={userId} requestId={request.id} onBooked={onBooked} />
                ) : null}
              </>
            ) : null}
          </div>
        </section>

        {/* ===== Calendar ===== */}
        <section className={`${card} flex flex-col p-4`}>
          <div className="mb-2 flex items-center justify-between">
            <button onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))} aria-label="Previous month" className="rounded-full p-1.5 text-[#A8653F] hover:bg-[#FBF3EA]">
              <ChevronLeft className="h-4 w-4" />
            </button>
            <p className="font-display text-lg text-ink">{month.toLocaleDateString("en-US", { month: "long", year: "numeric" })}</p>
            <button onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))} aria-label="Next month" className="rounded-full p-1.5 text-[#A8653F] hover:bg-[#FBF3EA]">
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          <div className="grid flex-1 grid-cols-7 content-start gap-1 text-center text-[11px] text-muted">
            {WEEKDAYS.map((d) => <div key={d} className="py-1 font-semibold">{d}</div>)}
            {cells.map((d, i) => {
              if (!d) return <div key={`e${i}`} />;
              const k = dayKey(d);
              const count = byDay[k]?.length ?? 0;
              const isToday = k === dayKey(now);
              const selected = k === selectedDay;
              return (
                <button
                  key={k}
                  onClick={() => setSelectedDay(count ? (selected ? null : k) : null)}
                  aria-label={`${d.toDateString()}${count ? `, ${count} session${count > 1 ? "s" : ""}` : ""}`}
                  className={`relative flex h-9 flex-col items-center justify-center rounded-lg text-sm transition ${
                    selected ? "bg-[#A8653F] text-white" : count ? "bg-[#FDEEDD] text-ink hover:bg-[#F6DFC6]" : "text-ink hover:bg-[#FBF3EA]"
                  } ${isToday && !selected ? "font-bold text-[#7A4527] ring-1 ring-[#A8653F]" : ""}`}
                >
                  {d.getDate()}
                  {count > 0 && <span className={`absolute bottom-1 h-1 w-1 rounded-full ${selected ? "bg-white" : "bg-[#A8653F]"}`} />}
                </button>
              );
            })}
          </div>
          <p className="mt-2 text-xs text-muted">Highlighted days have classes. Click one to filter.</p>
        </section>

        {/* ===== Upcoming (under Schedule, wide) ===== */}
        <section className={`${card} flex min-w-0 flex-col self-start overflow-hidden`} data-testid="upcoming">
          <div className="flex items-center gap-2 border-b border-[#F1E7DB] px-4 py-3">
            <span className="flex-1 text-[17px] font-semibold text-[#1E2A38]">
              {selectedDay ? `Classes on ${new Date(selectedDay + "T12:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}` : "Upcoming"}
            </span>
            {selectedDay ? <button onClick={() => setSelectedDay(null)} className="text-xs font-semibold text-[#7A4527] hover:underline">Show all</button> : null}
            <span className="rounded-full bg-[#FBF3EA] px-2 py-0.5 text-[12px] font-bold text-[#7A4527]">{listed.length}</span>
          </div>
          <div className="flex flex-col gap-1.5 p-2.5">
            {cancelError ? <p className="rounded-xl bg-[#fce8e6] px-3 py-2 text-xs text-[#c5221f]" role="alert">{cancelError}</p> : null}
            {cancelDone ? <p className="rounded-xl border border-[#E8D5C2] bg-[#FBF3EA] px-3 py-2 text-xs text-[#1E2A38]" data-testid="cancel-done">{cancelDone}</p> : null}
            {cancelAsk ? <CancelDialog s={cancelAsk} onConfirm={() => cancel(cancelAsk)} onClose={() => setCancelAsk(null)} /> : null}
            {listed.length === 0 ? (
              <p className="rounded-xl border border-dashed border-[#E3D3C1] bg-[#FFFBF6] px-3 py-4 text-center text-[13px] text-[#6B7280]">No upcoming classes.</p>
            ) : listedShown.map((s) => {
              const start = new Date(s.startsAt).getTime();
              const live = now.getTime() >= start - 10 * 60000;
              return (
                <div key={s.id} className="rounded-2xl border border-[#F1E7DB] bg-white">
                  <div className="flex flex-wrap items-center gap-2.5 px-2.5 py-2">
                    <span className="flex w-11 shrink-0 flex-col overflow-hidden rounded-[10px] border border-[#E8D5C2] bg-white text-center">
                      <span className="bg-[linear-gradient(90deg,#B06D45,#8E5233)] py-px text-[9.5px] font-extrabold tracking-[.08em] text-white">{mon(s.startsAt)}</span>
                      <span className="text-[17px] font-bold leading-[1.35] text-[#1E2A38]">{dnum(s.startsAt)}</span>
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13.5px] font-semibold text-[#1E2A38]">{s.topic}</span>
                      <span className="block truncate text-[11.5px] text-[#6B7280]">{s.tutorName} · {new Date(s.startsAt).toLocaleTimeString([], { weekday: "short", hour: "numeric", minute: "2-digit" })} · {s.durationMin} min</span>
                    </span>
                    {live ? <span className="shrink-0 rounded-full bg-[#A8653F] px-2 py-0.5 text-[10.5px] font-bold text-white">Now</span> : null}
                    <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
                      <Link href={meetHref(s.id)} className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-[12px] font-semibold ${live ? "bg-[linear-gradient(90deg,#B06D45,#8E5233)] text-white" : "bg-[linear-gradient(90deg,#B06D45,#8E5233)] text-white opacity-90"}`}>
                        <Video className="h-3.5 w-3.5" /> {live ? "Join now" : "Class room"}
                      </Link>
                      <button onClick={() => downloadIcs(s)} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-[#E8D5C2] bg-white px-2.5 text-[12px] font-medium text-[#7A4527] hover:bg-[#FBF3EA]">
                        <CalendarPlus className="h-3.5 w-3.5" /> Add to calendar
                      </button>
                      {session ? (
                        <CopyLinkButton who={{ role: "student", userId: session.userId }} sessionId={s.id} className="inline-flex h-8 items-center rounded-lg border border-[#E8D5C2] bg-white px-2.5 text-[12px] font-medium text-[#7A4527] hover:bg-[#FBF3EA]" />
                      ) : null}
                      {now.getTime() < start ? (
                        <button onClick={() => setCancelAsk(s)} disabled={cancelling === s.id} className="inline-flex h-8 items-center gap-1 rounded-lg px-2 text-[12px] font-medium text-[#6B7280] hover:bg-[#F3F1EE]" aria-label={`Cancel session on ${formatDateTime(s.startsAt)}`}>
                          <X className="h-3.5 w-3.5" /> Cancel
                        </button>
                      ) : null}
                    </div>
                  </div>
                </div>
              );
            })}
            {moreBtn(listed.length, allUpcoming, () => setAllUpcoming((v) => !v), "upcoming-more")}
          </div>
        </section>
        {/* ===== History (under the calendar) ===== */}
        <section className={`${card} flex min-w-0 flex-col self-start overflow-hidden`} data-testid="history">
          <div className="flex items-center gap-3 border-b border-[#F1E7DB] px-5 py-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#FBF3EA] text-[#A8653F]"><History className="h-[18px] w-[18px]" /></span>
            <span className="min-w-0 flex-1">
              <span className="block text-[17px] font-semibold text-[#1E2A38]">History</span>
              <span className="block text-[12px] text-[#6B7280]">{history.length ? `${history.length} past class${history.length > 1 ? "es" : ""} · tap one to see the notes` : "Your past classes show here."}</span>
            </span>
          </div>
          <div className="flex flex-col gap-1.5 p-2.5">
            {history.length === 0 ? (
              <p className="rounded-xl border border-dashed border-[#E3D3C1] bg-[#FFFBF6] px-3 py-4 text-center text-[13px] text-[#6B7280]">No past classes yet.</p>
            ) : historyShown.map((s) => {
              const open = openHist === s.id;
              const done = s.status === "scheduled";
              const chip = s.status === "cancelled" ? ["Cancelled", "bg-[#F3F1EE] text-[#6B6560]"] : s.status === "missed" ? ["Missed", "bg-[#FDEEDD] text-[#9A4F12]"] : ["Completed", "bg-[#F6EAE2] text-[#7A4527]"];
              return (
                <div key={s.id} className={`rounded-2xl border ${open ? "border-[#E8D5C2] bg-[#FFFBF6]" : "border-[#F1E7DB] bg-white"}`}>
                  <button type="button" onClick={() => setOpenHist(open ? null : s.id)} aria-expanded={open} className="flex w-full items-center gap-2.5 px-3 py-2 text-left">
                    <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] text-[12px] font-bold ${done ? "bg-[#F6EAE2] text-[#7A4527]" : "bg-[#F3F1EE] text-[#8F8984]"}`}>
                      {s.tutorName.split(" ").filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase()}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-semibold text-[#1E2A38]">{s.topic}</span>
                      <span className="block truncate text-[12px] text-[#6B7280]">{s.tutorName} · {formatDateTime(s.startsAt)}</span>
                    </span>
                    <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${chip[1]}`}>{chip[0]}</span>
                    <ChevronDown className={`h-4 w-4 shrink-0 text-[#A8653F] transition ${open ? "rotate-180" : ""}`} />
                  </button>
                  {open ? (
                    <div className="space-y-2 px-3 pb-3 pl-[58px] text-[13px] text-[#4B5563]">
                      {s.tutorSummary ? (
                        <>
                          <p>{s.tutorSummary.summary}</p>
                          {s.tutorSummary.homework.length > 0 ? <p><b className="text-[#1E2A38]">Homework:</b> {s.tutorSummary.homework.join(" · ")}</p> : null}
                          {s.tutorSummary.nextFocus ? <p className="text-xs text-[#6B7280]">Next time: {s.tutorSummary.nextFocus}</p> : null}
                        </>
                      ) : (
                        <p className="text-[#6B7280]">{s.status === "cancelled" ? "This class was cancelled." : s.status === "missed" ? "You did not join this class." : "No notes from the teacher yet."}</p>
                      )}
                      {s.status === "scheduled" && userId ? (
                        <RateSession userId={userId} sessionId={s.id} tutorName={s.tutorName} rating={ratings[s.id]} onSaved={(r) => setRatings((m) => ({ ...m, [s.id]: r }))} />
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
            {moreBtn(history.length, allHistory, () => setAllHistory((v) => !v), "history-more")}
          </div>
        </section>

      </div>
    </div>
  );
}

/** What happened to the class booked with this request: booked, done, or time passed without joining. */
function ClassStatus({
  s, tutorId, tutorFirst, now, resetting, error, onReset,
}: {
  s: LiveSession; tutorId: string; tutorFirst: string; now: Date; resetting: boolean; error: string; onReset: () => void;
}) {
  const start = new Date(s.startsAt).getTime();
  const ended = start + (Number(s.durationMin) || 60) * 60000 <= now.getTime();
  const taken = !!s.taken || !!s.tutorSummary;
  const newRequest = (
    <Link href={ROUTES.student.tutor(tutorId)} data-testid="send-new-request" className="inline-flex items-center gap-1.5 rounded-full border border-[#E8D5C2] bg-white px-4 py-2 text-xs font-semibold text-[#1E2A38] transition hover:bg-[#FBF3EA]">
      <Send className="h-3.5 w-3.5" /> Send {tutorFirst} a new request
    </Link>
  );

  if (!ended) {
    const live = now.getTime() >= start - 10 * 60000;
    return (
      <div className="mt-4 rounded-2xl border border-[#E8D5C2] bg-[linear-gradient(180deg,#FBF3EA,#FFFFFF)] p-4" data-testid="request-used">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#A8653F] text-white"><CalendarCheck2 className="h-5 w-5" /></span>
          <div className="min-w-0 flex-1">
            <p className="text-[15px] font-semibold text-[#1E2A38]">Your class is booked</p>
            <p className="mt-0.5 text-[13px] text-[#4B5563]">{formatDateTime(s.startsAt)} · {s.durationMin} min with {tutorFirst}</p>
            <p className="mt-1 text-xs text-[#6B756E]">One request gives one class. Cancel it before it starts if you need another time.</p>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 pl-[52px]">
          <Link href={meetHref(s.id)} className={`inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold transition ${live ? "bg-[linear-gradient(90deg,#B06D45,#8E5233)] text-white" : "border border-[#E8D5C2] bg-white text-[#2B3644] hover:bg-[#FBF3EA]"}`}>
            <Video className="h-3.5 w-3.5" /> {live ? "Join now" : "Class room"}
          </Link>
        </div>
      </div>
    );
  }

  if (taken) {
    return (
      <div className="mt-4 rounded-2xl border border-[#E8D5C2] bg-[linear-gradient(180deg,#FBF3EA,#FFFFFF)] p-4" data-testid="request-used">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#A8653F] text-white"><CheckCircle2 className="h-5 w-5" /></span>
          <div className="min-w-0 flex-1">
            <p className="text-[15px] font-semibold text-[#1E2A38]">Class done · this request is finished</p>
            <p className="mt-0.5 text-[13px] text-[#4B5563]">You had your class on {formatDateTime(s.startsAt)}. For another class, send {tutorFirst} a new request.</p>
          </div>
        </div>
        <div className="mt-3 pl-[52px]">{newRequest}</div>
      </div>
    );
  }

  return (
    <div className="mt-4 rounded-2xl border border-[#F3D9C6] bg-[linear-gradient(180deg,#FDF4EC,#FFFFFF)] p-4" data-testid="request-used">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#E8893A] text-white"><AlarmClockOff className="h-5 w-5" /></span>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold text-[#1E2A38]">The class time has passed</p>
          <p className="mt-0.5 text-[13px] text-[#4B5563]">{formatDateTime(s.startsAt)} with {tutorFirst}. You did not join this class.</p>
          <p className="mt-1 text-xs text-[#6B756E]">Reset it to free this request and book a new time.</p>
        </div>
      </div>
      {error && <p className="mt-3 rounded-xl bg-[#fce8e6] px-3 py-2 text-xs text-[#c5221f]" role="alert">{error}</p>}
      <div className="mt-3 flex flex-wrap gap-2 pl-[52px]">
        <button type="button" onClick={onReset} disabled={resetting} data-testid="reset-class" className="inline-flex items-center gap-1.5 rounded-full bg-[#E8893A] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#C9672B] disabled:opacity-60">
          {resetting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />} Reset and book again
        </button>
        {newRequest}
      </div>
    </div>
  );
}
