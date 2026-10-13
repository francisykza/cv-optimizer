import { Check, Minus, Plus, UserRound } from 'lucide-react'

import type { MatchReport } from '../../types/api'

export function KeywordList({ match, added = [] }: { match: MatchReport; added?: string[] }) {
  const softSkills = match.soft_skills ?? []
  const hasKeywords = match.matched_keywords.length + match.missing_keywords.length > 0
  if (!hasKeywords && softSkills.length === 0) return null

  return (
    <div className="card p-5">
      {hasKeywords && (
        <>
          <h3 className="text-sm font-semibold">Palabras clave de la oferta</h3>
          <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Palabras clave">
            {match.matched_keywords.map((kw) =>
              added.includes(kw) ? (
                <li
                  key={kw}
                  className="inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-1 text-xs font-medium text-sky-800 ring-1 ring-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:ring-sky-500/20"
                >
                  <Plus className="size-3" aria-label="Añadida por ti:" />
                  {kw}
                </li>
              ) : (
                <li
                  key={kw}
                  className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-800 ring-1 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/20"
                >
                  <Check className="size-3" aria-label="Incluida:" />
                  {kw}
                </li>
              ),
            )}
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
        </>
      )}

      {softSkills.length > 0 && (
        <div className={hasKeywords ? 'mt-5 border-t border-slate-100 pt-4 dark:border-slate-800' : ''}>
          <h3 className="flex items-center gap-1.5 text-sm font-semibold">
            <UserRound className="size-4 text-slate-400" aria-hidden />
            Competencias personales que pide la oferta
          </h3>
          <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            No las añadimos porque no se pueden verificar en tu CV y no cuentan en la puntuación. Si las tienes,
            demuéstralas con ejemplos en la entrevista o en la carta de presentación.
          </p>
          <ul className="mt-2.5 flex flex-wrap gap-1.5" aria-label="Competencias personales">
            {softSkills.map((skill) => (
              <li
                key={skill}
                className="rounded-md border border-dashed border-slate-300 px-2 py-1 text-xs text-slate-600 dark:border-slate-600 dark:text-slate-400"
              >
                {skill}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
