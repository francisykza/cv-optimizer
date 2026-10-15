import { forwardRef } from 'react'

/** Rotulador fluorescente visto en diagonal. La punta usa currentColor para cambiar de color en
 *  cada trazo. El punto (0, 0) del elemento es la punta: se posiciona con transform. */
export const MarkerPen = forwardRef<SVGSVGElement, { className?: string }>(function MarkerPen({ className }, ref) {
  return (
    <svg
      ref={ref}
      viewBox="0 0 120 40"
      width="96"
      height="32"
      aria-hidden
      className={className}
      style={{ position: 'absolute', left: 0, top: 0, transformOrigin: '0 100%', pointerEvents: 'none' }}
    >
      <g transform="rotate(-28 0 40)">
        {/* Punta biselada */}
        <path d="M0 40 L14 31 L18 39 Z" fill="currentColor" />
        <rect x="14" y="29" width="10" height="12" rx="1.5" fill="#d7dde8" />
        {/* Cuerpo */}
        <rect x="23" y="26" width="70" height="18" rx="4" fill="#1b2a4a" />
        <rect x="23" y="26" width="70" height="5" rx="2.5" fill="#ffffff" opacity="0.18" />
        {/* Capuchón trasero del color de la tinta */}
        <rect x="91" y="25" width="22" height="20" rx="5" fill="currentColor" />
        <rect x="93" y="27" width="6" height="16" rx="2" fill="#ffffff" opacity="0.35" />
      </g>
    </svg>
  )
})
