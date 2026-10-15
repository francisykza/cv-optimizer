import { TrendingUp } from 'lucide-react'

import { useAnimatedNumber } from '../../hooks/useAnimatedNumber'
import type { MatchReport } from '../../types/api'

const RADIUS = 42
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

function scoreColor(score: number): string {
  if (score >= 70) return 'text-emerald-500'
  if (score >= 40) return 'text-amber-500'
  return 'text-rose-500'
}

export function MatchScoreCard({ match }: { match: MatchReport }) {
  const delta = match.score_after - match.score_before
  // Al llegar el resultado, el marcador cuenta desde la puntuación de antes hasta la de después.
  const shown = useAnimatedNumber(match.score_after, match.score_before)
  const total = match.matched_keywords.length + match.missing_keywords.length

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold">Compatibilidad con la oferta</h3>
      <div className="mt-4 flex items-center gap-5">
        <div className="relative size-28 shrink-0">
          <svg viewBox="0 0 100 100" className="size-full -rotate-90" aria-hidden>
            <circle
              cx="50"
              cy="50"
              r={RADIUS}
              fill="none"
              strokeWidth="9"
              className="stroke-slate-100 dark:stroke-slate-800"
            />
            <circle
              cx="50"
              cy="50"
              r={RADIUS}
              fill="none"
              strokeWidth="9"
              strokeLinecap="round"
              stroke="currentColor"
              strokeDasharray={CIRCUMFERENCE}
              strokeDashoffset={CIRCUMFERENCE * (1 - shown / 100)}
              className={scoreColor(shown)}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-bold tabular-nums">{Math.round(shown)}%</span>
            <span className="text-[11px] text-slate-500 dark:text-slate-400">después</span>
          </div>
        </div>

        <div className="space-y-2 text-sm">
          <p className="text-slate-600 dark:text-slate-400">
            Antes:{' '}
            <span className="font-semibold tabular-nums text-slate-900 dark:text-slate-100">{match.score_before}%</span>
          </p>
          {delta > 0 && (
            <p className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/20">
              <TrendingUp className="size-3.5" aria-hidden />+{delta} puntos
            </p>
          )}
          <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            {match.matched_keywords.length} de {total} palabras clave de la oferta aparecen en tu CV.
          </p>
        </div>
      </div>
    </div>
  )
}
