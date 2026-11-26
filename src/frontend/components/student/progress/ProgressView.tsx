"use client";

/**
 * Student → Progress. One screen, everything real and live:
 *   study time  = minutes on learning pages (StudyTimer, saved in the portal state) + minutes in live classes (Meet joins)
 *   quizzes     = quizzes the teachers sent (class quizzes) + older practice quizzes
 * "This week" = Sunday to Saturday of this week, "This month" = this calendar month. Data refreshes every minute.
 */
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, Award, BarChart3, ChevronLeft, ChevronRight, ClipboardCheck, Flame, Star, Trophy } from "lucide-react";
import { ROUTES } from "@/lib/routes";
import { usePortal } from "@/lib/store/portal-store";
import { useSession } from "@/lib/auth/local-auth";
import { studentCourseApi, type ClassQuiz } from "@/lib/courses";
import { meetApi, type MeetItem } from "@/lib/meet";
import { dayKey } from "@/lib/utils";

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

const BROWN = "#A8653F";
const DEEP = "#7A4527";
const INK = "#1E2A38";
const MUTED = "#6B756E";
const CARD = "rounded-[20px] bg-white p-4 shadow-[0_1px_2px_rgba(60,50,30,.05),0_12px_30px_-20px_rgba(60,50,30,.22)] sm:px-5";
const H2 = "text-[18px] font-semibold tracking-[-0.01em] text-[#1E2A38]";
const NAV_BTN = "inline-flex h-7 w-7 items-center justify-center rounded-lg border border-[#EADBCB] bg-white text-[#7A4527] transition hover:bg-[#FBF3EA] disabled:opacity-40";

type Period = "week" | "month";
type Quiz = { id: string; title: string; course: string; score: number; at: Date };

function fmt(min: number) {
  const h = Math.floor(min / 60), m = min % 60;
  return h ? `${h}h ${m}m` : `${m} min`;
}
function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}
function addDays(d: Date, n: number) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}
/** Smooth path (Catmull-Rom to Bezier) through points in a 0-100 box. */
function smooth(p: { x: number; y: number }[]) {
  if (!p.length) return "";
  let d = `M${p[0].x} ${p[0].y}`;
  for (let i = 0; i < p.length - 1; i++) {
    const p0 = p[i - 1] ?? p[i], p1 = p[i], p2 = p[i + 1], p3 = p[i + 2] ?? p2;
    d += ` C${(p1.x + (p2.x - p0.x) / 6).toFixed(2)} ${(p1.y + (p2.y - p0.y) / 6).toFixed(2)} ${(p2.x - (p3.x - p1.x) / 6).toFixed(2)} ${(p2.y - (p3.y - p1.y) / 6).toFixed(2)} ${p2.x} ${p2.y}`;
  }
  return d;
}

export default function ProgressView() {
  const { state } = usePortal();
  const { session } = useSession();
  const userId = session?.userId ?? "";
  const [period, setPeriod] = useState<Period>("week");
  const [bar, setBar] = useState<number | null>(null);
  const [calOffset, setCalOffset] = useState(0);
  const [quizIdx, setQuizIdx] = useState<number | null>(null);

  /* ---------- live clock: a new day starts on its own ---------- */
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(t);
  }, []);
  const today = startOfDay(now);
  const todayKey = dayKey(today);
  const [selDay, setSelDay] = useState(todayKey);

  /* ---------- teachers' quizzes and live classes (reloaded every minute and when the tab comes back) ---------- */
  const [classQuizzes, setClassQuizzes] = useState<ClassQuiz[]>([]);
  const [classes, setClasses] = useState<MeetItem[]>([]);
  const load = useCallback(() => {
    if (!userId) return;
    studentCourseApi.classQuizzes(userId).then((r) => setClassQuizzes(r.items)).catch(() => {});
    meetApi.home("student", userId).then((r) => setClasses(r.past)).catch(() => {});
  }, [userId]);
  useEffect(() => {
    load();
    const t = window.setInterval(load, 60_000);
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => { window.clearInterval(t); window.removeEventListener("focus", onFocus); };
  }, [load]);

  /* ---------- minutes per day: learning pages + live classes ---------- */
  const minutesByDay = useMemo(() => {
    const m: Record<string, number> = { ...state.studyLog };
    classes.forEach((c) => {
      // only classes the student really joined, for the minutes he was in (older servers: the booked length)
      if (!c.startsAt || c.state === "cancelled" || c.attended === false) return;
      const k = dayKey(new Date(c.startsAt));
      m[k] = (m[k] ?? 0) + (c.attendedMin ?? c.durationMin ?? 0);
    });
    return m;
  }, [state.studyLog, classes]);
  const minutesOn = (d: Date) => minutesByDay[dayKey(d)] ?? 0;

  /* ---------- quizzes taken ---------- */
  const quizzes = useMemo<Quiz[]>(() => {
    const fromClass = classQuizzes
      .filter((q) => q.attemptsUsed > 0 && q.lastAt && (q.lastScore ?? q.best) !== null)
      .map((q) => ({ id: `c-${q.courseId}-${q.lecture}`, title: q.lectureTitle || `Lecture ${q.lecture} quiz`, course: q.courseTitle, score: Math.round(q.lastScore ?? q.best ?? 0), at: new Date(q.lastAt as string) }));
    const practice = state.attempts.map((a) => ({ id: `p-${a.id}`, title: a.lessonTitle, course: state.studySets.find((s) => s.id === a.studySetId)?.topic ?? "Practice", score: a.scorePct, at: new Date(a.completedAt) }));
    return [...fromClass, ...practice].sort((a, b) => a.at.getTime() - b.at.getTime());
  }, [classQuizzes, state.attempts, state.studySets]);
  const pending = classQuizzes.filter((q) => q.state === "open" && q.attemptsUsed === 0);

  /* ---------- the period: this week (Sun-Sat) or this month ---------- */
  const range = useMemo(() => {
    if (period === "week") {
      const start = addDays(today, -today.getDay());
      return Array.from({ length: 7 }, (_, i) => addDays(start, i));
    }
    const n = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
    return Array.from({ length: n }, (_, i) => new Date(today.getFullYear(), today.getMonth(), i + 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, todayKey]);
  const vals = range.map((d) => (d > today ? 0 : minutesOn(d)));
  const elapsed = range.filter((d) => d <= today).length;
  const studied = range.filter((d, i) => d <= today && vals[i] > 0).length;
  const total = vals.reduce((a, b) => a + b, 0);
  const peak = Math.max(...vals, 0);
  const step = period === "week" ? 15 : 30;
  const niceMax = Math.max(60, Math.ceil(peak / step) * step);
  const todayIdx = range.findIndex((d) => d.getTime() === today.getTime());
  const selBar = bar !== null && bar < range.length ? bar : Math.max(0, todayIdx);
  const tick = (m: number) => (m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ""}` : `${m}m`);
  const axis = [1, 0.5, 0].map((f) => (f ? tick(Math.round(niceMax * f)) : "0"));
  const ringPct = elapsed ? Math.round((studied / elapsed) * 100) : 0;
  const periodName = period === "week" ? "this week" : MONTHS[today.getMonth()];
  const inPeriod = (d: Date) => d >= range[0] && d < addDays(range[range.length - 1], 1);

  /* ---------- quiz scores in the period ---------- */
  const pq = quizzes.filter((q) => inPeriod(q.at)).slice(-10);
  const qi = quizIdx !== null && quizIdx < pq.length ? quizIdx : pq.length - 1;
  const qPts = pq.map((q, i) => ({ q, x: pq.length > 1 ? +((i / (pq.length - 1)) * 100).toFixed(2) : 50, y: +(100 - (Math.max(q.score, 0) / 100) * 100).toFixed(2) }));
  const qLine = qPts.length > 1 ? smooth(qPts) : "";
  const qArea = qLine ? `${qLine} L100 100 L0 100 Z` : "";
  const cq = qPts[qi];
  const qDiff = cq && qi > 0 ? cq.q.score - qPts[qi - 1].q.score : null;
  const pAvg = pq.length ? Math.round(pq.reduce((a, q) => a + q.score, 0) / pq.length) : null;
  const pBest = pq.length ? Math.max(...pq.map((q) => q.score)) : null;

  /* ---------- calendar: a week strip or the month grid ---------- */
  const calWeekStart = addDays(today, -today.getDay() + calOffset * 7);
  const calMonth = new Date(today.getFullYear(), today.getMonth() + calOffset, 1);
  const cells = period === "week"
    ? Array.from({ length: 7 }, (_, i) => addDays(calWeekStart, i))
    : (() => {
        const first = addDays(calMonth, -calMonth.getDay());
        const last = new Date(calMonth.getFullYear(), calMonth.getMonth() + 1, 0);
        const n = Math.ceil((last.getDate() + calMonth.getDay()) / 7) * 7;
        return Array.from({ length: n }, (_, i) => addDays(first, i));
      })();
  const calTitle = period === "week" ? `${MONTHS[calWeekStart.getMonth()]} ${calWeekStart.getFullYear()}` : `${MONTHS[calMonth.getMonth()]} ${calMonth.getFullYear()}`;
  const [sy, sm, sd] = selDay.split("-").map(Number);
  const selDate = new Date(sy, sm - 1, sd);
  const selMins = selDate > today ? 0 : minutesOn(selDate);
  const selQuizzes = quizzes.filter((q) => dayKey(q.at) === selDay);
  const selClasses = classes.filter((c) => c.startsAt && c.state !== "cancelled" && c.attended !== false && dayKey(new Date(c.startsAt)) === selDay);
  const calMax = Math.max(30, ...cells.map((d) => minutesOn(d)));

  /* rhythm line for the week strip */
  const rMax = Math.max(60, ...cells.map((d) => minutesOn(d)));
  const rPts = cells.map((d, i) => ({ d, key: dayKey(d), future: d > today, mins: minutesOn(d), x: +((i / 6) * 100).toFixed(2), y: +(d > today ? 96 : 92 - (Math.min(minutesOn(d), rMax) / rMax) * 80).toFixed(2) }));
  const past = rPts.filter((p) => !p.future);
  const rLine = past.length > 1 ? smooth(past) : "";
  const rArea = rLine ? `${rLine} L${past[past.length - 1].x} 100 L${past[0].x} 100 Z` : "";

  /* streak: days in a row with study, up to today (or yesterday) */
  let streak = 0;
  for (let d = minutesOn(today) ? today : addDays(today, -1); minutesOn(d) > 0; d = addDays(d, -1)) streak += 1;

  const switchPeriod = (p: Period) => { setPeriod(p); setBar(null); setCalOffset(0); setQuizIdx(null); setSelDay(todayKey); };

  return (
    <div className="flex flex-col gap-4 lg:h-[calc(100vh-150px)] lg:min-h-[600px]">
      {/* header */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[linear-gradient(150deg,#B06D45,#8E5233)] text-white shadow-[0_8px_18px_-10px_rgba(90,50,30,0.8)]">
            <BarChart3 className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-[30px] font-semibold leading-[1.1] tracking-[-0.015em] text-[#1E2A38]">Progress</h1>
            <p className="text-sm text-[#4B5563]">Your study time and quiz scores, live.</p>
          </div>
        </div>
        <div role="group" aria-label="Period" className="flex rounded-xl border border-[#EADBCB] bg-white p-1">
          {(["week", "month"] as const).map((p) => (
            <button key={p} type="button" onClick={() => switchPeriod(p)} aria-pressed={period === p} data-testid={`period-${p}`}
              className={`h-[32px] rounded-[9px] px-3.5 text-[13px] font-semibold transition ${period === p ? "bg-[#A8653F] text-white" : "text-[#3C4A5A] hover:bg-[#FBF3EA]"}`}>
              {p === "week" ? "This week" : "This month"}
            </button>
          ))}
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3.5 rounded-[26px] bg-[#F3EFE6] p-3 sm:p-4 lg:grid-cols-12 lg:grid-rows-[minmax(0,40%)_minmax(0,1fr)]">
        {/* study time ring */}
        <section className={`${CARD} flex min-h-[200px] flex-col items-center justify-between gap-2 lg:col-span-3 lg:min-h-0`} data-testid="progress-ring">
          <span className="relative min-h-0 w-full flex-1">
            <svg viewBox="0 0 168 168" className="absolute inset-0 m-auto h-full max-h-[150px] w-full" aria-hidden>
              <defs>
                <linearGradient id="pgRing" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#8E5233" /><stop offset="1" stopColor="#F2B98C" /></linearGradient>
              </defs>
              <circle cx="84" cy="84" r="70" fill="none" stroke="#F3EADF" strokeWidth="9" />
              <circle cx="84" cy="84" r="70" fill="none" stroke="url(#pgRing)" strokeWidth="9" strokeLinecap="round" pathLength={100} strokeDasharray={`${ringPct} 100`} transform="rotate(-90 84 84)" className="transition-[stroke-dasharray] duration-700" />
              <text x="84" y="84" textAnchor="middle" fontSize="28" fontWeight="600" fill={INK}>{Math.floor(total / 60)}<tspan fontSize="13" fill={MUTED}>h </tspan>{total % 60}<tspan fontSize="13" fill={MUTED}>m</tspan></text>
              <text x="84" y="104" textAnchor="middle" fontSize="11.5" fill={MUTED}>{periodName}</text>
            </svg>
          </span>
          <div className="self-stretch">
            <p className="text-[15px] font-semibold text-[#1E2A38]">{period === "week" ? "Weekly study time" : "Monthly study time"}</p>
            <p className="text-[12.5px] text-[#6B756E]">{studied} of {elapsed} days studied · {elapsed ? Math.round(total / elapsed) : 0} min a day</p>
          </div>
        </section>

        {/* next up (brown) */}
        <section className="relative flex min-h-[200px] flex-col gap-2 overflow-hidden rounded-[20px] bg-[linear-gradient(160deg,#3A2B29_0%,#5A433C_100%)] px-5 py-4 text-white lg:col-span-3 lg:min-h-0" data-testid="progress-next">
          <svg viewBox="0 0 300 300" preserveAspectRatio="xMidYMin slice" className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
            <g fill="none" stroke="#F7C58B" strokeOpacity=".12"><circle cx="230" cy="40" r="60" /><circle cx="230" cy="40" r="95" /><circle cx="230" cy="40" r="130" /></g>
          </svg>
          <span className="relative inline-flex h-[22px] items-center gap-1.5 self-start rounded-full bg-white/15 px-2.5 text-[11px] font-bold text-[#FDEEDD]"><Star className="h-3 w-3 fill-[#F7C58B] text-[#F7C58B]" />Next up</span>
          <div className="relative flex min-h-0 flex-1 items-center justify-center">
            <BookScene />
          </div>
          {pending.length ? (
            <div className="relative">
              <p className="truncate text-[17px] font-semibold leading-tight">{pending[0].lectureTitle || `Lecture ${pending[0].lecture} quiz`}</p>
              <p className="truncate text-[12px] text-[#E8DBD4]">{pending[0].courseTitle} · {pending[0].questions} questions{pending.length > 1 ? ` · ${pending.length - 1} more waiting` : ""}</p>
              <Link href={ROUTES.student.assessments} className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-full bg-[linear-gradient(90deg,#B06D45,#8E5233)] px-4 text-[12.5px] font-semibold text-white transition hover:brightness-110">Start quiz <ArrowRight className="h-3.5 w-3.5" /></Link>
            </div>
          ) : (
            <div className="relative">
              <p className="text-[17px] font-semibold leading-tight">{quizzes.length ? "All quizzes done" : "Take your first quiz"}</p>
              <p className="text-[12px] text-[#E8DBD4]">{quizzes.length ? "New quizzes from your teachers show here." : "Your teachers send quizzes in live classes."}</p>
              <Link href={ROUTES.student.assessments} className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-full bg-[linear-gradient(90deg,#B06D45,#8E5233)] px-4 text-[12.5px] font-semibold text-white transition hover:brightness-110">Go to quizzes <ArrowRight className="h-3.5 w-3.5" /></Link>
            </div>
          )}
        </section>

        {/* study hours */}
        <section className={`${CARD} flex min-h-[200px] flex-col gap-2 lg:col-span-6 lg:min-h-0`} data-testid="progress-hours">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className={H2}>Study hours</h2>
              <p className="text-xs text-[#6B756E]">Lessons, videos, quizzes and live classes · {period === "week" ? "this week" : MONTHS[today.getMonth()]}</p>
            </div>
            <div className="text-right">
              <p className="text-[24px] font-semibold leading-none tracking-[-0.02em] text-[#1E2A38]">{Math.floor(total / 60)}<span className="text-[12px] font-medium text-[#6B756E]">h</span> {total % 60}<span className="text-[12px] font-medium text-[#6B756E]">min</span></p>
              <p className="mt-1 text-[11.5px] text-[#6B756E]">{range[selBar].toLocaleDateString("en-US", { weekday: "short", day: "numeric", month: "short" })} · {range[selBar] > today ? "not yet" : fmt(vals[selBar] ?? 0)}</p>
            </div>
          </div>
          <div className="flex min-h-0 flex-1 gap-2">
            <div className="flex flex-col justify-between pb-[20px] text-[10px] text-[#9AA29C]">{axis.map((t, i) => <span key={i}>{t}</span>)}</div>
            <div className="flex min-w-0 flex-1 flex-col">
              <div className="relative flex min-h-[80px] flex-1 items-end justify-around bg-[repeating-linear-gradient(to_top,#F3F1EC_0,#F3F1EC_1px,transparent_1px,transparent_50%)]">
                {range.map((d, i) => {
                  const v = vals[i], on = i === selBar, future = d > today, h = Math.max((v / niceMax) * 100, future ? 2 : 3);
                  return (
                    <button key={i} type="button" onClick={() => setBar(i)} aria-label={`${d.toDateString()}: ${future ? "not yet" : fmt(v)}`} className="relative flex h-full min-w-0 flex-1 flex-col items-center justify-end">
                      {on && !future && <span className="absolute z-[1] inline-flex h-[20px] items-center whitespace-nowrap rounded-md bg-[#7A4527] px-[6px] text-[10.5px] font-semibold text-white" style={{ bottom: `calc(${h}% + 6px)` }}>{fmt(v)}</span>}
                      <span className="rounded-full transition-[height,background-color] duration-500" style={{ width: period === "week" ? 10 : 6, height: `${h}%`, background: on ? BROWN : future ? "#F1ECE4" : v ? "#E7CDB6" : "#EEE8DE" }} />
                    </button>
                  );
                })}
              </div>
              <div className="flex h-[18px] justify-around pt-1.5">
                {range.map((d, i) => {
                  const show = period === "week" || d.getDate() === 1 || d.getDate() % 5 === 0 || i === todayIdx;
                  return <span key={i} className={`min-w-0 flex-1 text-center text-[10.5px] ${i === selBar ? "font-bold text-[#7A4527]" : "text-[#9AA29C]"}`}>{show ? (period === "week" ? (i === todayIdx ? "Today" : DAY_NAMES[d.getDay()]) : d.getDate()) : ""}</span>;
                })}
              </div>
            </div>
          </div>
        </section>

        {/* quiz scores */}
        <section className={`${CARD} flex min-h-[300px] flex-col gap-2.5 lg:col-span-6 lg:min-h-0`} data-testid="progress-quizzes">
          <div className="flex items-start justify-between">
            <div>
              <h2 className={H2}>Quiz scores</h2>
              <p className="text-xs text-[#6B756E]">{pq.length ? `${pq.length} quiz${pq.length > 1 ? "zes" : ""} ${periodName === "this week" ? "this week" : `in ${periodName}`} · click a point` : `Quizzes ${periodName === "this week" ? "this week" : `in ${periodName}`}`}</p>
            </div>
            <p className="text-[24px] font-semibold leading-none tracking-[-0.02em] text-[#1E2A38]">{pAvg ?? "–"}<span className="text-[12px] font-medium text-[#6B756E]">{pAvg !== null ? "% avg" : ""}</span></p>
          </div>
          {pq.length === 0 ? (
            <Link href={ROUTES.student.assessments} className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 rounded-2xl bg-[#FAF6EF] text-center text-sm text-[#6B756E] transition hover:bg-[#F6EEE3]">
              <ClipboardCheck className="h-7 w-7 text-[#C9A27A]" />
              No quiz {period === "week" ? "this week" : "this month"} yet.
              <span className="text-[12.5px] font-semibold text-[#7A4527]">{pending.length ? `${pending.length} waiting for you →` : "Open quizzes →"}</span>
            </Link>
          ) : (
            <div className="flex min-h-0 flex-1 gap-3">
              <div className="flex min-w-0 flex-1 flex-col">
                <div className="relative mx-2 mt-6 min-h-[80px] flex-1">
                  <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
                    <defs><linearGradient id="pgArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#B06D45" stopOpacity=".25" /><stop offset="1" stopColor="#B06D45" stopOpacity="0" /></linearGradient></defs>
                    <path d="M0 0H100M0 50H100M0 100H100" stroke="#F1EBE1" vectorEffect="non-scaling-stroke" />
                    {qArea && <path className="pg-rise" d={qArea} fill="url(#pgArea)" />}
                    {qLine && <path className="pg-draw" pathLength={1} d={qLine} fill="none" stroke={BROWN} strokeWidth="2.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />}
                  </svg>
                  {qPts.map((p, i) => (
                    <button key={p.q.id + i} type="button" onClick={() => setQuizIdx(i)} aria-label={`${p.q.title}: ${p.q.score}%`} className="absolute -ml-[12px] -mt-[12px] flex h-6 w-6 items-center justify-center" style={{ left: `${p.x}%`, top: `${p.y}%` }}>
                      <span className="box-border rounded-full border-[2.5px] transition-all" style={{ borderColor: BROWN, width: i === qi ? 14 : 10, height: i === qi ? 14 : 10, background: i === qi ? BROWN : "#fff" }} />
                    </button>
                  ))}
                  {cq && <span className="pointer-events-none absolute flex h-6 items-center whitespace-nowrap rounded-md bg-[#7A4527] px-2 text-[11.5px] font-semibold text-white" style={{ left: `${cq.x}%`, top: `${cq.y}%`, transform: `translate(${qi === 0 ? "-10%" : qi === qPts.length - 1 ? "-90%" : "-50%"}, calc(-100% - 14px))` }}>{cq.q.score}%</span>}
                </div>
                <div className="mx-2 flex justify-between pt-1 text-[10.5px]">
                  {qPts.map((p, i) => <span key={i} className={`w-6 text-center ${i === qi ? "font-bold text-[#7A4527]" : "text-[#9AA29C]"}`}>{p.q.at.getDate()}/{p.q.at.getMonth() + 1}</span>)}
                </div>
              </div>
              <div className="flex w-[170px] shrink-0 flex-col gap-2">
                {cq && (
                  <div className="flex flex-col gap-1 rounded-2xl bg-[#FBF3EA] px-3 py-2.5">
                    <span className="text-[10.5px] font-bold tracking-[.08em] text-[#A8653F]">QUIZ {qi + 1}</span>
                    <span className="line-clamp-2 text-[13.5px] font-semibold leading-tight text-[#1E2A38]">{cq.q.title}</span>
                    <span className="truncate text-[11px] text-[#6B756E]">{cq.q.course} · {cq.q.at.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}</span>
                    <span className="flex items-baseline gap-1.5">
                      <b className="text-[20px] text-[#1E2A38]">{cq.q.score}%</b>
                      <span className={`text-[11px] font-bold ${qDiff == null ? "text-[#6B756E]" : qDiff >= 0 ? "text-[#2F7A4E]" : "text-[#C0563E]"}`}>{qDiff == null ? "first" : `${qDiff >= 0 ? "▲" : "▼"} ${Math.abs(qDiff)}`}</span>
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
          <div className="grid shrink-0 grid-cols-3 gap-2">
            {[
              { label: "Best", value: pBest === null ? "–" : `${pBest}%`, Icon: Trophy, color: "#E8893A" },
              { label: "Taken", value: String(pq.length), Icon: ClipboardCheck, color: BROWN },
              { label: "Certificates", value: String(state.certificates.length), Icon: Award, color: "#3E9B6B" },
            ].map(({ label, value, Icon, color }) => (
              <span key={label} className="flex items-center gap-1.5 rounded-xl bg-[#FAF6EF] px-2.5 py-[7px]">
                <Icon className="h-[14px] w-[14px] shrink-0" style={{ color }} strokeWidth={2.1} />
                <span className="truncate text-[11.5px] text-[#6B756E]">{label}</span>
                <b className="ml-auto text-[13px] text-[#1E2A38]">{value}</b>
              </span>
            ))}
          </div>
        </section>

        {/* calendar */}
        <section className={`${CARD} flex min-h-[300px] flex-col gap-2.5 lg:col-span-6 lg:min-h-0`} data-testid="progress-calendar">
          <div className="flex items-center justify-between">
            <h2 className={H2}>{calTitle}</h2>
            <span className="flex items-center gap-2">
              <span className="inline-flex h-[24px] items-center gap-1 rounded-full bg-[#FBF3EA] px-2.5 text-[11.5px] font-bold text-[#9A4F12]"><Flame className="h-3.5 w-3.5 fill-[#F2B98C] text-[#E8893A]" />{streak} day streak</span>
              <button type="button" onClick={() => setCalOffset((w) => w - 1)} aria-label={period === "week" ? "Previous week" : "Previous month"} className={NAV_BTN}><ChevronLeft className="h-3.5 w-3.5" /></button>
              <button type="button" onClick={() => setCalOffset((w) => w + 1)} disabled={calOffset >= 0} aria-label={period === "week" ? "Next week" : "Next month"} className={NAV_BTN}><ChevronRight className="h-3.5 w-3.5" /></button>
            </span>
          </div>

          {period === "week" ? (
            <div className="grid grid-cols-7 gap-1">
              {cells.map((d) => {
                const k = dayKey(d), on = k === selDay, isToday = k === todayKey, future = d > today, mins = minutesOn(d);
                return (
                  <button key={k} type="button" onClick={() => setSelDay(k)} aria-pressed={on} className={`flex flex-col items-center gap-0.5 rounded-xl pb-1 pt-1.5 transition ${on ? "bg-[#A8653F]" : "hover:bg-[#FBF3EA]"}`}>
                    <span className={`text-[10.5px] ${on ? "text-[#FDEEDD]" : "text-[#9AA29C]"}`}>{DAY_NAMES[d.getDay()]}</span>
                    <span className={`text-[14px] ${on || isToday ? "font-bold" : "font-medium"} ${on ? "text-white" : future ? "text-[#C9C2B8]" : "text-[#1E2A38]"}`}>{d.getDate()}</span>
                    <span className="h-[5px] w-[5px] rounded-full" style={{ background: mins > 0 ? (on ? "#F7C58B" : "#E8893A") : "transparent" }} />
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="grid min-h-0 flex-1 grid-cols-7 gap-1 text-center" style={{ gridTemplateRows: `auto repeat(${cells.length / 7}, minmax(0, 1fr))` }}>
              {DAY_NAMES.map((n) => <span key={n} className="text-[10px] font-semibold text-[#9AA29C]">{n.slice(0, 2)}</span>)}
              {cells.map((d) => {
                const k = dayKey(d), on = k === selDay, inMonth = d.getMonth() === calMonth.getMonth(), future = d > today, mins = minutesOn(d);
                const a = mins ? 0.15 + 0.6 * Math.min(mins / calMax, 1) : 0;
                return (
                  <button key={k} type="button" onClick={() => setSelDay(k)} aria-pressed={on} aria-label={`${d.toDateString()}: ${future ? "not yet" : fmt(mins)}`}
                    className={`flex min-h-0 items-center justify-center rounded-lg text-[12px] transition ${on ? "bg-[#A8653F] font-bold text-white" : k === todayKey ? "font-bold text-[#7A4527] ring-1 ring-[#A8653F]" : future || !inMonth ? "text-[#C9C2B8]" : "text-[#1E2A38] hover:ring-1 hover:ring-[#E3D3C1]"}`}
                    style={on ? undefined : { background: a ? `rgba(232,137,58,${a.toFixed(2)})` : undefined }}>
                    {d.getDate()}
                  </button>
                );
              })}
            </div>
          )}

          <div className="flex shrink-0 items-center justify-between gap-2 rounded-xl border-[1.5px] border-dashed border-[#E8D9C7] px-3 py-1.5 text-[12px] text-[#6B756E]">
            <b className="text-[#1E2A38]">{selDay === todayKey ? "Today · " : ""}{DAY_NAMES[selDate.getDay()]} {selDate.getDate()} {MONTHS[selDate.getMonth()].slice(0, 3)}</b>
            <span className="truncate">
              {selDate > today ? "This day has not come yet" : selMins || selQuizzes.length || selClasses.length
                ? [selMins ? `${fmt(selMins)} studied` : "", selClasses.length ? `${selClasses.length} live class${selClasses.length > 1 ? "es" : ""}` : "", selQuizzes.length ? `${selQuizzes.length} quiz${selQuizzes.length > 1 ? "zes" : ""} · best ${Math.max(...selQuizzes.map((q) => q.score))}%` : ""].filter(Boolean).join(" · ")
                : "No study on this day"}
            </span>
          </div>

          {period === "week" && (
            <div className="relative flex min-h-[90px] flex-1 flex-col gap-1 overflow-hidden rounded-2xl bg-[linear-gradient(180deg,#FFFBF6_0%,#FBF3EA_100%)] px-3 pb-2 pt-2.5">
              <span className="text-[12.5px] font-semibold text-[#1E2A38]">Study rhythm <span className="font-normal text-[#6B756E]">· minutes each day</span></span>
              <div className="relative mx-2.5 mt-1 min-h-[40px] flex-1">
                <svg key={`${calOffset}`} viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
                  <defs>
                    <linearGradient id="pgRh" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#B06D45" stopOpacity=".3" /><stop offset="1" stopColor="#B06D45" stopOpacity="0" /></linearGradient>
                  </defs>
                  <path d="M0 33H100M0 66H100" stroke="#EFE3D4" strokeDasharray="2 3" vectorEffect="non-scaling-stroke" />
                  {rArea && <path className="pg-rise" d={rArea} fill="url(#pgRh)" />}
                  {rLine && <path className="pg-draw" pathLength={1} d={rLine} fill="none" stroke={BROWN} strokeWidth="3" strokeLinecap="round" vectorEffect="non-scaling-stroke" />}
                </svg>
                {rPts.map((p) => {
                  const on = p.key === selDay;
                  return (
                    <button key={p.key} type="button" onClick={() => setSelDay(p.key)} aria-label={`${DAY_NAMES[p.d.getDay()]} ${p.d.getDate()}: ${p.future ? "not yet" : `${p.mins} min`}`} className="absolute -ml-3 -mt-3 flex h-6 w-6 items-center justify-center" style={{ left: `${p.x}%`, top: `${p.y}%` }}>
                      {on && <span className="pg-pulse absolute h-3 w-3 rounded-full bg-[#A8653F]" />}
                      <span className="relative box-border rounded-full border-[2.5px]" style={{ width: on ? 13 : 9, height: on ? 13 : 9, background: on ? BROWN : p.future ? "#F7F1E8" : "#fff", borderColor: p.future ? "#E3D3C1" : BROWN }} />
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

/** Open book with a floating orb and sparkles (Next up card). */
function BookScene() {
  return (
    <svg viewBox="0 0 170 112" aria-hidden className="h-full max-h-[96px] w-auto drop-shadow-[0_12px_14px_rgba(20,10,5,.35)]">
      <defs>
        <radialGradient id="pgOrb" cx=".35" cy=".3" r=".75"><stop offset="0" stopColor="#FCD3B1" /><stop offset=".6" stopColor="#EE8F55" /><stop offset="1" stopColor="#C9672B" /></radialGradient>
        <linearGradient id="pgPg" x1="0" x2="1"><stop offset="0" stopColor="#FFFFFF" /><stop offset="1" stopColor="#F2EADF" /></linearGradient>
      </defs>
      <path d="M22 88 85 104 148 88 148 80 85 96 22 80z" fill="#8E5233" />
      <path d="M22 80 85 96 148 80 148 74 85 90 22 74z" fill="#E3A877" />
      <path d="M85 90 C66 80 42 78 24 82 V44 C42 40 66 42 85 52z" fill="url(#pgPg)" />
      <path d="M85 90 C104 80 128 78 146 82 V44 C128 40 104 42 85 52z" fill="#F7F1E8" />
      <path d="M85 52 V90" stroke="#D9CDBB" strokeWidth="1.5" />
      <g stroke="#CBBFA9" strokeWidth="1.6" strokeLinecap="round"><path d="M36 54c12-2 26-1 38 3M36 63c12-2 26-1 38 3M36 72c12-2 26-1 38 3M96 57c12-4 26-5 38-3M96 66c12-4 26-5 38-3" /></g>
      <g className="pg-bob"><circle cx="112" cy="26" r="17" fill="url(#pgOrb)" /><ellipse cx="106" cy="19" rx="5" ry="3" fill="#fff" opacity=".4" /></g>
      <g fill="#F7C58B">
        <path className="pg-tw" d="M54 18l2 6 6 2-6 2-2 6-2-6-6-2 6-2z" />
        <path className="pg-tw" style={{ animationDelay: "-1s" }} d="M146 34l1.3 3.7 3.7 1.3-3.7 1.3-1.3 3.7-1.3-3.7-3.7-1.3 3.7-1.3z" />
      </g>
    </svg>
  );
}
