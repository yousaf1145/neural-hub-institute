"use client";

/**
 * Student Home. Students no longer make their own courses, so every number comes from their teachers' courses:
 *   Courses in progress  courses for this student (made for him / by his teachers / joined) + open courses he started
 *   % of goal / Lectures lectures his teachers have taught out of all lectures of those courses
 *   Avg quiz score       his best mark in each lecture quiz a teacher sent (class quizzes)
 *   Today                live classes today, open quizzes not done yet, the next lecture
 */
import { useEffect, useState } from "react";
import DashboardV3, { type TodayItem } from "./v3/DashboardV3";
import { meetApi, classPath, type MeetItem } from "@/lib/meet";
import { usePortal } from "@/lib/store/portal-store";
import { studyStreak } from "@/lib/store/selectors";
import { useSession } from "@/lib/auth/local-auth";
import { studentCourseApi, type ClassQuiz, type MyCourseCard } from "@/lib/courses";
import { ROUTES } from "@/lib/routes";

export default function DashboardView() {
  const { state } = usePortal();
  const { session } = useSession();
  const userId = session?.userId ?? "";
  const [courses, setCourses] = useState<MyCourseCard[]>([]);
  const [quizzes, setQuizzes] = useState<ClassQuiz[]>([]);
  const [classes, setClasses] = useState<MeetItem[]>([]);
  useEffect(() => {
    if (!userId) return;
    let alive = true;
    studentCourseApi.list(userId)
      .then((r) => alive && setCourses([...r.forMe, ...r.open.filter((c) => c.progress.lecturesDone > 0)]))
      .catch(() => {});
    studentCourseApi.classQuizzes(userId).then((r) => alive && setQuizzes(r.items)).catch(() => {});
    meetApi.home("student", userId).then((r) => alive && setClasses(r.upcoming)).catch(() => {});
    return () => {
      alive = false;
    };
  }, [userId]);
  const now = new Date();

  // ---- the teachers' courses ----
  let doneLectures = 0, totalLectures = 0, currentCourses = 0;
  courses.forEach((c) => {
    const total = Math.max(c.lectures, 1);
    const done = Math.min(c.progress.lecturesDone, total);
    doneLectures += done;
    totalLectures += total;
    if (done < total) currentCourses += 1;
  });
  const goalPct = totalLectures ? Math.round((doneLectures / totalLectures) * 100) : 0;
  // continue: a started, unfinished course first, else the newest unfinished one
  const next = courses.find((c) => c.progress.lecturesDone > 0 && c.progress.lecturesDone < c.lectures)
    ?? courses.find((c) => c.progress.lecturesDone < c.lectures);
  const inProgress = next
    ? { title: next.title, next: `Lecture ${next.progress.lecturesDone + 1}`, href: ROUTES.student.teacherCourse(next.id, next.progress.lecturesDone + 1) }
    : undefined;

  // ---- lecture quizzes the teachers sent ----
  const taken = quizzes.filter((q) => q.attemptsUsed > 0 && (q.best ?? q.lastScore) !== null)
    .sort((a, b) => (a.lastAt ?? "").localeCompare(b.lastAt ?? ""));
  const scores = taken.map((q) => Math.round(q.lastScore ?? q.best ?? 0));
  const avg = taken.length ? Math.round(taken.reduce((a, q) => a + (q.best ?? q.lastScore ?? 0), 0) / taken.length) : null;

  // ---- today: live classes today, open quizzes not done yet, the next lecture ----
  const endOfDay = new Date(now);
  endOfDay.setHours(23, 59, 59, 999);
  const today: TodayItem[] = [
    ...classes
      .filter((c): c is MeetItem & { startsAt: string } => !!c.startsAt && c.state !== "ended" && c.state !== "cancelled" && c.state !== "closed" && new Date(c.startsAt).getTime() <= endOfDay.getTime())
      .sort((a, b) => a.startsAt.localeCompare(b.startsAt))
      .map((c) => ({
        kind: "class" as const,
        title: c.topic || "Live class",
        sub: `${c.other?.name ?? "Teacher"} · ${new Date(c.startsAt).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`,
        href: classPath(c.code),
        at: c.startsAt,
      })),
    ...quizzes
      .filter((q) => q.state === "open" && q.attemptsUsed === 0)
      .map((q) => ({
        kind: "quiz" as const,
        title: q.lectureTitle || `Lecture ${q.lecture} quiz`,
        sub: `${q.courseTitle} · ${q.questions} questions`,
        href: ROUTES.student.assessments,
        at: q.dueAt ?? undefined,
      })),
    ...(inProgress ? [{ kind: "lecture" as const, title: inProgress.next, sub: inProgress.title, href: inProgress.href }] : []),
  ];

  return (
    <DashboardV3
      name={session?.name || state.profile.name}
      userId={userId}
      inProgress={inProgress}
      courses={currentCourses}
      goalPct={goalPct}
      avg={avg}
      scores={scores}
      certificates={state.certificates.length}
      streak={studyStreak(state)}
      today={today}
    />
  );
}
