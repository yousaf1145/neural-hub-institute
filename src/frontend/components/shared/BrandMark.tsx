/**
 * Neural Hub Institute logo: two green pillars with a glowing orange orb between them (the original mark).
 * `tile` (default) draws it on a soft cream tile; `bare` draws only the mark.
 */
export default function BrandMark({ size = 40, bare = false, className = "" }: { size?: number; bare?: boolean; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      aria-hidden="true"
      className={`shrink-0 ${className}`}
    >
      <defs>
        <linearGradient id="nhb-bar" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#2F5D3E" />
          <stop offset="1" stopColor="#1F4A2E" />
        </linearGradient>
        <radialGradient id="nhb-orb" cx=".35" cy=".3" r=".75">
          <stop offset="0" stopColor="#FFD2A0" />
          <stop offset=".55" stopColor="#F27A1A" />
          <stop offset="1" stopColor="#B9470A" />
        </radialGradient>
      </defs>
      {bare ? null : <rect x=".75" y=".75" width="38.5" height="38.5" rx="11" fill="#F4F1EC" stroke="#E6DED2" strokeWidth="1.5" />}
      <rect x="11" y="9" width="5" height="22" rx="2.5" fill="url(#nhb-bar)" />
      <rect x="24" y="9" width="5" height="22" rx="2.5" fill="url(#nhb-bar)" />
      <circle cx="20" cy="20" r="3.4" fill="url(#nhb-orb)" />
    </svg>
  );
}
