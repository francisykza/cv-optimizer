import { Check, Minus } from 'lucide-react'

import type { MatchReport } from '../../types/api'

export function KeywordList({ match }: { match: MatchReport }) {
  if (match.matched_keywords.length + match.missing_keywords.length === 0) return null

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold">Palabras clave de la oferta</h3>
      <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Palabras clave">
        {match.matched_keywords.map((kw) => (
          <li
            key={kw}
            className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-800 ring-1 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/20"
          >
            <Check className="size-3" aria-label="Incluida:" />
            {kw}
          </li>
        ))}
        {match.missing_keywords.map((kw) => (
          <li
            key={kw}
            className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-500 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-700"
          >
            <Minus className="size-3" aria-label="No incluida:" />
            {kw}
          </li>
        ))}
      </ul>
    </div>
  )
}
