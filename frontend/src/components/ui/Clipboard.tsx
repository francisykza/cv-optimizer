import type { ReactNode } from 'react'

import { cn } from '../../lib/format'

/** Tablero de pinza: la hoja de papel (hijo) queda sujeta por una pinza metálica. Es el soporte de
 *  todo lo que es "documento": la demo de la portada, el CV optimizado y el pitch. */
export function Clipboard({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('board', className)}>
      <span className="board-clip" aria-hidden />
      {children}
    </div>
  )
}
