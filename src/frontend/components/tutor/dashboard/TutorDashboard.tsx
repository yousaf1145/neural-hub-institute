"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUpRight, CalendarCheck, CalendarDays, CheckCircle2, ChevronLeft, ChevronRight, GraduationCap, Inbox, Lightbulb,
  LineChart, RefreshCw, ShieldAlert, Sparkles, Square, Star, Timer, TrendingUp, Users, Video, Volume2, type LucideIcon,
} from "lucide-react";
import { useTutor } from "@/components/tutor/shared/tutor-context";
import { ErrorBox, Loading, joinState } from "@/components/tutor/shared/ui";
import PersonPhoto from "@/components/shared/PersonPhoto";
import { ROUTES } from "@/lib/routes";
import { meetHref } from "@/lib/meet";
import { tutorApi, useTutorQuery, type DailyBrief, type Dashboard, type SessionView } from "@/lib/tutor/api";
import { dayKey } from "@/lib/utils";
import "@/app/tutor/tutor-new.css";

/** Tutor dashboard, new look: 4 numbers, schedule + daily brief, student journey + this month. */

type Tone = "blue" | "violet" | "teal" | "amber";
const PLURALS: Record<string, string> = { class: "classes", quiz: "quizzes" };
const plural = (n: number, w: string) => `${n} ${n === 1 ? w : (PLURALS[w] ?? `${w}s`)}`;
const timeText = (iso: string | null) => new Date(iso ?? 0).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
const firstName = (n: string) => n.replace(/^(Dr|Mr|Ms|Mrs|Prof)\.?\s+/i, "").split(" ")[0] || n;
const PHOTO = "bg-gradient-to-br from-[#E3EEFB] to-[#CFE1F7] font-bold text-[#1572C9]";

function Tile({ tone, Icon, size = 36 }: { tone: Tone; Icon: LucideIcon; size?: number }) {
  return (
    <span className={`nh-tv-tile nh-tv-${tone}`} style={{ width: size, height: size, borderRadius: size * 0.31 }}>
      <span className="nh-tv-gloss" />
      <Icon className="relative text-white" style={{ width: size * 0.48, height: size * 0.48 }} strokeWidth={2.1} />
    </span>
  );
}

function CountUp({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return setV(value);
    let raf = 0;
    const t0 = performance.now();
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / 900);
      setV(value * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <>{v.toFixed(decimals)}</>;
}

function CardHead({ tone, Icon, title, sub, href, linkLabel, right }: { tone: Tone; Icon: LucideIcon; title: string; sub: string; href?: string; linkLabel?: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-3">
        <Tile tone={tone} Icon={Icon} />
        <div className="min-w-0">
          <b className="block text-[16px] text-[#1B1F24]">{title}</b>
          <span className="block truncate text-[12px] text-[#6B6F76]">{sub}</span>
        </div>
      </div>
      {right}
      {href && (
        <Link href={href} className="nh-tv-pill">
          {linkLabel} <ChevronRight className="h-3.5 w-3.5" />
        </Link>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- 4 numbers */

function StatCard({ tone, Icon, label, href, delay, children }: { tone: Tone; Icon: LucideIcon; label: string; href: string; delay: number; children: React.ReactNode }) {
  return (
    <Link href={href} className="nh-tv-card nh-tv-lift nh-tv-up flex min-h-[104px] flex-col justify-between gap-2 px-4 py-3.5" style={{ animationDelay: `${delay}s` }}>
      <div className="flex items-center gap-2.5">
        <Tile tone={tone} Icon={Icon} size={30} />
        <span className="flex-1 text-[11.5px] font-bold uppercase tracking-[0.12em] text-[#3B4047]">{label}</span>
        <span className="nh-tv-arrow"><ArrowUpRight className="h-3.5 w-3.5" /></span>
      </div>
      <div className="flex items-end justify-between gap-3">{children}</div>
    </Link>
  );
}

function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const w = 96, h = 34;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - (Math.max(0, Math.min(100, v)) / 100) * (h - 4) - 2}`);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="shrink-0" aria-hidden="true">
      <polygon points={`0,${h} ${pts.join(" ")} ${w},${h}`} fill="rgba(21,114,201,.08)" />
      <polyline points={pts.join(" ")} fill="none" stroke="#1572C9" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" className="nh-tv-draw" />
    </svg>
  );
}

/* ---------------------------------------------------------------- schedule */

function ScheduleCard({ sessions }: { sessions: SessionView[] }) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = useMemo(() => Array.from({ length: 31 }, (_, i) => new Date(today.getTime() + (i - 3) * 86400000)), [today.getTime()]); // eslint-disable-line react-hooks/exhaustive-deps
  const [pick, setPick] = useState(dayKey(today));
  const strip = useRef<HTMLDivElement>(null);
  const live = sessions.filter((s) => s.status === "scheduled" && !s.ended);
  const has = new Set(live.map((s) => dayKey(new Date(s.startsAt ?? 0))));
  const list = live.filter((s) => dayKey(new Date(s.startsAt ?? 0)) === pick).sort((a, b) => (a.startsAt ?? "").localeCompare(b.startsAt ?? ""));
  const picked = new Date(`${pick}T12:00:00`);
  const move = (dir: number) => strip.current?.scrollBy({ left: dir * strip.current.clientWidth * 0.9, behavior: "smooth" });

  return (
    <section className="nh-tv-card nh-tv-up flex min-h-0 flex-col gap-3 px-[18px] py-4" style={{ animationDelay: ".1s" }}>
      <CardHead tone="blue" Icon={CalendarDays} title="Schedule" sub={picked.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })} href={ROUTES.tutor.schedule} linkLabel="Full schedule" />
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => move(-1)} className="nh-tv-navbtn" aria-label="Earlier days"><ChevronLeft className="h-4 w-4" /></button>
        <div ref={strip} className="nh-tv-strip flex min-w-0 flex-1 gap-2 overflow-x-auto scroll-smooth py-0.5">
          {days.map((d) => {
            const k = dayKey(d);
            const on = k === pick;
            const past = d < today;
            return (
              <button key={k} type="button" onClick={() => setPick(k)} aria-pressed={on} className={`nh-tv-day ${on ? "is-on" : ""} ${past ? "is-past" : ""}`}>
                <span className="text-[10.5px] font-bold uppercase tracking-[0.06em]">{d.toLocaleDateString("en-US", { weekday: "short" })}</span>
                <span className="text-[19px] font-semibold leading-none">{d.getDate()}</span>
                <span className={`h-[5px] w-[5px] rounded-full ${has.has(k) ? "bg-[#1572C9]" : "bg-transparent"}`} />
              </button>
            );
          })}
        </div>
        <button type="button" onClick={() => move(1)} className="nh-tv-navbtn" aria-label="Later days"><ChevronRight className="h-4 w-4" /></button>
      </div>
      {list.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-1 rounded-2xl border border-dashed border-[#E2DCD7] py-4 text-center">
          <CalendarCheck className="h-6 w-6 text-[#A8ACB2]" />
          <b className="mt-1 text-[14px] text-[#1B1F24]">No classes on this day</b>
          <span className="text-[12.5px] text-[#6B6F76]">Students book from your open hours.</span>
        </div>
      ) : (
        <ul className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
          {list.map((s) => {
            const j = joinState(s);
            const ended = new Date(s.startsAt ?? 0).getTime() + s.durationMin * 60000 < Date.now();
            return (
              <li key={`${s.userId}-${s.id}`} className="nh-tv-row flex items-center gap-3.5 px-3.5 py-3">
                <b className="w-[70px] shrink-0 text-[14px] text-[#1B1F24]">{timeText(s.startsAt)}</b>
                <PersonPhoto kind="student" id={s.userId} name={s.studentName} className={`h-[40px] w-[40px] text-[13px] ${PHOTO}`} />
                <span className="min-w-0 flex-1">
                  <b className="block truncate text-[15px] text-[#1B1F24]">{s.studentName}</b>
                  <span className="block truncate text-[12.5px] text-[#6B6F76]">{s.topic} · {s.durationMin} min</span>
                </span>
                {j.live && !s.outcome ? (
                  <Link href={meetHref(s.id, { userId: s.userId })} className="nh-tv-btn shrink-0 rounded-full"><Video className="h-3.5 w-3.5" /> Join now</Link>
                ) : s.outcome === "completed" ? (
                  <span className="nh-tv-chip bg-[#E4F5EC] text-[#1E7A4E]">Completed</span>
                ) : s.outcome === "no_show" ? (
                  <span className="nh-tv-chip bg-[#FBE4E1] text-[#B4271E]">Missed</span>
                ) : ended ? (
                  <Link href={ROUTES.tutor.schedule} className="nh-tv-chip bg-[#FCE3C9] text-[#8F3A00]">Awaiting check-in</Link>
                ) : (
                  <span className="nh-tv-chip bg-[#E3EEFB] text-[#1559A8]">{j.label ? `Starts ${j.label}` : "Confirmed"}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/* ---------------------------------------------------------------- daily brief */

function BriefCard({ tutorId, data, todayList }: { tutorId: string; data: Dashboard; todayList: SessionView[] }) {
  const q = useTutorQuery(() => tutorApi.dailyBrief(tutorId), [tutorId]);
  const brief: DailyBrief | null = q.data;
  const [spin, setSpin] = useState(false);
  const [line, setLine] = useState(-1);
  const [speaking, setSpeaking] = useState(false);
  useEffect(() => () => window.speechSynthesis?.cancel(), []);

  const { counts } = data;
  const next = todayList.find((s) => new Date(s.startsAt ?? 0).getTime() + s.durationMin * 60000 > Date.now());
  const info = [
    next ? `Your next class is with ${next.studentName} at ${timeText(next.startsAt)}.` : todayList.length ? "Your classes for today are done." : "No classes today.",
    counts.pendingRequests
      ? `${plural(counts.pendingRequests, "new request")} ${counts.pendingRequests === 1 ? "is" : "are"} waiting for your decision.`
      : "No new requests waiting.",
    ...(counts.reviewsToReply ? [`${plural(counts.reviewsToReply, "review")} from students ${counts.reviewsToReply === 1 ? "is" : "are"} waiting for your reply.`] : []),
  ];
  const risk = brief?.lines?.risk ?? brief?.priorities.filter((p) => p.urgency !== "low" && !p.title.startsWith("Session with")).map((p) => `${p.title}: ${p.detail}`) ?? [];
  const good = brief?.lines?.good ?? [];
  const all = [...info, ...risk, ...good];

  const refresh = async () => {
    setSpin(true);
    try {
      q.setData(await tutorApi.dailyBrief(tutorId, true));
    } catch {
      /* keep the old brief */
    } finally {
      setSpin(false);
    }
  };

  const speak = () => {
    const ss = window.speechSynthesis;
    if (!ss) return;
    if (speaking) {
      ss.cancel();
      setSpeaking(false);
      setLine(-1);
      return;
    }
    ss.cancel();
    setSpeaking(true);
    const intro = new SpeechSynthesisUtterance(`Hello ${firstName(data.tutor.name)}. Here is your daily brief.`);
    ss.speak(intro);
    all.forEach((t, i) => {
      const u = new SpeechSynthesisUtterance(t);
      u.rate = 0.98;
      u.onstart = () => setLine(i);
      if (i === all.length - 1) u.onend = () => (setSpeaking(false), setLine(-1));
      ss.speak(u);
    });
    if (brief?.tip) {
      const tip = new SpeechSynthesisUtterance(`Tip: ${brief.tip}`);
      tip.onstart = () => setLine(all.length);
      tip.onend = () => (setSpeaking(false), setLine(-1));
      ss.speak(tip);
    }
  };

  const Lines = ({ items, start, dot }: { items: string[]; start: number; dot: string }) => (
    <ul className="flex flex-col">
      {items.map((t, i) => (
        <li key={i} className={`nh-tv-bline ${line === start + i ? "is-on" : ""}`}>
          <span className="mt-[7px] h-[6px] w-[6px] shrink-0 rounded-full" style={{ background: dot }} />
          <span>{t}</span>
        </li>
      ))}
    </ul>
  );

  return (
    <section className="nh-tv-card nh-tv-up flex min-h-0 flex-col gap-2.5 px-[18px] py-4" style={{ animationDelay: ".15s" }}>
      <CardHead
        tone="violet"
        Icon={Sparkles}
        title="Daily brief"
        sub={`Checked ${plural(counts.activeStudents, "student")}, ${plural(data.scores.length, "quiz")} and ${plural(counts.pendingRequests, "request")}`}
        right={
          <div className="flex shrink-0 items-center gap-2">
            <button type="button" onClick={speak} className={`nh-tv-say ${speaking ? "is-on" : ""}`} title={speaking ? "Stop reading" : "Read the brief aloud"}>
              {speaking ? <Square className="h-3.5 w-3.5 fill-current" /> : <Volume2 className="h-4 w-4" />} {speaking ? "Stop" : "Listen"}
            </button>
            <button type="button" onClick={refresh} disabled={spin || q.loading} className="nh-tv-navbtn" aria-label="Write a fresh brief" title="Write a fresh brief">
              <RefreshCw className={`h-4 w-4 ${spin ? "animate-spin" : ""}`} />
            </button>
          </div>
        }
      />
      <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto pr-0.5">
      <div className="nh-tv-box"><Lines items={info} start={0} dot="#2E3238" /></div>
      {q.loading && !brief ? (
        <span className="nh-sk block h-24 rounded-xl" />
      ) : (
        <>
          {risk.length > 0 && (
            <div className="nh-tv-box">
              <p className="nh-tv-boxhead text-[#C2352B]"><ShieldAlert className="h-3.5 w-3.5" /> Students at risk &amp; follow-up</p>
              <Lines items={risk} start={info.length} dot="#C2352B" />
            </div>
          )}
          {good.length > 0 && (
            <div className="nh-tv-box">
              <p className="nh-tv-boxhead text-[#1E7A4E]"><CheckCircle2 className="h-3.5 w-3.5" /> Going well</p>
              <Lines items={good} start={info.length + risk.length} dot="#2FA36B" />
            </div>
          )}
          {brief?.tip && (
            <p className={`flex items-start gap-2 rounded-[13px] border border-[#F6E2B5] bg-[#FFF8E8] px-3.5 py-2.5 text-[13px] leading-relaxed text-[#4A3B12] ${line === all.length ? "ring-2 ring-[#F5B400]/50" : ""}`}>
              <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-[#D99A00]" />
              <span><b>Tip:</b> {brief.tip}</span>
            </p>
          )}
          {q.error && !brief && <p className="text-[12.5px] text-[#6B6F76]">The AI brief is not available right now.</p>}
        </>
      )}
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- journey + month */

function JourneyCard({ j }: { j: Dashboard["journey"] }) {
  const steps: [string, number, LucideIcon][] = [
    ["Requested", j.requested, Inbox], ["Accepted", j.accepted, CheckCircle2], ["Booked", j.booked, CalendarCheck], ["Taught", j.taught, GraduationCap], ["Rated you", j.rated, Star],
  ];
  const pct = (a: number, b: number) => (b ? Math.min(100, Math.round((a / b) * 100)) : 0);
  const bars: [string, number, string][] = [
    ["Accept rate", pct(j.accepted, j.requested), "from-[#7DBDF5] to-[#1572C9]"],
    ["Booked a class", pct(j.booked, j.accepted), "from-[#C4B3FF] to-[#6D4AE0]"],
    ["Came back again", pct(j.cameBack, j.taught), "from-[#86E3C4] to-[#18936A]"],
  ];
  return (
    <section className="nh-tv-card nh-tv-up flex flex-col gap-3 px-[18px] py-4" style={{ animationDelay: ".2s" }}>
      <CardHead tone="teal" Icon={TrendingUp} title="Student journey" sub="How many students reach each step with you" href={ROUTES.tutor.reports} linkLabel="Reports" />
      <div className="relative grid grid-cols-5 gap-1 pt-1">
        <span className="nh-tv-dash absolute left-[10%] right-[10%] top-[24px] hidden sm:block" aria-hidden="true" />
        {steps.map(([label, n, Icon], i) => (
          <div key={label} className="relative flex flex-col items-center gap-0.5 text-center">
            <span className={`relative flex h-[42px] w-[42px] items-center justify-center rounded-[13px] ${i === 0 ? "nh-tv-blue text-white shadow-[0_8px_18px_-8px_rgba(21,114,201,.7)]" : "border border-[#E2DCD7] bg-white text-[#1572C9]"}`}>
              <Icon className="h-[18px] w-[18px]" strokeWidth={1.9} />
              <span className="absolute -right-2 -top-2 flex h-[19px] w-[19px] items-center justify-center rounded-full bg-[#1B1F24] text-[11px] font-bold text-white">{i + 1}</span>
            </span>
            <b className="mt-1 text-[19px] leading-none text-[#1B1F24]"><CountUp value={n} /></b>
            <span className="text-[11.5px] text-[#6B6F76]">{label}</span>
          </div>
        ))}
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {bars.map(([label, v, grad]) => (
          <div key={label} className="nh-tv-row px-3 py-2">
            <div className="flex items-center justify-between">
              <span className="text-[10.5px] font-bold uppercase tracking-[0.1em] text-[#3B4047]">{label}</span>
              <b className="text-[14.5px] text-[#1B1F24]">{v}%</b>
            </div>
            <span className="mt-1.5 block h-[5px] overflow-hidden rounded-full bg-[#EFEBE7]">
              <span className={`nh-tv-bar block h-full rounded-full bg-gradient-to-r ${grad}`} style={{ width: `${v}%` }} />
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function MonthCard({ m }: { m: Dashboard["month"] }) {
  const [all, setAll] = useState(false);
  const rows: [Tone, LucideIcon, string, React.ReactNode, string, string][] = [
    ["blue", Video, "Sessions taught", <CountUp key="s" value={m.sessionsTaught} />, "Classes finished this month", ROUTES.tutor.schedule],
    ["amber", Star, "Avg rating", m.rating === null ? "—" : <><CountUp value={m.rating} decimals={1} /><span className="ml-1 text-[12.5px] font-normal text-[#6B6F76]">/ 5.0</span></>,
      m.ratingCount ? `From ${plural(m.ratingCount, "review")} this month` : "No reviews this month yet", ROUTES.tutor.reviews],
    ["teal", Timer, "Teaching hours", <><CountUp value={m.hours} decimals={m.hours % 1 ? 1 : 0} /><span className="ml-1 text-[12.5px] font-normal text-[#6B6F76]">h</span></>, "Live time this month", ROUTES.tutor.earnings],
  ];
  const SHOW = 2;
  const shown = all ? rows : rows.slice(0, SHOW);
  return (
    <section className="nh-tv-card nh-tv-up flex flex-col gap-2 px-[18px] py-4" style={{ animationDelay: ".25s" }}>
      <CardHead tone="amber" Icon={LineChart} title="This month" sub="Sessions, rating and teaching hours" href={ROUTES.tutor.earnings} linkLabel="Earnings" />
      <div className="mt-1 flex flex-col gap-2">
        {shown.map(([tone, Icon, label, value, note, href]) => (
          <Link key={label} href={href} className="nh-tv-row nh-tv-lift flex items-center gap-3 px-3 py-2">
            <Tile tone={tone} Icon={Icon} size={34} />
            <span className="min-w-0 flex-1">
              <span className="block text-[10px] font-bold uppercase tracking-[0.1em] text-[#3B4047]">{label}</span>
              <span className="flex min-w-0 items-baseline gap-2">
                <b className="text-[19px] leading-tight text-[#1B1F24]">{value}</b>
                <span className="truncate text-[11.5px] text-[#6B6F76]">{note}</span>
              </span>
            </span>
            <span className="nh-tv-arrow"><ArrowUpRight className="h-3.5 w-3.5" /></span>
          </Link>
        ))}
      </div>
      {rows.length > SHOW ? (
        <button type="button" onClick={() => setAll((v) => !v)} aria-expanded={all} data-testid="month-more"
          className="nh-tv-pill mx-auto">
          {all ? "See less" : `See more (${rows.length - SHOW})`} <ChevronRight className={`h-3.5 w-3.5 transition ${all ? "-rotate-90" : "rotate-90"}`} />
        </button>
      ) : null}
    </section>
  );
}

/* ---------------------------------------------------------------- page */

export default function TutorDashboard() {
  const { tutorId } = useTutor();
  const { data, error, loading, reload } = useTutorQuery(() => tutorApi.dashboard(tutorId), [tutorId], { live: true });

  if (loading && !data) return <Loading label="Loading your dashboard…" variant="dashboard" />;
  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const { tutor, counts, sessions, scores, pendingRequests } = data;
  const now = Date.now();
  const todayK = dayKey();
  const todayList = sessions
    .filter((s) => s.status === "scheduled" && !s.ended && dayKey(new Date(s.startsAt ?? 0)) === todayK)
    .sort((a, b) => (a.startsAt ?? "").localeCompare(b.startsAt ?? ""));
  const next = sessions
    .filter((s) => s.status === "scheduled" && !s.outcome && !s.ended && new Date(s.startsAt ?? 0).getTime() + s.durationMin * 60000 > now)
    .sort((a, b) => (a.startsAt ?? "").localeCompare(b.startsAt ?? ""))[0];
  const avgScore = scores.length ? Math.round(scores.reduce((a, s) => a + s.scorePct, 0) / scores.length) : null;
  const seatsLeft = Math.max(0, tutor.capacity - counts.activeStudents);


  return (
    <div className="nh-tv flex flex-col gap-3.5">
      {/* four numbers */}
      <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
        <Link href={ROUTES.tutor.schedule} className="nh-tv-hero nh-tv-lift nh-tv-up !min-h-[104px] !justify-between !gap-2 !px-4 !py-3.5">
          <span className="nh-tv-shine" />
          <span className="nh-tv-ring" aria-hidden="true" />
          <div className="relative flex items-center gap-2.5">
            <span className="flex h-[30px] w-[30px] items-center justify-center rounded-[10px] border border-white/30 bg-white/15"><Video className="h-4 w-4" /></span>
            <span className="flex-1 text-[11.5px] font-bold uppercase tracking-[0.12em]">Today’s sessions</span>
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white/20"><ArrowUpRight className="h-3.5 w-3.5" /></span>
          </div>
          <span className="relative flex items-baseline gap-3">
            <b className="text-[30px] font-semibold leading-none"><CountUp value={todayList.length} /></b>
            <span className="flex min-w-0 items-center gap-2 truncate text-[12.5px] text-[#DCEBFF]">
              {next ? <><span className="h-[7px] w-[7px] shrink-0 rounded-full bg-[#5FE3A1]" /> Next: {next.studentName} at {timeText(next.startsAt)}</> : "No more classes booked"}
            </span>
          </span>
        </Link>

        <StatCard tone="violet" Icon={Inbox} label="New requests" href={ROUTES.tutor.requests} delay={0.05}>
          <span className="flex min-w-0 items-baseline gap-3">
            <b className="text-[30px] font-semibold leading-none text-[#1B1F24]"><CountUp value={counts.pendingRequests} /></b>
            <span className="truncate text-[12.5px] text-[#6B6F76]">{counts.acceptanceRate === null ? "No decisions yet" : `${counts.acceptanceRate}% acceptance rate`}</span>
          </span>
          <div className="flex items-end">
            <span className="flex -space-x-2">
              {pendingRequests.slice(0, 3).map((r) => (
                <PersonPhoto key={r.id} kind="student" id={r.userId} name={r.student.name} className={`h-7 w-7 border-2 border-[#FAF8F6] text-[10px] ${PHOTO}`} />
              ))}
            </span>
          </div>
        </StatCard>

        <StatCard tone="teal" Icon={Users} label="Active students" href={ROUTES.tutor.students} delay={0.1}>
          <span className="flex min-w-0 items-baseline gap-3">
            <b className="text-[30px] font-semibold leading-none text-[#1B1F24]"><CountUp value={counts.activeStudents} /></b>
            <span className="truncate text-[12.5px] text-[#6B6F76]">{seatsLeft ? `${plural(seatsLeft, "open seat")} left` : "Fully booked"}</span>
          </span>
          <div className="flex items-end">
            <span className="w-[80px] text-right">
              <span className="text-[11px] text-[#6B6F76]">{counts.activeStudents} / {tutor.capacity} seats</span>
              <span className="mt-1 block h-[6px] overflow-hidden rounded-full bg-[#EFEBE7]">
                <span className="nh-tv-bar block h-full rounded-full bg-gradient-to-r from-[#6FE3BB] to-[#18936A]" style={{ width: `${tutor.capacity ? Math.min(100, (counts.activeStudents / tutor.capacity) * 100) : 0}%` }} />
              </span>
            </span>
          </div>
        </StatCard>

        <StatCard tone="amber" Icon={LineChart} label="Avg quiz score" href={ROUTES.tutor.students} delay={0.15}>
          <span className="flex min-w-0 items-baseline gap-3">
            <b className="text-[30px] font-semibold leading-none text-[#1B1F24]">
              {avgScore === null ? "—" : <><CountUp value={avgScore} /><span className="ml-1 text-[14px] font-normal text-[#6B6F76]">%</span></>}
            </b>
            <span className="truncate text-[12.5px] text-[#6B6F76]">{scores.length ? `From ${plural(scores.length, "quiz")}` : "No quizzes taken yet"}</span>
          </span>
          <div className="flex items-end">
            <Spark values={scores.slice(-10).map((s) => s.scorePct)} />
          </div>
        </StatCard>
      </div>

      <div className="grid items-stretch gap-3.5 xl:h-[306px] xl:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <ScheduleCard sessions={sessions} />
        <BriefCard tutorId={tutorId} data={data} todayList={todayList} />
      </div>

      <div className="grid items-stretch gap-3.5 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <JourneyCard j={data.journey} />
        <MonthCard m={data.month} />
      </div>
    </div>
  );
}
