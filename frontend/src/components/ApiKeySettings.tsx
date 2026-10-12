import { CheckCircle2, ChevronDown, Eye, EyeOff, ExternalLink, Info, LoaderCircle, Lock, XCircle } from 'lucide-react'
import { useId, useState } from 'react'

import { cn } from '../lib/format'
import { ApiError, validateApiKey } from '../services/api'

type Validation =
  | { state: 'idle' }
  | { state: 'checking' }
  | { state: 'valid' }
  | { state: 'invalid'; message: string }

interface ApiKeySettingsProps {
  apiKey: string
  onApiKeyChange: (value: string) => void
  remember: boolean
  onRememberChange: (value: boolean) => void
  onClear: () => void
  open: boolean
  onOpenChange: (open: boolean) => void
  /** false si el backend no tiene clave propia: entonces BYOK es obligatorio. */
  serverKeyAvailable: boolean | null
  disabled?: boolean
}

export function ApiKeySettings({
  apiKey,
  onApiKeyChange,
  remember,
  onRememberChange,
  onClear,
  open,
  onOpenChange,
  serverKeyAvailable,
  disabled,
}: ApiKeySettingsProps) {
  const [visible, setVisible] = useState(false)
  const [validation, setValidation] = useState<Validation>({ state: 'idle' })
  const panelId = useId()
  const inputId = useId()
  const hasKey = apiKey.trim().length > 0

  const handleChange = (value: string) => {
    onApiKeyChange(value)
    setValidation({ state: 'idle' })
  }

  const handleValidate = async () => {
    setValidation({ state: 'checking' })
    try {
      const { valid } = await validateApiKey(apiKey.trim())
      setValidation(valid ? { state: 'valid' } : { state: 'invalid', message: 'Groq ha rechazado esta clave.' })
    } catch (err) {
      setValidation({
        state: 'invalid',
        message: err instanceof ApiError ? err.message : 'No se pudo validar la clave.',
      })
    }
  }

  return (
    <section className="card overflow-hidden">
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        aria-expanded={open}
        aria-controls={panelId}
        className="focus-ring flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-slate-50/80 sm:px-6 dark:hover:bg-slate-800/40"
      >
        <span className="flex items-start gap-3 sm:items-center">
          <span
            className={cn(
              'flex size-9 shrink-0 items-center justify-center rounded-lg ring-1 transition',
              hasKey
                ? 'bg-emerald-50 text-emerald-600 ring-emerald-100 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20'
                : 'bg-slate-100 text-slate-600 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700',
            )}
          >
            <Lock className="size-4.5" aria-hidden />
          </span>
          <span>
            <span className="flex flex-wrap items-center gap-2 text-sm font-semibold">
              Usa tu propia API Key de Groq
              {hasKey ? (
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
                  Clave activa
                </span>
              ) : (
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                  {serverKeyAvailable === false ? 'Necesaria' : 'Opcional'}
                </span>
              )}
            </span>
            <span className="mt-0.5 block text-sm text-slate-500 dark:text-slate-400">
              Sin límites del modo gratuito. Tu clave nunca se guarda en el servidor.
            </span>
          </span>
        </span>
        <ChevronDown
          className={cn('size-5 shrink-0 text-slate-400 transition-transform duration-200', open && 'rotate-180')}
          aria-hidden
        />
      </button>

      <div
        id={panelId}
        className={cn(
          'grid transition-[grid-template-rows] duration-300 ease-out',
          open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
        )}
      >
        <div className="overflow-hidden" inert={!open}>
          <div className="border-t border-slate-100 px-5 pb-5 pt-4 sm:px-6 dark:border-slate-800">
            {serverKeyAvailable === false && (
              <p className="mb-4 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2.5 text-sm text-amber-800 ring-1 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20">
                <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
                El modo gratuito no está disponible ahora mismo. Introduce tu clave de Groq para continuar.
              </p>
            )}

            <label htmlFor={inputId} className="text-sm font-medium">
              API Key de Groq
            </label>
            <div className="mt-1.5 flex flex-col gap-2 sm:flex-row">
              <div className="relative flex-1">
                <Lock
                  className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400"
                  aria-hidden
                />
                <input
                  id={inputId}
                  type={visible ? 'text' : 'password'}
                  value={apiKey}
                  onChange={(e) => handleChange(e.target.value)}
                  placeholder="gsk_…"
                  autoComplete="off"
                  spellCheck={false}
                  disabled={disabled}
                  className="focus-ring h-11 w-full rounded-lg border border-slate-300 bg-white pl-9 pr-11 font-mono text-sm shadow-sm transition placeholder:text-slate-400 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950"
                />
                <button
                  type="button"
                  onClick={() => setVisible((v) => !v)}
                  className="focus-ring absolute right-1.5 top-1/2 flex size-8 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                  aria-label={visible ? 'Ocultar clave' : 'Mostrar clave'}
                >
                  {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
              <button
                type="button"
                onClick={handleValidate}
                disabled={!hasKey || validation.state === 'checking' || disabled}
                className="focus-ring inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
              >
                {validation.state === 'checking' && <LoaderCircle className="size-4 animate-spin" aria-hidden />}
                Validar clave
              </button>
            </div>

            <div aria-live="polite" className="min-h-6 pt-2 text-sm">
              {validation.state === 'valid' && (
                <p className="flex items-center gap-1.5 text-emerald-700 dark:text-emerald-400">
                  <CheckCircle2 className="size-4" aria-hidden /> Clave válida. Se usará en tus optimizaciones.
                </p>
              )}
              {validation.state === 'invalid' && (
                <p className="flex items-center gap-1.5 text-rose-700 dark:text-rose-400">
                  <XCircle className="size-4" aria-hidden /> {validation.message}
                </p>
              )}
            </div>

            <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
              <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => onRememberChange(e.target.checked)}
                  className="size-4 rounded border-slate-300 accent-indigo-600"
                />
                Recordar durante esta sesión
              </label>
              <div className="flex items-center gap-4 text-sm">
                {hasKey && (
                  <button
                    type="button"
                    onClick={() => {
                      onClear()
                      setValidation({ state: 'idle' })
                    }}
                    className="focus-ring rounded font-medium text-slate-600 underline-offset-4 hover:text-rose-600 hover:underline dark:text-slate-400"
                  >
                    Olvidar clave
                  </button>
                )}
                <a
                  href="https://console.groq.com/keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="focus-ring inline-flex items-center gap-1 rounded font-medium text-indigo-600 underline-offset-4 hover:underline dark:text-indigo-400"
                >
                  Conseguir una clave <ExternalLink className="size-3.5" aria-hidden />
                </a>
              </div>
            </div>

            <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2.5 text-xs leading-relaxed text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
              Tu clave viaja cifrada (HTTPS) en una cabecera y solo se usa para procesar tu petición: no se guarda
              ni se registra en el servidor. En el navegador se guarda solo en memoria, o en esta pestaña si marcas
              "Recordar durante esta sesión".
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
