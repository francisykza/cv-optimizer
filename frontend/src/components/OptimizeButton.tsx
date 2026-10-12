import { ArrowRight, LoaderCircle, Sparkles } from 'lucide-react'

import { LOADING_STEPS } from '../hooks/useOptimize'
import { cn } from '../lib/format'

interface OptimizeButtonProps {
  loading: boolean
  step: number
  disabled: boolean
  disabledReason?: string
  onClick: () => void
  onCancel: () => void
}

export function OptimizeButton({ loading, step, disabled, disabledReason, onClick, onCancel }: OptimizeButtonProps) {
  return (
    <div className="flex flex-col items-center gap-3">
      <button
        type="button"
        onClick={onClick}
        disabled={disabled || loading}
        aria-busy={loading}
        className={cn(
          'focus-ring group relative inline-flex h-14 w-full max-w-md items-center justify-center gap-2.5 overflow-hidden rounded-xl px-8 text-base font-semibold text-white shadow-lg transition-all duration-200',
          'bg-gradient-to-r from-indigo-600 via-violet-600 to-indigo-600 bg-[length:200%_100%] shadow-indigo-600/25',
          !disabled && !loading && 'hover:-translate-y-0.5 hover:bg-right hover:shadow-xl hover:shadow-indigo-600/30 active:translate-y-0',
          loading && 'cursor-wait',
          disabled && !loading && 'cursor-not-allowed opacity-50 shadow-none',
        )}
      >
        {/* Brillo que recorre el botón mientras carga */}
        {loading && (
          <span
            aria-hidden
            className="absolute inset-0 animate-shimmer bg-[linear-gradient(90deg,transparent,rgb(255_255_255/0.18),transparent)] bg-[length:400px_100%] bg-no-repeat"
          />
        )}
        {loading ? (
          <>
            <LoaderCircle className="size-5 animate-spin" aria-hidden />
            <span aria-live="polite">{LOADING_STEPS[step]}</span>
          </>
        ) : (
          <>
            <Sparkles className="size-5" aria-hidden />
            Optimizar mi CV
            <ArrowRight className="size-5 transition-transform group-hover:translate-x-0.5" aria-hidden />
          </>
        )}
      </button>

      {loading ? (
        <div className="flex w-full max-w-md flex-col items-center gap-3">
          <ol className="flex w-full gap-1.5" aria-label="Progreso">
            {LOADING_STEPS.map((label, index) => (
              <li
                key={label}
                className={cn(
                  'h-1 flex-1 rounded-full transition-colors duration-500',
                  index < step
                    ? 'bg-indigo-500'
                    : index === step
                      ? 'animate-pulse bg-indigo-300 dark:bg-indigo-500/50'
                      : 'bg-slate-200 dark:bg-slate-800',
                )}
              >
                <span className="sr-only">{label}</span>
              </li>
            ))}
          </ol>
          <button
            type="button"
            onClick={onCancel}
            className="focus-ring rounded text-sm font-medium text-slate-500 underline-offset-4 hover:text-slate-800 hover:underline dark:hover:text-slate-200"
          >
            Cancelar
          </button>
        </div>
      ) : (
        disabled &&
        disabledReason && <p className="text-sm text-slate-500 dark:text-slate-400">{disabledReason}</p>
      )}
    </div>
  )
}
