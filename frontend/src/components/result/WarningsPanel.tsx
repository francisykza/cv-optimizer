import { FileWarning, Info, LocateFixed, SearchX, ShieldAlert, ShieldCheck } from 'lucide-react'

import { cn } from '../../lib/format'
import { UNGROUNDED_CODES, type ValidationWarning, type WarningCode } from '../../types/api'

const LABELS: Record<WarningCode, string> = {
  UNGROUNDED_DATE: 'Fecha',
  UNGROUNDED_METRIC: 'Cifra',
  UNGROUNDED_ENTITY: 'Dato',
  UNGROUNDED_SKILL: 'Habilidad',
  UNGROUNDED_CLAIM: 'Afirmación',
  GAP_LEAKED: 'Requisito de la oferta',
  FORMAT: 'Formato',
  LIMITED_CHECK: 'Aviso',
  KEYWORD_DROPPED: 'Palabra clave',
}

interface WarningsPanelProps {
  warnings: ValidationWarning[]
  onLocate: (term: string) => void
}

export function WarningsPanel({ warnings, onLocate }: WarningsPanelProps) {
  const ungrounded = warnings.filter((w) => UNGROUNDED_CODES.has(w.code))
  const others = warnings.filter((w) => !UNGROUNDED_CODES.has(w.code))

  if (ungrounded.length === 0) {
    // Si el CV se tradujo, solo se pudieron verificar los hechos que no dependen del idioma.
    const limited = others.some((w) => w.code === 'LIMITED_CHECK')
    return (
      <div className="card p-5">
        <div className="flex items-center gap-2.5">
          <span className="flex size-7 items-center justify-center rounded-md bg-emerald-50 text-emerald-600 ring-1 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20">
            <ShieldCheck className="size-4" aria-hidden />
          </span>
          <h3 className="text-sm font-semibold">Verificación anti-invención</h3>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
          {limited
            ? 'Fechas, cifras y datos de contacto coinciden con tu CV original.'
            : 'Fechas, cifras, empresas, títulos, habilidades y el resumen coinciden con tu CV original.'}
        </p>
        {others.length > 0 && <OtherWarnings warnings={others} />}
      </div>
    )
  }

  return (
    <div className="card border-amber-300 p-5 ring-1 ring-amber-200 dark:border-amber-500/40 dark:ring-amber-500/20">
      <div className="flex items-center gap-2.5">
        <span className="flex size-7 items-center justify-center rounded-md bg-amber-50 text-amber-600 ring-1 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20">
          <ShieldAlert className="size-4" aria-hidden />
        </span>
        <h3 className="text-sm font-semibold">
          {ungrounded.length === 1 ? 'Revisa 1 dato' : `Revisa ${ungrounded.length} datos`}
        </h3>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        No aparecen en tu CV original. Elimínalos o corrígelos antes de usar este CV.
      </p>
      <ul className="mt-3 space-y-2">
        {ungrounded.map((w) => (
          <li key={`${w.code}-${w.term}`}>
            <button
              type="button"
              onClick={() => w.term && onLocate(w.term)}
              className="focus-ring group w-full rounded-lg border border-slate-200 p-3 text-left transition hover:border-amber-300 hover:bg-amber-50/60 dark:border-slate-800 dark:hover:border-amber-500/40 dark:hover:bg-amber-500/5"
            >
              <span className="flex items-center justify-between gap-2">
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">
                  {LABELS[w.code]}
                </span>
                <LocateFixed
                  className="size-3.5 text-slate-400 opacity-0 transition group-hover:opacity-100"
                  aria-label="Ver en el CV"
                />
              </span>
              <span className="mt-1.5 block text-sm text-slate-700 dark:text-slate-300">{w.message}</span>
              {w.snippet && (
                <span className="mt-1 block truncate text-xs italic text-slate-500" title={w.snippet}>
                  "{w.snippet}"
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
      {others.length > 0 && <OtherWarnings warnings={others} />}
    </div>
  )
}

function OtherWarnings({ warnings }: { warnings: ValidationWarning[] }) {
  return (
    <ul className="mt-3 space-y-2 border-t border-slate-100 pt-3 dark:border-slate-800">
      {warnings.map((w) => {
        const Icon = w.code === 'FORMAT' ? FileWarning : w.code === 'KEYWORD_DROPPED' ? SearchX : Info
        return (
          <li key={`${w.code}-${w.term}`} className={cn('flex gap-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400')}>
            <Icon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            {w.message}
          </li>
        )
      })}
    </ul>
  )
}
