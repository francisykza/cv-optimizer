import { ClipboardPaste, Info, LoaderCircle, TriangleAlert, X } from 'lucide-react'
import { useEffect, useId } from 'react'

import { type SmartPasteState, useSmartPaste } from '../hooks/useSmartPaste'
import { JOB_OFFER_MAX_CHARS, JOB_OFFER_MIN_CHARS } from '../lib/constants'
import { cn, formatNumber } from '../lib/format'
import type { AdjustmentLevel, OutputLanguage } from '../types/api'
import { SectionCard } from './ui/SectionCard'

interface JobDescriptionProps {
  value: string
  onChange: (value: string) => void
  language: OutputLanguage
  onLanguageChange: (value: OutputLanguage) => void
  adjustment?: AdjustmentLevel
  onAdjustmentChange?: (value: AdjustmentLevel) => void
  disabled?: boolean
  /** Avisa mientras se lee un enlace o una captura (para bloquear el botón de optimizar). */
  onBusyChange?: (busy: boolean) => void
}

const LANGUAGES: { value: OutputLanguage; label: string }[] = [
  { value: 'auto', label: 'Igual que la oferta' },
  { value: 'es', label: 'Español' },
  { value: 'en', label: 'Inglés' },
]

const ADJUSTMENTS: { value: AdjustmentLevel; label: string; hint: string }[] = [
  {
    value: 'deep',
    label: 'Profundo',
    hint: 'Reescribe el enfoque: verbos de acción y logros con lo que ya pone tu CV.',
  },
  { value: 'subtle', label: 'Sutil', hint: 'Mantiene tus frases y solo incorpora las palabras clave de la oferta.' },
]

export function JobDescription({
  value,
  onChange,
  language,
  onLanguageChange,
  adjustment = 'deep',
  onAdjustmentChange,
  disabled,
  onBusyChange,
}: JobDescriptionProps) {
  const adjustmentId = useId()
  const adjustmentHintId = useId()
  const paste = useSmartPaste(value, onChange)
  const textareaId = useId()
  const counterId = useId()
  const languageId = useId()
  const length = value.trim().length
  const tooShort = length > 0 && length < JOB_OFFER_MIN_CHARS
  const tooLong = length > JOB_OFFER_MAX_CHARS

  useEffect(() => onBusyChange?.(paste.busy), [paste.busy, onBusyChange])

  return (
    <SectionCard
      step={2}
      title="Pega la oferta de empleo"
      description="El texto, el enlace o una captura de pantalla (Ctrl+V). Cuanto más completa, mejor."
    >
      <label htmlFor={textareaId} className="sr-only">
        Texto de la oferta de empleo
      </label>
      <textarea
        id={textareaId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onPaste={paste.onPaste}
        disabled={disabled}
        readOnly={paste.busy}
        aria-busy={paste.busy}
        aria-describedby={counterId}
        aria-invalid={tooShort || tooLong}
        placeholder={
          'Pega aquí la oferta:\n• El texto (Ctrl+A y Ctrl+C en la web de la oferta)\n• El enlace (https://…)\n• Una o varias capturas de pantalla'
        }
        className={cn(
          'focus-ring min-h-56 w-full flex-1 resize-y rounded-md border bg-paper px-4 py-3 text-sm leading-relaxed transition placeholder:text-slate-400 disabled:opacity-60 dark:bg-slate-950',
          tooLong
            ? 'border-rose-300 dark:border-rose-500/50'
            : 'border-slate-300 dark:border-slate-700',
          paste.busy && 'cursor-progress opacity-70',
        )}
      />

      <PasteStatus state={paste.state} />
      {paste.notice && (
        <div
          role={paste.notice.tone === 'warning' ? 'alert' : 'status'}
          className={cn(
            'mt-3 flex items-start gap-2.5 rounded-lg px-3 py-2.5 text-sm ring-1',
            paste.notice.tone === 'warning'
              ? 'bg-amber-50 text-amber-900 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-200 dark:ring-amber-500/25'
              : 'bg-sky-50 text-sky-900 ring-sky-200 dark:bg-sky-500/10 dark:text-sky-200 dark:ring-sky-500/25',
          )}
        >
          {paste.notice.tone === 'warning' ? (
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          ) : (
            <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
          )}
          <p className="flex-1">{paste.notice.text}</p>
          <button
            type="button"
            onClick={paste.dismissNotice}
            aria-label="Cerrar aviso"
            className="focus-ring -m-1 rounded p-1 opacity-70 transition hover:opacity-100"
          >
            <X className="size-3.5" aria-hidden />
          </button>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-5 gap-y-3">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
          <div className="flex items-center gap-2">
            <label htmlFor={languageId} className="text-sm text-slate-600 dark:text-slate-400">
              Idioma del CV
            </label>
            <select
              id={languageId}
              value={language}
              onChange={(e) => onLanguageChange(e.target.value as OutputLanguage)}
              disabled={disabled}
              className="focus-ring h-9 rounded-lg border border-slate-300 bg-white px-2.5 text-sm shadow-sm dark:border-slate-700 dark:bg-slate-900"
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
          {onAdjustmentChange && (
            <div className="flex items-center gap-2">
              <label htmlFor={adjustmentId} className="text-sm text-slate-600 dark:text-slate-400">
                Nivel de ajuste
              </label>
              <select
                id={adjustmentId}
                value={adjustment}
                onChange={(e) => onAdjustmentChange(e.target.value as AdjustmentLevel)}
                disabled={disabled}
                aria-describedby={adjustmentHintId}
                className="focus-ring h-9 rounded-lg border border-slate-300 bg-white px-2.5 text-sm shadow-sm dark:border-slate-700 dark:bg-slate-900"
              >
                {ADJUSTMENTS.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        <p
          id={counterId}
          aria-live="polite"
          className={cn(
            'text-xs tabular-nums',
            tooShort ? 'text-amber-600 dark:text-amber-400' : tooLong ? 'text-rose-600' : 'text-slate-500',
          )}
        >
          {tooShort
            ? `Faltan ${JOB_OFFER_MIN_CHARS - length} caracteres`
            : `${formatNumber(length)} / ${formatNumber(JOB_OFFER_MAX_CHARS)}`}
        </p>
      </div>
      {onAdjustmentChange && (
        <p id={adjustmentHintId} className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          {ADJUSTMENTS.find((a) => a.value === adjustment)?.hint}
        </p>
      )}
    </SectionCard>
  )
}

function PasteStatus({ state }: { state: SmartPasteState }) {
  if (state.kind === 'idle') {
    return (
      <p className="mt-2 flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
        <ClipboardPaste className="size-3.5" aria-hidden />
        Las capturas se leen en tu navegador: no se envían a ningún servidor.
      </p>
    )
  }
  const label =
    state.kind === 'url'
      ? 'Leyendo la oferta desde el enlace…'
      : state.phase === 'loading'
        ? 'Preparando el lector de capturas (solo la primera vez tarda unos segundos)…'
        : `Leyendo el texto de la captura… ${Math.round(state.progress * 100)} %`
  const percent = state.kind === 'ocr' && state.phase === 'recognizing' ? Math.round(state.progress * 100) : null

  return (
    <div role="status" aria-live="polite" className="mt-2 text-xs text-cobalt-700 dark:text-cobalt-300">
      <p className="flex items-center gap-1.5">
        <LoaderCircle className="size-3.5 animate-spin" aria-hidden />
        {label}
      </p>
      {percent !== null && (
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-cobalt-100 dark:bg-cobalt-500/20">
          <div className="h-full rounded-full bg-cobalt-500 transition-[width]" style={{ width: `${percent}%` }} />
        </div>
      )}
    </div>
  )
}
