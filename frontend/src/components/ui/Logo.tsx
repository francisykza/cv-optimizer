/** Una hoja con un trazo de rotulador verde: el gesto central de la app. */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="6" fill="#1b2a4a" />
      <path d="M9 6.5h10l4.5 4.5v13.5a1.5 1.5 0 0 1-1.5 1.5H9a1.5 1.5 0 0 1-1.5-1.5V8A1.5 1.5 0 0 1 9 6.5z" fill="#fff" />
      <rect x="10" y="14" width="10" height="3.6" rx="0.6" fill="#b9f2c8" />
      <path d="M10.5 15.8h9M10.5 20.8h6.5M10.5 11h5" stroke="#1b2a4a" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  )
}
