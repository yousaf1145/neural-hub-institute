"use client";

/**
 * Home · "Your path": the course the student is on now, as 5 steps on a curved road.
 *   live course   Joined → Lectures → Class quiz → Live classes → Certificate
 *   video course  Joined → Videos → Requested → Review → Certificate
 * Real data from /api/certificates/requests/student/{uid} (the same numbers as the Certificates page),
 * refreshed every minute and when the tab gets focus. A dot travels along the road to the next step.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { certRequestApi, type CertCourse } from "@/lib/certRequests";
import { ROUTES } from "@/lib/routes";

type Step = { label: string; sub: string; done: boolean };
export type PathView = { title: string; tutor: string; href: string; steps: Step[] };

/** Line-art scene (same style as the "My journey" / "Keep going" drawings): a dashed road with 5 stops. */
const INK = "#1E2A38";
const VB_W = 280, VB_H = 150;
const STOPS = [
  { x: 30, y: 112 },
  { x: 88, y: 58 },
  { x: 142, y: 104 },
  { x: 198, y: 50 },
  { x: 252, y: 92 },
];
const SEGS = STOPS.slice(1).map((b, i) => {
  const a = STOPS[i];
  const mx = (a.x + b.x) / 2;
  return `M${a.x} ${a.y} C${mx} ${a.y} ${mx} ${b.y} ${b.x} ${b.y}`;
});
const ROAD = `M${STOPS[0].x} ${STOPS[0].y}` + SEGS.map((d) => d.slice(d.indexOf("C") - 1)).join("");

type IconKind = "hello" | "screen" | "quiz" | "class" | "letter" | "review" | "cap";
function iconFor(label: string): IconKind {
  if (/joined|teacher/i.test(label)) return "hello";
  if (/lecture|video/i.test(label)) return "screen";
  if (/quiz/i.test(label)) return "quiz";
  if (/class/i.test(label)) return "class";
  if (/request/i.test(label)) return "letter";
  if (/review/i.test(label)) return "review";
  return "cap";
}

/** One small line drawing, centred on (0,0), about 30 px wide. */
function Icon({ kind }: { kind: IconKind }) {
  switch (kind) {
    case "hello": // a waving hand
      return (
        <g>
          <path d="M-6 10c-5-4-8-9-9-14 0-2 2-3 4-1l4 5V-9c0-2 3-2 3 0v7-10c0-2 3-2 3 0v10-8c0-2 3-2 3 0v9-6c0-2 3-2 3 0V3c0 5-3 9-8 9z" fill="#FFFFFF" />
          <path d="M9-15l3-3M12-10h4M-13-13l-3-3" stroke="#E8893A" />
        </g>
      );
    case "screen": // a video lecture
      return (
        <g>
          <rect x="-15" y="-11" width="30" height="20" rx="3" fill="#FFFFFF" />
          <path d="M-3-5v8l7-4z" fill="#E8893A" stroke="none" />
          <path d="M-5 13h10M0 9v4" />
        </g>
      );
    case "quiz": // a quiz sheet with a tick
      return (
        <g>
          <rect x="-10" y="-14" width="20" height="27" rx="2.5" fill="#FFFFFF" transform="rotate(-6)" />
          <path d="M-5-6h10M-5-1h10M-5 4h6" strokeWidth={1.2} transform="rotate(-6)" />
          <path d="M5 6l3 3 6-7" stroke="#E8893A" strokeWidth={2} />
        </g>
      );
    case "class": // a laptop with a teacher on screen
      return (
        <g>
          <rect x="-14" y="-12" width="28" height="18" rx="2.5" fill="#FFFFFF" />
          <circle cx="0" cy="-5.5" r="3" fill="#FDEEDD" />
          <path d="M-5 3c1-3 3-4 5-4s4 1 5 4" />
          <path d="M-18 9h36l-3 4h-30z" fill="#FFFFFF" />
        </g>
      );
    case "letter": // the certificate request
      return (
        <g>
          <rect x="-14" y="-9" width="28" height="19" rx="2.5" fill="#FFFFFF" />
          <path d="M-14-8l14 10 14-10" />
          <circle cx="12" cy="-10" r="3.5" fill="#E8893A" stroke="none" />
        </g>
      );
    case "review": // a magnifier over a page
      return (
        <g>
          <rect x="-13" y="-13" width="18" height="24" rx="2" fill="#FFFFFF" />
          <path d="M-9-6h10M-9-1h8" strokeWidth={1.2} />
          <circle cx="5" cy="4" r="6" fill="#FDEEDD" />
          <path d="M9 8l6 6" strokeWidth={2.2} />
        </g>
      );
    default: // graduation cap
      return (
        <g>
          <path d="M-16-3L0-10l16 7L0 4z" fill={INK} />
          <path d="M-9 0v7c0 2.5 4 4.5 9 4.5s9-2 9-4.5V0" fill="#FDEEDD" />
          <path d="M16-3v9" />
          <circle cx="16" cy="8" r="2" fill="#E8893A" stroke="none" />
        </g>
      );
  }
}

/** Turn one certificate course into the 5 steps. Exported for tests. */
export function pathFor(c: CertCourse): PathView {
  const r = c.request;
  const issued = r?.status === "issued";
  if (c.kind === "live") {
    const lt = c.lecturesTotal ?? 0;
    const ld = Math.min(c.lecturesDone ?? 0, lt || Infinity);
    const lecturesDone = ld >= lt;
    const qs = c.quizzesSent ?? 0;
    const qp = c.quizzesPassed ?? 0;
    const quizDone = qs > 0 ? qp >= qs : lecturesDone;
    const need = c.minClasses ?? 3;
    const att = c.classes?.attended ?? 0;
    const asked = !!r && r.status !== "rejected" && r.status !== "not_yet";
    const certSub = issued ? "ready" : asked ? "in review" : c.eligible ? "ask now" : "locked";
    if (lt === 0) {
      // a live course without the teacher's lecture plan: classes are the whole path
      const booked = (c.classes?.booked ?? 0) + (c.classes?.upcoming ?? 0);
      return {
        title: c.title,
        tutor: c.tutor?.name ?? "",
        href: c.eligible && !asked ? ROUTES.student.certificates : ROUTES.student.sessions,
        steps: [
          { label: "Joined", sub: "accepted", done: true },
          { label: "1st class", sub: att ? "attended" : booked ? "booked" : "book one", done: att > 0 || issued },
          { label: "Classes", sub: `${Math.min(att, need)}/${need}`, done: att >= need || issued },
          { label: "Request", sub: asked || issued ? "sent" : c.eligible ? "ask now" : `after ${need}`, done: asked || issued },
          { label: "Certificate", sub: certSub, done: issued },
        ],
      };
    }
    return {
      title: c.title,
      tutor: c.tutor?.name ?? "",
      href: c.courseId ? ROUTES.student.teacherCourse(c.courseId) : ROUTES.student.certificates,
      steps: [
        { label: "Joined", sub: "course", done: true },
        { label: "Lectures", sub: `${ld}/${lt}`, done: lecturesDone || issued },
        { label: "Quiz", sub: qs > 0 ? `${qp}/${qs}` : "none yet", done: quizDone || issued },
        { label: "Classes", sub: `${Math.min(att, need)}/${need}`, done: att >= need || issued },
        { label: "Certificate", sub: certSub, done: issued },
      ],
    };
  }
  const total = c.total ?? 0;
  const done = Math.min(c.done ?? 0, total || Infinity);
  const asked = !!r && r.status !== "rejected";
  return {
    title: c.title,
    tutor: c.tutor?.name ?? "",
    href: ROUTES.student.certificates,
    steps: [
      { label: "Joined", sub: "course", done: true },
      { label: "Videos", sub: total ? `${done}/${total}` : "—", done: c.eligible || (total > 0 && done >= total) || asked },
      { label: "Request", sub: asked ? "sent" : c.eligible ? "ask now" : "after videos", done: asked },
      { label: "Review", sub: issued ? "approved" : asked ? "waiting" : "—", done: issued },
      { label: "Certificate", sub: issued ? "ready" : "locked", done: issued },
    ],
  };
}

/** The course to show: an unfinished one with the most progress (live first), else the newest finished one. */
export function pickCourse(list: CertCourse[]): CertCourse | null {
  if (!list.length) return null;
  const open = list.filter((c) => c.request?.status !== "issued");
  const pool = open.length ? open : list;
  return [...pool].sort((a, b) => (b.progressPct ?? 0) - (a.progressPct ?? 0) || (a.kind === "live" ? -1 : 1))[0];
}

const EMPTY: PathView = {
  title: "Start with a teacher",
  tutor: "",
  href: ROUTES.student.tutors,
  steps: [
    { label: "Teacher", sub: "find one", done: false },
    { label: "Lectures", sub: "", done: false },
    { label: "Quiz", sub: "", done: false },
    { label: "Classes", sub: "", done: false },
    { label: "Certificate", sub: "", done: false },
  ],
};

export default function LearningPath({ userId }: { userId: string }) {
  const [view, setView] = useState<PathView | null>(null);
  const [seq, setSeq] = useState(0); // bumps on every load so the animation replays only when something changed

  useEffect(() => {
    if (!userId) return;
    let alive = true;
    let last = "";
    const load = () =>
      certRequestApi
        .mine(userId)
        .then((r) => {
          if (!alive) return;
          const c = pickCourse(r.courses);
          const v = c ? pathFor(c) : EMPTY;
          const key = JSON.stringify(v);
          if (key !== last) {
            last = key;
            setView(v);
            setSeq((n) => n + 1);
          }
        })
        .catch(() => alive && !last && setView(EMPTY));
    void load();
    const t = window.setInterval(load, 60_000);
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => {
      alive = false;
      window.clearInterval(t);
      window.removeEventListener("focus", onFocus);
    };
  }, [userId]);

  const v = view ?? EMPTY;
  const doneCount = v.steps.filter((s) => s.done).length;
  const current = v.steps.findIndex((s) => !s.done); // -1: all done

  // measure the road and each piece between two stops
  const road = useRef<SVGPathElement>(null);
  const segRefs = useRef<(SVGPathElement | null)[]>([]);
  const [len, setLen] = useState(0);
  const [cum, setCum] = useState<number[]>([0, 0, 0, 0, 0]);
  useEffect(() => {
    const p = road.current;
    if (!p) return;
    setLen(p.getTotalLength());
    const c = [0];
    segRefs.current.forEach((sp, i) => c.push(c[i] + (sp?.getTotalLength() ?? 0)));
    setCum(c);
  }, []);

  // a loop: the dot walks from icon to icon (a short stop on each), then starts again
  const MOVE = 900, STAY = 650, REST = 1100;
  const [d, setD] = useState(0);
  const [at, setAt] = useState(0);
  useEffect(() => {
    if (!len) return;
    if (typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const legs = STOPS.length - 1;
    const cycle = STAY + legs * (MOVE + STAY) + REST;
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      let t = (now - t0) % cycle;
      let dist = 0, stop = 0;
      if (t < STAY) { dist = 0; stop = 0; }
      else {
        t -= STAY;
        const leg = Math.min(legs - 1, Math.floor(t / (MOVE + STAY)));
        const inLeg = t - leg * (MOVE + STAY);
        if (t >= legs * (MOVE + STAY)) { dist = cum[legs]; stop = legs; }
        else if (inLeg < MOVE) {
          const k = inLeg / MOVE;
          const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
          dist = cum[leg] + (cum[leg + 1] - cum[leg]) * e; stop = -1;
        } else { dist = cum[leg + 1]; stop = leg + 1; }
      }
      setD(dist);
      setAt(stop);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [len, cum]);
  const dot = useMemo(() => {
    const p = road.current;
    if (!p || !len) return null;
    const pt = p.getPointAtLength(d);
    return { x: pt.x, y: pt.y };
  }, [d, len]);

  return (
    <Link
      href={v.href}
      aria-label={`Your path in ${v.title}: ${doneCount} of ${v.steps.length} steps done${current >= 0 ? `, next: ${v.steps[current].label}` : ""}`}
      data-testid="learning-path"
      className="nh3-card relative flex min-h-[190px] flex-col overflow-hidden rounded-[20px] border border-[#EFE6DA] bg-[linear-gradient(180deg,#FFFFFF_45%,#FBF3EA)] p-4 shadow-[0_1px_2px_rgba(60,40,20,0.04),0_10px_26px_-18px_rgba(60,40,20,0.25)] transition hover:shadow-[0_16px_30px_-20px_rgba(90,50,30,.55)]"
    >
      <h2 className="m-0 font-display text-[18px] font-semibold text-[#1E2A38]">Your path</h2>
      <div className="flex min-h-0 flex-1 items-center justify-center">
        <svg viewBox="0 18 282 128" className="h-full max-h-[170px] w-full" fill="none" stroke={INK} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          {SEGS.map((sd, i) => <path key={i} ref={(el) => { segRefs.current[i] = el; }} d={sd} stroke="none" />)}
          <path ref={road} d={ROAD} stroke="#2F3E4E" strokeDasharray="4 6" strokeWidth={1.6} />
          {STOPS.map((pt, i) => {
            const st = v.steps[i];
            const here = at === i;
            return (
              <g key={i} style={{ transform: here ? "scale(1.12)" : "none", transformOrigin: `${pt.x}px ${pt.y}px`, transformBox: "view-box", transition: "transform .35s ease" }}>
                <circle cx={pt.x} cy={pt.y} r="27" fill={here ? "#FDEEDD" : st.done ? "#FBF3EA" : "#FFFFFF"} stroke={here ? "#E8893A" : INK} strokeWidth={here ? 2 : 1.7} style={{ transition: "fill .35s, stroke .35s" }} />
                <g transform={`translate(${pt.x} ${pt.y}) scale(1.3)`}><Icon kind={iconFor(st.label)} /></g>
              </g>
            );
          })}
          {dot && at < 0 ? <circle cx={dot.x} cy={dot.y} r="5" fill="#E8893A" stroke="#FFFFFF" strokeWidth={2} /> : null}
        </svg>
      </div>
    </Link>
  );
}
