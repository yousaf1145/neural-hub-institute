"use client";

/**
 * Student Home v3 (canvas "Student Dashboard · Rearranged", layout 1 + Film C).
 * One screen, no scroll. Every card is a link. Today's plan is built from real data:
 * live classes coming up today, open lecture quizzes, and the next lecture to continue.
 */
import LearningPath from "./LearningPath";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Award, BookOpen, CalendarDays, ClipboardCheck, Play, Search, Video } from "lucide-react";
import { JourneyDrawing, StudentAtDesk } from "../v2/Drawings";
import HowItWorksFilm from "./HowItWorksFilm";
import RealTeacherCard from "../../shared/RealTeacherCard";
import { ROUTES } from "@/lib/routes";

export type TodayItem = {
  kind: "class" | "quiz" | "lecture";
  title: string;
  sub: string;
  href: string;
  /** when it starts (classes) or is due (quizzes) */
  at?: string;
};

export type DashboardV3Props = {
  name: string;
  userId: string;
  inProgress?: { title: string; next: string; href: string };
  courses: number;
  goalPct: number;
  avg: number | null;
  scores: number[];
  certificates: number;
  streak: number;
  today: TodayItem[];
};

const INK = "#1E2A38";
const SLATE = "#2F3E4E";
const MANGO = "#E8893A";
const card = "nh3-card rounded-[20px] border border-[#E8EAEE] bg-white shadow-[0_1px_2px_rgba(30,42,56,0.04),0_10px_26px_-18px_rgba(30,42,56,0.25)]";
const caps = "text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]";

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
};

export default function DashboardV3(p: DashboardV3Props) {
  return (
    <div className="nh-v3 nh-keep-light flex flex-col gap-4 text-[#1E2A38] xl:h-[calc(100vh-150px)] xl:min-h-[620px]">
      <section aria-label="Overview" className="grid shrink-0 grid-cols-1 gap-4 md:grid-cols-2 xl:h-[31%] xl:grid-cols-[minmax(0,2.05fr)_minmax(0,1fr)_minmax(0,1.1fr)]">
        <Hero {...p} />
        <LearningPath userId={p.userId} />
        <TeacherCard />
      </section>
      <section aria-label="Today" className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.12fr)]">
        <div className="grid min-h-0 grid-cols-1 gap-4 sm:grid-cols-2 sm:grid-rows-2">
          <TodayCard items={p.today} />
          <QuizCard avg={p.avg} scores={p.scores} />
          <KeepGoingCard />
          <JourneyCard inProgress={p.inProgress} pct={p.goalPct} certificates={p.certificates} />
        </div>
        <Monitor />
      </section>
    </div>
  );
}

/* ---------------- Row 1 ---------------- */

function Hero({ name, inProgress, courses }: DashboardV3Props) {
  const first = name.split(" ")[0] || name;
  const headline = inProgress ? `${inProgress.next} is waiting.` : courses ? "Ready for your next lecture?" : "Learn any topic with a real teacher.";
  return (
    <div className="nh3-card relative flex min-h-[190px] flex-col justify-center gap-3 overflow-hidden rounded-[22px] border border-[#F1E2D2] bg-[#FBF3EA] px-7 py-5 md:col-span-2 xl:col-span-1">
      <svg aria-hidden width="300" height="300" viewBox="0 0 300 300" fill="none" className="pointer-events-none absolute -bottom-[130px] right-[150px]">
        <circle cx="150" cy="150" r="148" stroke="#EBDCCB" strokeWidth="1.5" />
        <circle cx="150" cy="150" r="98" stroke="#EBDCCB" strokeWidth="1.5" />
      </svg>
      {/* books + lamp drawing */}
      <svg aria-hidden viewBox="0 0 200 150" className="pointer-events-none absolute bottom-0 right-3 hidden h-[76%] sm:block">
        <ellipse cx="100" cy="142" rx="90" ry="6" fill="#EBDCCB" />
        <rect x="30" y="112" width="120" height="16" rx="3" fill={SLATE} />
        <rect x="38" y="96" width="104" height="16" rx="3" fill={MANGO} />
        <rect x="26" y="128" width="132" height="12" rx="3" fill="#3B4D60" />
        <path d="M44 100h70M40 116h84" stroke="#FFFFFF" strokeOpacity=".5" strokeWidth="2" strokeLinecap="round" />
        <g style={{ transformOrigin: "120px 70px", animation: "nh3Float 3s ease-in-out infinite" }}>
          <path d="M92 88c0-14 12-22 28-22s28 8 28 22z" fill="#FFFFFF" stroke={SLATE} strokeWidth="3" />
          <path d="M120 66V50" stroke={SLATE} strokeWidth="3" />
          <path d="M106 88c4 6 24 6 28 0" fill="none" stroke={MANGO} strokeWidth="3" />
        </g>
        <g>
          <path d="M160 96l10-40 6 2-10 40z" fill="#F2C14E" />
          <path d="M170 56l3-8 3 10z" fill={INK} />
        </g>
        {[[40, 40], [70, 22], [178, 30]].map(([x, y], i) => (
          <path key={i} d={`M${x} ${y - 6}v12M${x - 6} ${y}h12`} stroke={MANGO} strokeWidth="2.5" strokeLinecap="round" style={{ transformOrigin: `${x}px ${y}px`, animation: `nh3Spark 2.4s ease-in-out ${i * 0.6}s infinite` }} />
        ))}
      </svg>
      <span className="relative inline-flex h-8 items-center gap-2 self-start rounded-full border border-[#F1E2D2] bg-white px-3 text-[12.5px] font-medium text-[#3C4A5A]">
        <CalendarDays className="h-[14px] w-[14px] text-[#2F3E4E]" />
        {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
      </span>
      <h1 className="relative m-0 max-w-[60%] font-display text-[clamp(20px,1.85vw,28px)] font-semibold leading-[1.1] tracking-[-0.015em]">
        {greeting()}, {first}.
        <br />
        <span className="text-[#2F3E4E]">{headline}</span>
      </h1>
      <div className="relative flex flex-wrap gap-2.5">
        <Link href={inProgress?.href ?? ROUTES.student.courses} className="inline-flex h-10 items-center gap-2 rounded-[12px] bg-[linear-gradient(90deg,#B06D45,#8E5233)] px-5 text-[14px] font-semibold text-white transition hover:brightness-110">
          {inProgress ? <><Play className="h-4 w-4" /> Continue</> : <>Explore courses <ArrowRight className="h-4 w-4" /></>}
        </Link>
        <Link href={ROUTES.student.tutors} className="inline-flex h-10 items-center gap-2 rounded-[12px] border border-[#E3D3C1] bg-white px-5 text-[14px] font-semibold text-[#1E2A38] transition hover:border-[#2F3E4E]">
          <Search className="h-4 w-4" /> Find a tutor
        </Link>
      </div>
    </div>
  );
}

function TeacherCard() {
  return <RealTeacherCard />;
}

/* ---------------- Row 2 ---------------- */

const KIND = {
  class: { icon: Video, c: "#E0533D", label: "Live class" },
  quiz: { icon: ClipboardCheck, c: MANGO, label: "Quiz" },
  lecture: { icon: BookOpen, c: "#A8653F", label: "Lecture" },
} as const;

function until(at: string | undefined, now: number) {
  if (!at) return "";
  const ms = new Date(at).getTime() - now;
  if (ms <= 0) return "now";
  const m = Math.round(ms / 60000);
  return m < 60 ? `in ${m} min` : `in ${Math.floor(m / 60)}h ${m % 60}m`;
}

/** Today's plan: real items, the spotlight moves on by itself every few seconds. */
function TodayCard({ items }: { items: TodayItem[] }) {
  const [tick, setTick] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => { setTick((x) => x + 1); setNow(Date.now()); }, 3500);
    return () => window.clearInterval(t);
  }, []);
  const list = items.slice(0, 4);
  const active = list.length ? tick % list.length : 0;
  const d = new Date(now);
  const dayPct = Math.min(100, Math.max(0, ((d.getHours() * 60 + d.getMinutes() - 480) / (14 * 60)) * 100));
  const top = list[active];
  return (
    <div className={`${card} flex min-h-[220px] xl:min-h-0 flex-col gap-2 overflow-hidden p-4`}>
      <div className="flex items-center justify-between">
        <h2 className="m-0 font-display text-[18px] font-semibold">Today</h2>
        <span className="flex items-center gap-1.5 text-[11.5px] font-semibold text-[#6B7280]">
          <span className="h-2 w-2 rounded-full bg-[#3E9B6B]" style={{ animation: "nh3Live 1.6s ease-in-out infinite" }} /> auto
        </span>
      </div>
      <div className="relative h-1.5 rounded-full bg-[#EEF1F5]" aria-label="How much of the day has passed">
        <span className="absolute inset-y-0 left-0 rounded-full bg-[linear-gradient(90deg,#2F3E4E,#E8893A)]" style={{ width: `${dayPct}%` }} />
        <span className="absolute -top-[3px] h-3 w-3 -translate-x-1/2 rounded-full border-2 border-white bg-[#E8893A] shadow" style={{ left: `${dayPct}%` }} />
      </div>
      {list.length ? (
        <ul className="m-0 flex min-h-0 flex-1 list-none flex-col gap-1.5 p-0">
          {list.map((it, i) => {
            const k = KIND[it.kind];
            const on = i === active;
            return (
              <li key={`${it.kind}-${i}`}>
                <Link href={it.href} className={`flex items-center gap-2.5 rounded-[12px] px-2.5 py-1.5 transition-all duration-500 ${on ? "bg-[#FBF3EA] shadow-[inset_3px_0_0_#E8893A]" : "hover:bg-[#F5F6F8]"}`}>
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[9px] text-white" style={{ background: k.c, animation: on ? "nh3Pulse 1.8s ease-in-out infinite" : undefined }}>
                    <k.icon className="h-[14px] w-[14px]" />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-[13px] font-semibold">{it.title}</span>
                    <span className="truncate text-[11.5px] text-[#6B7280]">{it.sub}</span>
                  </span>
                  {it.at && <span className="shrink-0 text-[11px] font-semibold text-[#9A4F12]">{until(it.at, now)}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      ) : (
        <Link href={ROUTES.student.tutors} className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
          <svg viewBox="0 0 80 60" className="h-14" aria-hidden>
            <rect x="10" y="10" width="60" height="44" rx="6" fill="#FBF3EA" stroke={SLATE} strokeWidth="2.5" />
            <path d="M10 22h60M26 6v10M54 6v10" stroke={SLATE} strokeWidth="2.5" strokeLinecap="round" />
            <path d="M30 38l7 7 14-14" fill="none" stroke={MANGO} strokeWidth="3" strokeLinecap="round" style={{ strokeDasharray: 40, animation: "nh3Draw 3s ease-in-out infinite" }} />
          </svg>
          <span className="text-[13px] font-semibold">All clear today</span>
          <span className="text-[12px] text-[#6B7280]">Book a class with a teacher</span>
        </Link>
      )}
      {top && <span key={active} className="sr-only" aria-live="polite">{KIND[top.kind].label}: {top.title}</span>}
    </div>
  );
}

function QuizCard({ avg, scores }: { avg: number | null; scores: number[] }) {
  const a = avg ?? 0;
  return (
    <Link href={ROUTES.student.assessments} className={`${card} relative flex min-h-[220px] xl:min-h-0 flex-col gap-2 overflow-hidden p-4`}>
      <div className="flex items-center justify-between">
        <h2 className="m-0 font-display text-[18px] font-semibold">Quiz score</h2>
        <ArrowRight className="h-4 w-4 text-[#6B7280]" />
      </div>
      <div className="flex flex-1 items-center gap-3">
        <div className="relative h-[96px] w-[96px] shrink-0">
          <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90" aria-hidden>
            <circle cx="50" cy="50" r="42" fill="none" stroke="#F1E7DB" strokeWidth="10" />
            <circle cx="50" cy="50" r="42" fill="none" stroke={MANGO} strokeWidth="10" strokeLinecap="round" strokeDasharray="264" strokeDashoffset={264 - (264 * a) / 100} style={{ animation: "nh3Ring 1.4s cubic-bezier(.2,.8,.2,1) both" }} />
          </svg>
          <span className="absolute inset-0 flex flex-col items-center justify-center">
            <strong className="font-display text-[22px] leading-none">{avg === null ? "–" : `${a}%`}</strong>
            <span className="text-[10px] text-[#6B7280]">average</span>
          </span>
        </div>
        {/* trophy */}
        <svg viewBox="0 0 70 80" className="h-[96px] flex-1" aria-hidden style={{ animation: "nh3Float 3s ease-in-out infinite" }}>
          <path d="M18 8h34v18a17 17 0 0 1-34 0z" fill="#F2C14E" stroke="#B9822A" strokeWidth="2" />
          <path d="M18 14H8c0 10 5 16 12 16M52 14h10c0 10-5 16-12 16" fill="none" stroke="#B9822A" strokeWidth="2.5" />
          <rect x="30" y="42" width="10" height="12" fill="#B9822A" />
          <rect x="20" y="54" width="30" height="9" rx="2" fill="#8E5233" />
          <path d="M35 14l3 6 6 1-4 4 1 6-6-3-6 3 1-6-4-4 6-1z" fill="#FFFFFF" />
          <path d="M10 70h50" stroke="#EFE6DA" strokeWidth="3" strokeLinecap="round" />
        </svg>
      </div>
      {/* quick numbers instead of the old coloured bars */}
      <div className="grid grid-cols-3 gap-1.5" data-testid="quiz-stats">
        {[
          ["Taken", scores.length ? String(scores.length) : "0"],
          ["Best", scores.length ? `${Math.max(...scores)}%` : "–"],
          ["Last", scores.length ? `${scores[scores.length - 1]}%` : "–"],
        ].map(([k, v], i) => (
          <span key={k} className="flex flex-col items-center rounded-xl border border-[#F1E7DB] bg-[#FFFBF6] py-1.5" style={{ animation: `nh3Rise .6s ease ${i * 0.08}s both` }}>
            <strong className="font-display text-[15px] leading-tight text-[#7A4527]">{v}</strong>
            <span className="text-[10px] font-semibold uppercase tracking-[.08em] text-[#8F8984]">{k}</span>
          </span>
        ))}
      </div>
    </Link>
  );
}

const TIPS = [
  "Ten minutes a day beats one long night.",
  "Ask your teacher one question every class.",
  "Do the quiz right after the lecture.",
  "Explain it to a friend to really learn it.",
];

function KeepGoingCard() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setI((x) => (x + 1) % TIPS.length), 6000);
    return () => window.clearInterval(t);
  }, []);
  return (
    <Link href={ROUTES.student.courses} className={`${card} relative flex min-h-[220px] xl:min-h-0 flex-col overflow-hidden bg-[linear-gradient(180deg,#FFFFFF_40%,#FBF3EA)] p-4`}>
      <h2 className="m-0 font-display text-[18px] font-semibold">Keep going</h2>
      <div className="flex min-h-0 flex-1 items-center justify-center">
        <StudentAtDesk className="h-full max-h-[130px] w-auto" />
      </div>
      <p key={i} className="m-0 min-h-[34px] text-[12.5px] leading-snug text-[#3C4A5A]" style={{ animation: "nh3Fade .5s ease both" }}>{TIPS[i]}</p>
      <span className="mt-1 flex gap-1" aria-hidden>
        {TIPS.map((_, k) => <span key={k} className={`h-1.5 rounded-full transition-all ${k === i ? "w-5 bg-[#E8893A]" : "w-1.5 bg-[#D9DEE5]"}`} />)}
      </span>
    </Link>
  );
}

function JourneyCard({ inProgress, pct, certificates }: { inProgress?: DashboardV3Props["inProgress"]; pct: number; certificates: number }) {
  return (
    <Link href={inProgress?.href ?? ROUTES.student.courses} className={`${card} relative flex min-h-[220px] xl:min-h-0 flex-col overflow-hidden p-4`}>
      <div className="flex items-center justify-between">
        <h2 className="m-0 font-display text-[18px] font-semibold">My journey</h2>
        <span className="rounded-full bg-[#EEF1F5] px-2 py-0.5 text-[11.5px] font-bold text-[#2F3E4E]">{pct}%</span>
      </div>
      <div className="flex min-h-0 flex-1 items-center justify-center">
        <JourneyDrawing className="h-full max-h-[120px] w-auto" />
      </div>
      <div className="h-1.5 rounded-full bg-[#EEF1F5]">
        <span className="block h-full rounded-full bg-[linear-gradient(90deg,#2F3E4E,#E8893A)] transition-all duration-1000" style={{ width: `${pct}%` }} />
      </div>
      <span className="mt-2 flex items-center justify-between text-[12px] text-[#6B7280]">
        <span className="truncate">{inProgress ? `${inProgress.title} · ${inProgress.next}` : "Start your first course"}</span>
        <span className="inline-flex shrink-0 items-center gap-1 font-semibold text-[#9A4F12]"><Award className="h-3.5 w-3.5" />{certificates}</span>
      </span>
    </Link>
  );
}

/** A PC monitor playing the "How it works" film. */
function Monitor() {
  return (
    <div className="flex min-h-[300px] flex-col items-center justify-center rounded-[22px] border border-[#E8EAEE] bg-[linear-gradient(180deg,#F5F6F8,#EEF1F5)] p-4">
      <div className="flex w-full max-w-[720px] flex-1 flex-col items-center">
        <div className="relative w-full flex-1 rounded-[14px] bg-[#1E2A38] p-[10px] shadow-[0_24px_40px_-24px_rgba(30,42,56,0.9)]" style={{ maxHeight: "calc(100% - 46px)" }}>
          <span aria-hidden className="absolute left-1/2 top-[3px] h-1 w-1 -translate-x-1/2 rounded-full bg-[#56687C]" />
          <div className="h-full min-h-[220px] w-full overflow-hidden rounded-[6px]">
            <HowItWorksFilm />
          </div>
        </div>
        <span aria-hidden className="h-[26px] w-[70px] bg-[linear-gradient(180deg,#3B4D60,#2B3644)] [clip-path:polygon(18%_0,82%_0,100%_100%,0_100%)]" />
        <span aria-hidden className="h-2 w-[180px] rounded-full bg-[#2B3644]" />
      </div>
    </div>
  );
}
