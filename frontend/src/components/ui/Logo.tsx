export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <defs>
        <linearGradient id="logo-gradient" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6366f1" />
          <stop offset="1" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#logo-gradient)" />
      <path d="M10 8h8l4 4v12a2 2 0 0 1-2 2h-10a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2z" fill="#fff" opacity=".95" />
      <path
        d="M12.5 18.5l2.5 2.5 5-5"
        fill="none"
        stroke="#6366f1"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
