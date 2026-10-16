import { useEffect, useRef } from 'react'

import { cn } from '../../lib/format'
import { canAnimate, EASE_HAND } from '../../lib/motion'
import type { Verdict } from './types'

const VERDICT: Record<Verdict, { label: string; stroke: string; text: string }> = {
  apply: { label: 'Aplicar', stroke: 'stroke-emerald-600', text: 'text-emerald-800' },
  maybe: { label: 'Quizá', stroke: 'stroke-cobalt-600', text: 'text-cobalt-800' },
  skip: { label: 'No', stroke: 'stroke-slate-400', text: 'text-slate-500' },
}

// Óvalo abierto, un poco torcido y con el final pasado del principio: como rodea la nota un corrector.
const RING =
  'M14 33 C 10 15, 34 5, 52 7 C 70 9, 79 22, 75 37 C 71 52, 51 60, 33 57 C 18 54, 8 44, 12 30 C 14 24, 20 18, 27 15'

/** La nota del corrector: la puntuación del juez rodeada a mano. Es lo único que llama la atención. */
export function ScoreMark({ score, verdict, className }: { score: number; verdict: Verdict; className?: string }) {
  const ring = useRef<SVGPathElement>(null)
  const style = VERDICT[verdict]

  useEffect(() => {
    const path = ring.current
    if (!path || !canAnimate(path as unknown as HTMLElement)) return
    const length = path.getTotalLength?.() ?? 220
    path.animate(
      [
        { strokeDasharray: `${length}`, strokeDashoffset: `${length}` },
        { strokeDasharray: `${length}`, strokeDashoffset: '0' },
      ],
      { duration: 650, delay: 120, easing: EASE_HAND, fill: 'backwards' },
    )
  }, [])

  return (
    <div className={cn('relative flex h-[4.5rem] w-24 shrink-0 flex-col items-center justify-center', className)}>
      <svg viewBox="0 0 86 64" className="absolute inset-0 size-full overflow-visible" aria-hidden>
        <path ref={ring} d={RING} fill="none" strokeWidth="3.4" strokeLinecap="round" className={style.stroke} />
      </svg>
      <span className={cn('relative font-serif text-[1.85rem] leading-none font-semibold tabular-nums', style.text)}>
        {score}
      </span>
      <span className={cn('relative mt-0.5 text-[11px] font-medium', style.text)}>{style.label}</span>
      <span className="sr-only">
        Encaje {score} sobre 100: {style.label.toLowerCase()}
      </span>
    </div>
  )
}
