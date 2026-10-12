import { KeyRound, RotateCcw, TriangleAlert } from 'lucide-react'

import type { ApiError } from '../services/api'

const TITLES: Record<string, string> = {
  PDF_NO_TEXT: 'No hemos podido leer tu PDF',
  INVALID_PDF: 'El archivo no es válido',
  TOO_MANY_PAGES: 'El CV es demasiado largo',
  FILE_TOO_LARGE: 'El archivo es demasiado grande',
  INVALID_JOB_OFFER: 'Revisa la oferta de empleo',
  BYOK_KEY_INVALID: 'Tu API key no es válida',
  RATE_LIMITED: 'Has alcanzado el límite gratuito',
  SERVER_LLM_NOT_CONFIGURED: 'Modo gratuito no disponible',
  UPSTREAM_RATE_LIMITED: 'El servicio de IA está saturado',
  LLM_TIMEOUT: 'La IA ha tardado demasiado',
  NETWORK_ERROR: 'Sin conexión con el servidor',
}

// Errores en los que usar una clave propia (BYOK) es la solución.
const SUGGEST_BYOK = new Set(['RATE_LIMITED', 'SERVER_LLM_NOT_CONFIGURED', 'BYOK_KEY_INVALID', 'UPSTREAM_RATE_LIMITED'])
const RETRYABLE = new Set([
  'NETWORK_ERROR',
  'CLIENT_TIMEOUT',
  'LLM_TIMEOUT',
  'LLM_BAD_OUTPUT',
  'LLM_UPSTREAM_ERROR',
  'UPSTREAM_RATE_LIMITED',
  'INTERNAL_ERROR',
])

interface ErrorAlertProps {
  error: ApiError
  onRetry: () => void
  onUseOwnKey: () => void
}

export function ErrorAlert({ error, onRetry, onUseOwnKey }: ErrorAlertProps) {
  return (
    <div
      role="alert"
      className="animate-fade-in-up rounded-2xl border border-rose-200 bg-rose-50 p-5 dark:border-rose-500/30 dark:bg-rose-500/10"
    >
      <div className="flex gap-3">
        <TriangleAlert className="mt-0.5 size-5 shrink-0 text-rose-600 dark:text-rose-400" aria-hidden />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-rose-900 dark:text-rose-200">
            {TITLES[error.code] ?? 'Algo ha salido mal'}
          </h3>
          <p className="mt-1 text-sm text-rose-800 dark:text-rose-300">{error.message}</p>

          {(SUGGEST_BYOK.has(error.code) || RETRYABLE.has(error.code)) && (
            <div className="mt-3 flex flex-wrap gap-2">
              {RETRYABLE.has(error.code) && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="focus-ring inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-rose-700 shadow-sm ring-1 ring-rose-200 hover:bg-rose-100 dark:bg-rose-950 dark:text-rose-200 dark:ring-rose-500/30"
                >
                  <RotateCcw className="size-3.5" aria-hidden /> Reintentar
                </button>
              )}
              {SUGGEST_BYOK.has(error.code) && (
                <button
                  type="button"
                  onClick={onUseOwnKey}
                  className="focus-ring inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-rose-700 shadow-sm ring-1 ring-rose-200 hover:bg-rose-100 dark:bg-rose-950 dark:text-rose-200 dark:ring-rose-500/30"
                >
                  <KeyRound className="size-3.5" aria-hidden />
                  {error.code === 'BYOK_KEY_INVALID' ? 'Revisar mi API key' : 'Usar mi propia API key'}
                </button>
              )}
            </div>
          )}

          {error.requestId && (
            <p className="mt-3 font-mono text-[11px] text-rose-700/70 dark:text-rose-300/60">ID: {error.requestId}</p>
          )}
        </div>
      </div>
    </div>
  )
}
