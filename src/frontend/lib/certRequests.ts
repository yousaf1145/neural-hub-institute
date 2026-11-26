"use client";

/**
 * Certificate requests (backend modules/certificates/requests.py).
 * video course: student asks -> admin approves -> certificate
 * live course:  student asks -> tutor recommends (or "not yet") -> admin approves -> certificate
 */
import { API_BASE, ApiError } from "@/lib/api";

export type CertReqStatus = "tutor_review" | "admin_review" | "issued" | "rejected" | "not_yet";
export type Person = { id: string; publicId: string; name: string };

export type CertRequest = {
  id: string; // CR-XXXXXXX
  kind: "video" | "live";
  status: CertReqStatus;
  stage: string;
  student: Person;
  tutor: Person;
  course: { key: string; title: string };
  summary: {
    done?: number; total?: number; watchedSeconds?: number; courseSeconds?: number;
    attendancePct?: number; attended?: number; held?: number; hours?: number;
    lecturesDone?: number | null; lecturesTotal?: number | null;
  };
  progressPct: number | null;
  flags: { code: string; text: string }[];
  grade: string;
  tutorRemarks: string;
  tutorAt: string | null;
  adminBy: string;
  adminNote: string;
  adminAt: string | null;
  reason: string;
  certificateId: string;
  createdAt: string | null;
  updatedAt: string | null;
  waitingHours: number;
  report?: CertReport;
  history?: { at: string; by: string; action: string; note: string }[];
};

export type ClassRow = {
  id: string; topic: string; startsAt: string | null; durationMin: number;
  status: "attended" | "missed" | "cancelled" | "upcoming";
  minutes: number | null; outcome: string | null; notes: string; summary: string; joins: number;
};
export type VideoRow = {
  id: string; title: string; duration: number; watched: number; watchedPct: number; furthestPct: number;
  completed: boolean; done: boolean; startedAt: string | null; lastWatchedAt: string | null;
};
export type CertReport = {
  kind: "video" | "live";
  rule: { watchPct?: number; attendancePct?: number; minClasses?: number };
  course: { id?: string; key?: string; title: string; videos?: number; seconds?: number; price?: number; currency?: string; studySetId?: string };
  tutor: Person & { email: string; subject: string; verified: boolean; rating: number };
  student: Person & { email: string; level: string; joinedAt: string | null };
  access?: { open: boolean; free: boolean; purchase: { at: string | null; amount: number; currency: string; method: string } | null };
  videos?: VideoRow[];
  done?: number; total?: number; watchedSeconds?: number; courseSeconds?: number;
  classes?: ClassRow[];
  counts?: { attended: number; missed: number; cancelled: number; upcoming: number; booked: number; held: number };
  attendancePct?: number; hours?: number;
  syllabus?: { lecturesDone: number; lecturesTotal: number; pct: number;
               courses: { id: string; title: string; done: number; total: number; quizzes: { lecture: number; attempts: number; best: number; passed: boolean }[] }[] } | null;
  courseFinished?: boolean;
  progressPct: number;
  startedAt: string | null; lastActivityAt?: string | null; lastClassAt?: string | null;
  eligible: boolean; missing: string[]; at: string;
};

/** A course on the student's Certificates page: ready or not, and its latest request. */
export type CertCourse = {
  kind: "video" | "live";
  key: string;
  title: string;
  tutor: Person;
  eligible: boolean;
  missing: string[];
  progressPct: number;
  attendancePct?: number;
  /** live course with a teacher's course: lectures the teacher marked done / lectures in the course */
  lecturesDone?: number | null;
  lecturesTotal?: number | null;
  /** quizzes the tutor sent from a live class: how many, how many passed, the average best score */
  quizzesSent?: number | null;
  quizzesPassed?: number | null;
  quizAvg?: number | null;
  /** the teacher's course behind a live course (to open it) */
  courseId?: string | null;
  /** live course: classes needed for the certificate */
  minClasses?: number | null;
  classes?: { attended: number; held: number; missed: number; upcoming: number; booked?: number; cancelled?: number };
  done?: number;
  total?: number;
  request: CertRequest | null;
};

const enc = encodeURIComponent;

async function call<T>(path: string, method: "GET" | "POST" = "GET", body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      cache: "no-store",
      ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    });
  } catch {
    throw new ApiError("Could not reach the Neural Hub Institute backend. Make sure the backend is running.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(typeof data?.detail === "string" ? data.detail : `Request failed (${res.status}).`, res.status);
  return data as T;
}

const S = (uid: string) => `/api/certificates/requests/student/${enc(uid)}`;
const T = (tid: string) => `/api/tutor/${enc(tid)}/certificate-requests`;

export const certRequestApi = {
  mine: (uid: string) => call<{ requests: CertRequest[]; courses: CertCourse[] }>(S(uid)),
  video: (uid: string, courseId: string) =>
    call<{ eligible: boolean; missing: string[]; done: number; total: number; rule: { watchPct: number }; request: CertRequest | null }>(
      `${S(uid)}/video/${enc(courseId)}`,
    ),
  askVideo: (uid: string, courseId: string) => call<{ request: CertRequest }>(S(uid), "POST", { kind: "video", courseId }),
  askLive: (uid: string, tutorId: string, courseKey: string) =>
    call<{ request: CertRequest }>(S(uid), "POST", { kind: "live", tutorId, courseKey }),
  myId: (uid: string) => call<{ userId: string; publicId: string; name: string }>(`/api/portal/me/${enc(uid)}`),
  // tutor
  tutorList: (tid: string, status = "waiting", q = "") =>
    call<{ items: CertRequest[]; counts: Record<"waiting" | "sent" | "issued" | "closed" | "all", number> }>(
      `${T(tid)}?status=${enc(status)}&q=${enc(q)}`,
    ),
  tutorGet: (tid: string, rid: string) => call<{ request: CertRequest; grades: string[] }>(`${T(tid)}/${enc(rid)}`),
  tutorDecide: (tid: string, rid: string, b: { decision: "approve" | "not_yet" | "reject"; grade?: string; remarks?: string }) =>
    call<{ request: CertRequest }>(`${T(tid)}/${enc(rid)}/decision`, "POST", b),
};

/** The steps a student sees for one request. */
export function steps(kind: "video" | "live", status: CertReqStatus | null) {
  const names = kind === "live" ? ["Requested", "Teacher review", "Admin review", "Certificate ready"] : ["Requested", "Admin review", "Certificate ready"];
  const at =
    status === null ? -1
    : status === "issued" ? names.length - 1
    : status === "admin_review" ? names.length - 2
    : status === "tutor_review" ? 1
    : 0;
  return names.map((n, i) => ({ name: n, done: i < at || (status === "issued" && i === at), current: i === at && status !== "issued" }));
}

export const fmtHours = (s?: number) => (s === undefined ? "–" : s >= 3600 ? `${(s / 3600).toFixed(1)} h` : `${Math.round(s / 60)} min`);
