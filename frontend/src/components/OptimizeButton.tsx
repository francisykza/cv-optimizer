import { LoaderCircle } from 'lucide-react'

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
          'focus-ring relative inline-flex h-14 w-full max-w-md items-center justify-center gap-2.5 overflow-hidden rounded-md px-8 text-base font-semibold text-white transition-colors duration-150',
          'bg-cobalt-600 dark:bg-cobalt-500',
          !disabled && !loading && 'hover:bg-cobalt-700 active:bg-cobalt-800 dark:hover:bg-cobalt-400',
          loading && 'cursor-wait',
          disabled && !loading && 'cursor-not-allowed opacity-50',
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
          'Optimizar mi CV'
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
                    ? 'bg-cobalt-500'
                    : index === step
                      ? 'animate-pulse bg-cobalt-300 dark:bg-cobalt-500/50'
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
