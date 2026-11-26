"use client";

/**
 * Counts real study time. Every minute the student spends on a learning page (a course, a lecture, a video,
 * the AI Teacher, a quiz) with the tab open and active (or a video / voice playing), one minute is added to
 * today's study log. The log is saved with the portal state, so Progress and the teacher see it.
 */
import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { usePortal } from "@/lib/store/portal-store";

const LEARNING = [/^\/student\/courses\/.+/, /^\/student\/lectures/, /^\/student\/ai-professor\//, /^\/student\/ai-teacher/, /^\/student\/assessments/, /^\/student\/materials/, /^\/student\/ask/];
const IDLE_MS = 3 * 60_000; // no mouse / keys / scroll for 3 minutes = not studying (unless media is playing)

export default function StudyTimer() {
  const pathname = usePathname();
  const { actions } = usePortal();
  const lastActive = useRef(Date.now());
  const learning = LEARNING.some((re) => re.test(pathname));

  useEffect(() => {
    const mark = () => { lastActive.current = Date.now(); };
    const evs = ["mousemove", "keydown", "scroll", "touchstart", "click"] as const;
    evs.forEach((e) => window.addEventListener(e, mark, { passive: true }));
    return () => evs.forEach((e) => window.removeEventListener(e, mark));
  }, []);

  useEffect(() => {
    if (!learning) return;
    lastActive.current = Date.now();
    const t = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      const playing = Array.from(document.querySelectorAll("video, audio")).some((m) => !(m as HTMLMediaElement).paused);
      if (playing || Date.now() - lastActive.current < IDLE_MS) actions.logStudyMinutes(1);
    }, 60_000);
    return () => window.clearInterval(t);
  }, [learning, actions]);

  return null;
}
