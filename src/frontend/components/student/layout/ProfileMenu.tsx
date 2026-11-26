"use client";

/** Top-bar profile chip: hover (or focus) opens a card with the student ID, the account details and quick links. */
import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, ChevronDown, Copy, LifeBuoy, LogOut, Mail, Settings, ShieldCheck } from "lucide-react";
import PersonPhoto from "@/components/shared/PersonPhoto";
import { useStudentPublicId } from "@/components/student/shared/MyStudentId";
import { logOut } from "@/lib/auth/local-auth";
import { ROUTES } from "@/lib/routes";

type Props = { name: string; email?: string; userId?: string; picture?: string };

export default function ProfileMenu({ name, email, userId, picture }: Props) {
  const router = useRouter();
  const publicId = useStudentPublicId();
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const show = () => {
    window.clearTimeout(timer.current);
    setOpen(true);
  };
  const hide = () => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(false), 150);
  };
  const copy = async () => {
    if (!publicId) return;
    try {
      await navigator.clipboard.writeText(publicId);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* the id is on screen anyway */
    }
  };

  const item = "flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm text-[#1E2A38] transition hover:bg-[#FBF3EA]";

  return (
    <div
      className="relative"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) hide();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") setOpen(false);
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label="Your account"
        data-testid="profile-chip"
        className="flex items-center gap-3 rounded-2xl border border-[#E8D5C2] bg-white py-[5px] pl-3.5 pr-1.5 transition hover:bg-[#FBF3EA]"
      >
        <span className="hidden max-w-[180px] truncate text-sm font-semibold text-[#1E2A38] lg:block">{name}</span>
        <PersonPhoto kind="student" id={userId} name={name} src={picture} className="h-[38px] w-[38px] rounded-xl bg-[linear-gradient(150deg,#B06D45,#8E5233)] text-sm font-semibold text-white" />
        <ChevronDown className={`hidden h-3.5 w-3.5 text-[#A8653F] transition sm:block ${open ? "rotate-180" : ""}`} />
      </button>

      {open ? (
        <div className="absolute right-0 top-full z-50 pt-2" data-testid="profile-card">
          <div className="nh-menu-pop w-[300px] overflow-hidden rounded-[20px] border border-[#EFE6DA] bg-white shadow-[0_24px_50px_-20px_rgba(60,40,20,.45)]">
            {/* student ID on top */}
            <div className="relative overflow-hidden bg-[linear-gradient(135deg,#B06D45,#8E5233)] px-4 pb-4 pt-3.5 text-white">
              <svg viewBox="0 0 200 120" className="pointer-events-none absolute -right-8 -top-10 h-32 w-48" aria-hidden>
                <g fill="none" stroke="#fff" strokeOpacity=".14"><circle cx="150" cy="40" r="34" /><circle cx="150" cy="40" r="58" /></g>
              </svg>
              <p className="relative text-[10.5px] font-bold tracking-[.14em] text-[#FBE3CF]">STUDENT ID</p>
              <div className="relative mt-1 flex items-center gap-2">
                <span className="font-mono text-[19px] font-bold tracking-wide" data-testid="profile-card-id">{publicId || "…"}</span>
                <button
                  type="button"
                  onClick={copy}
                  disabled={!publicId}
                  className="ml-auto inline-flex h-8 items-center gap-1 rounded-lg bg-white/20 px-2.5 text-xs font-semibold text-white ring-1 ring-white/30 transition hover:bg-white/30 disabled:opacity-60"
                >
                  {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />} {copied ? "Copied" : "Copy"}
                </button>
              </div>
              <p className="relative mt-1 text-[11.5px] text-[#FBE3CF]">Tutors and support find you with this ID.</p>
            </div>

            {/* who */}
            <div className="flex items-center gap-3 border-b border-[#F1E7DB] px-4 py-3.5">
              <PersonPhoto kind="student" id={userId} name={name} src={picture} className="h-11 w-11 rounded-full bg-[#F6EAE2] text-sm font-bold text-[#7A4527]" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[15px] font-semibold text-[#1E2A38]">{name}</p>
                {email ? (
                  <p className="flex items-center gap-1 truncate text-xs text-[#6B7280]"><Mail className="h-3 w-3 shrink-0" /> {email}</p>
                ) : null}
              </div>
              <span className="shrink-0 rounded-full bg-[#FBF3EA] px-2 py-0.5 text-[10.5px] font-bold text-[#7A4527]">Student</span>
            </div>

            <nav className="p-2">
              <Link href={ROUTES.student.settings} className={item}><Settings className="h-4 w-4 text-[#A8653F]" /> Profile &amp; settings</Link>
              <Link href={`${ROUTES.student.settings}?tab=security`} className={item}><ShieldCheck className="h-4 w-4 text-[#A8653F]" /> Sign-in &amp; security</Link>
              <Link href={ROUTES.student.support} className={item}><LifeBuoy className="h-4 w-4 text-[#A8653F]" /> Help &amp; Support</Link>
              <div className="my-1 border-t border-[#F1E7DB]" />
              <button
                type="button"
                onClick={() => {
                  logOut();
                  router.replace(ROUTES.login());
                }}
                className={`${item} w-full text-left`}
              >
                <LogOut className="h-4 w-4 text-[#8F8984]" /> Sign out
              </button>
            </nav>
          </div>
        </div>
      ) : null}
    </div>
  );
}
