"use client";

/**
 * Pick a one-hour slot of the tutor (next 2 weeks) and book it. Taken slots are shown but cannot be chosen.
 * The server checks the slot again when booking, so a slot someone else took a second earlier is refused cleanly.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CalendarCheck, ChevronDown, Loader2, RefreshCw } from "lucide-react";
import { ApiError } from "@/lib/api";
import { bookingApi, dayParts, timeLabel, type PayDetails, type Slot, type SlotDay } from "@/lib/booking";
import CheckoutDialog from "@/components/shared/CheckoutDialog";
import type { LiveSession } from "@/types/portal";

const NOTE: Record<string, string> = {
  booked: "Taken",
  group: "Group class",
  mine: "Your class",
  busy: "You're busy",
  past: "Too close to book",
  off: "Day off",
};

const fmtPrice = (n: number, cur: string) => {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: cur, minimumFractionDigits: n % 1 ? 2 : 0, maximumFractionDigits: 2 }).format(n);
  } catch {
    return `${cur} ${Math.round(n)}`;
  }
};

export default function SlotPicker({ tutorId, tutorName, userId, requestId, onBooked }: {
  tutorId: string;
  tutorName: string;
  userId: string;
  requestId: string;
  onBooked: (s: LiveSession) => void;
}) {
  const [days, setDays] = useState<SlotDay[] | null>(null);
  const [day, setDay] = useState("");
  const [pick, setPick] = useState<Slot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [price, setPrice] = useState<{ amount: number; currency: string; mode: string } | null>(null);
  const chose = useRef(false); // the student clicked a day himself
  const [checkout, setCheckout] = useState(false);
  const bookRef = useRef<HTMLButtonElement>(null);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const r = await bookingApi.slots(tutorId, userId, 14);
      setDays(r.days);
      setPrice(r.price ? { amount: r.price, currency: r.currency || "USD", mode: r.payMode || "test" } : null);
      const firstFree = r.days.find((x) => x.slots.some((s) => s.state === "free"))?.date || r.days[0]?.date || "";
      setDay((d) => {
        const still = r.days.find((x) => x.date === d)?.slots.some((s) => s.state === "free");
        return d && (still || chose.current) ? d : firstFree;
      });
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Could not load the tutor's free times.");
    }
  }, [tutorId, userId]);

  useEffect(() => {
    setDays(null);
    setDay("");
    setPick(null);
    chose.current = false;
    void load();
  }, [load]);
  // someone else may book while the page is open
  useEffect(() => {
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    const t = window.setInterval(onFocus, 30000); // real time enough: slots others book, times that pass
    return () => {
      window.removeEventListener("focus", onFocus);
      window.clearInterval(t);
    };
  }, [load]);

  const current = useMemo(() => days?.find((d) => d.date === day), [days, day]);
  useEffect(() => {
    if (pick && !current?.slots.some((s) => s.start === pick.start && s.state === "free")) setPick(null);
  }, [current, pick]);

  /** Free class: book at once. Paid class: the checkout collects the payment details and calls this with them. */
  const book = async (payment?: PayDetails) => {
    if (!pick) return;
    setBusy(true);
    setError("");
    try {
      const { session } = await bookingApi.book(userId, requestId, pick.start, payment);
      setCheckout(false);
      onBooked(session);
      setPick(null);
      await load();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Could not book. Please try again.";
      await load();
      if (payment && e instanceof ApiError && e.status === 422) throw new Error(msg); // a payment detail: fix it in the checkout
      setCheckout(false);
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  if (loadError)
    return (
      <div className="mt-4 rounded-xl bg-[#fce8e6] px-4 py-3 text-sm text-[#c5221f]" role="alert">
        {loadError}{" "}
        <button type="button" onClick={() => void load()} className="font-semibold underline">Try again</button>
      </div>
    );
  if (!days)
    return <p className="mt-4 flex items-center gap-2 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" /> Loading free times…</p>;

  const first = tutorName.replace("Dr. ", "").split(" ")[0];
  const anyFree = days.some((d) => d.slots.some((s) => s.state === "free"));
  const nextFree = days.flatMap((d) => d.slots.filter((s) => s.state === "free").map((s) => ({ d, s })))[0];
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const choose = (date: string) => {
    chose.current = true;
    setDay(date);
  };
  const allSlots = current?.slots ?? [];
  const shown = showAll ? allSlots : allSlots.slice(0, 8);
  const label = "text-[11.5px] font-extrabold tracking-[.06em] text-[#A8653F]";

  return (
    <div className="mt-3 flex flex-col gap-3" data-testid="slot-picker">
      {/* 1 · day */}
      <div className="flex items-center justify-between">
        <span className={label}>1 · PICK A DAY</span>
        <span className="flex items-center gap-3 text-[11.5px] text-[#6B7280]">
          Next 2 weeks · your time ({tz})
          <button type="button" onClick={() => void load()} className="inline-flex items-center gap-1 text-[#A8653F] hover:text-[#7A4527]" aria-label="Refresh free times">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </span>
      </div>
      <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1" role="tablist">
        {days.map((d) => {
          const p = dayParts(d.date);
          const free = d.slots.filter((s) => s.state === "free").length;
          const sel = d.date === day;
          const note = d.off ? "Off" : d.closed ? "Done" : !d.slots.length ? "No class" : free ? `${free} free` : "Full";
          return (
            <button
              key={d.date}
              type="button"
              role="tab"
              aria-selected={sel}
              onClick={() => { choose(d.date); setShowAll(false); }}
              data-testid="slot-day"
              className={`flex h-[70px] w-[72px] shrink-0 flex-col items-center justify-center rounded-2xl border text-center transition ${
                sel ? "border-transparent bg-[linear-gradient(160deg,#B06D45,#8E5233)] text-white shadow-[0_10px_20px_-12px_rgba(90,50,30,.8)]"
                  : free ? "border-[#EFE0D0] bg-white text-[#1E2A38] hover:border-[#C9A27A]" : "border-[#EFEBE6] bg-[#F7F5F2] text-[#A9A39C]"
              }`}
            >
              <span className="text-[10.5px] font-bold uppercase tracking-[.06em] opacity-80">{p.weekday}</span>
              <span className="text-[19px] font-bold leading-tight">{p.day}</span>
              <span className={`text-[10.5px] font-bold ${sel ? "text-[#FDEEDD]" : free ? "text-[#A8653F]" : "text-[#B3ADA6]"}`}>{note}</span>
            </button>
          );
        })}
      </div>

      {/* 2 · time */}
      {current ? (
        <div className="flex flex-col gap-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className={label}>2 · PICK A TIME <span className="font-semibold tracking-normal text-[#6B7280]">on {dayParts(current.date).long}</span></span>
            <span className="flex gap-3 text-[11.5px] text-[#6B7280]">
              <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-[3px] border-[1.5px] border-[#D9C3AE] bg-white" />Free</span>
              <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-[3px] bg-[#F3F1EE]" />Taken</span>
            </span>
          </div>
          {current.off ? (
            <p className="rounded-xl bg-[#F7F5F2] px-4 py-3 text-sm text-[#6B7280]">{first} is not teaching on this day{current.note ? ` (${current.note})` : ""}.</p>
          ) : current.closed ? (
            <p className="rounded-xl bg-[#F7F5F2] px-4 py-3 text-sm text-[#6B7280]" data-testid="day-closed">
              No times left today (classes are booked at least 1 hour before they start).
              {nextFree ? <> Next free: <button type="button" className="font-semibold text-[#7A4527] underline" onClick={() => choose(nextFree.d.date)}>{dayParts(nextFree.d.date).long}</button></> : null}
            </p>
          ) : !current.slots.length ? (
            <p className="rounded-xl bg-[#F7F5F2] px-4 py-3 text-sm text-[#6B7280]">{first} does not teach on {dayParts(current.date).weekday}s.</p>
          ) : (
            <>
              {!current.slots.some((x) => x.state === "free") ? (
                <p className="text-xs text-[#6B7280]" data-testid="day-full">Every time on this day is taken. Please pick another day.</p>
              ) : null}
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Free times">
                {shown.map((s) => {
                  const free = s.state === "free";
                  const sel = pick?.start === s.start;
                  return (
                    <button
                      key={s.start}
                      type="button"
                      role="radio"
                      aria-checked={sel}
                      disabled={!free}
                      onClick={() => setPick(s)}
                      data-testid="slot"
                      data-state={s.state}
                      className={`flex h-[50px] flex-col items-start justify-center rounded-[13px] border px-3 text-left transition ${
                        sel ? "border-transparent bg-[linear-gradient(160deg,#B06D45,#8E5233)] text-white shadow-[0_10px_20px_-12px_rgba(90,50,30,.8)]"
                          : free ? "border-[#E8D5C2] bg-white text-[#1E2A38] hover:border-[#A8653F] hover:bg-[#FFFBF6]"
                            : s.state === "mine" ? "cursor-default border-[#E8D5C2] bg-[#FBF3EA] text-[#7A4527]"
                              : "cursor-not-allowed border-[#EFEBE6] bg-[#F3F1EE] text-[#A9A39C]"
                      }`}
                    >
                      <span className={`text-[15px] font-bold ${!free && s.state !== "mine" ? "line-through decoration-1" : ""}`}>{timeLabel(s.start)}</span>
                      <span className="text-[11px] opacity-80">{free ? `to ${timeLabel(s.end)}` : NOTE[s.state]}</span>
                    </button>
                  );
                })}
              </div>
              {allSlots.length > 8 ? (
                <button type="button" onClick={() => setShowAll((v) => !v)} aria-expanded={showAll} data-testid="more-times"
                  className="inline-flex items-center gap-1.5 self-center rounded-full border border-dashed border-[#D9C3AE] bg-[#FFFBF6] px-3.5 py-1.5 text-[12.5px] font-bold text-[#7A4527] hover:bg-[#FBF3EA]">
                  {showAll ? "Fewer times" : `More times (${allSlots.length - 8})`}
                  <ChevronDown className={`h-3.5 w-3.5 transition ${showAll ? "rotate-180" : ""}`} />
                </button>
              ) : null}
            </>
          )}
        </div>
      ) : null}

      {!anyFree ? <p className="text-xs text-[#6B7280]">No free times in the next 2 weeks. Ask {first} in Messages.</p> : null}
      {error ? <p className="rounded-xl bg-[#fce8e6] px-4 py-2.5 text-sm text-[#c5221f]" role="alert" data-testid="book-error">{error}</p> : null}

      {/* 3 · book */}
      <div className="flex flex-col gap-3 rounded-2xl border border-[#F1E2D2] bg-[#FBF3EA] px-3.5 py-2.5 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1 text-[12px] text-[#6B7280]">
          <p className="truncate text-[14px] font-bold text-[#1E2A38]">
            {pick ? <>{dayParts(current?.date ?? "").long} · {timeLabel(pick.start)} – {timeLabel(pick.end)}</> : "Pick a time above"}
          </p>
          <p data-testid="class-price">
            {price ? <>Price <b className="text-[#1E2A38]">{fmtPrice(price.amount, price.currency)}</b>{price.mode === "test" ? " · test payment, no real money" : ""} · cancel before it starts for a refund</> : "Every class is 1 hour; you can cancel until it starts."}
          </p>
        </div>
        <button
          ref={bookRef}
          type="button"
          onClick={() => (price ? setCheckout(true) : void book())}
          disabled={!pick || busy}
          className="inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-xl bg-[linear-gradient(90deg,#B06D45,#8E5233)] px-5 py-2.5 text-sm font-bold text-white shadow-[0_8px_18px_-10px_rgba(90,50,30,.8)] transition hover:brightness-110 disabled:opacity-45"
          data-testid="book-slot"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarCheck className="h-4 w-4" />}
          {busy ? "Booking…" : price ? "Pay & book" : "Book this class"}
        </button>
      </div>
      {checkout && pick && price ? (
        <CheckoutDialog
          summary={{ title: "Live class", tutor: tutorName, when: `${dayParts(current?.date ?? "").long}, ${timeLabel(pick.start)} – ${timeLabel(pick.end)}`, length: "1 hour" }}
          amount={fmtPrice(price.amount, price.currency)}
          testMode={price.mode === "test"}
          onPay={(p) => book(p)}
          onClose={() => setCheckout(false)}
        />
      ) : null}
    </div>
  );
}
