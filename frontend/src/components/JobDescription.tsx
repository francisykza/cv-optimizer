import { useId } from 'react'

import { JOB_OFFER_MAX_CHARS, JOB_OFFER_MIN_CHARS } from '../lib/constants'
import { cn, formatNumber } from '../lib/format'
import type { OutputLanguage } from '../types/api'
import { SectionCard } from './ui/SectionCard'

interface JobDescriptionProps {
  value: string
  onChange: (value: string) => void
  language: OutputLanguage
  onLanguageChange: (value: OutputLanguage) => void
  disabled?: boolean
}

const LANGUAGES: { value: OutputLanguage; label: string }[] = [
  { value: 'auto', label: 'Igual que la oferta' },
  { value: 'es', label: 'Español' },
  { value: 'en', label: 'Inglés' },
]

export function JobDescription({ value, onChange, language, onLanguageChange, disabled }: JobDescriptionProps) {
  const textareaId = useId()
  const counterId = useId()
  const languageId = useId()
  const length = value.trim().length
  const tooShort = length > 0 && length < JOB_OFFER_MIN_CHARS
  const tooLong = length > JOB_OFFER_MAX_CHARS

  return (
    <SectionCard step={2} title="Pega la oferta de empleo" description="Cuanto más completa, mejor será el resultado.">
      <label htmlFor={textareaId} className="sr-only">
        Texto de la oferta de empleo
      </label>
      <textarea
        id={textareaId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        aria-describedby={counterId}
        aria-invalid={tooShort || tooLong}
        placeholder={'Ej.: Buscamos Backend Developer con experiencia en Python, FastAPI y PostgreSQL…\n\nIncluye responsabilidades, requisitos y tecnologías.'}
        className={cn(
          'focus-ring min-h-56 w-full flex-1 resize-y rounded-xl border bg-white px-4 py-3 text-sm leading-relaxed shadow-sm transition placeholder:text-slate-400 disabled:opacity-60 dark:bg-slate-950',
          tooLong
            ? 'border-rose-300 dark:border-rose-500/50'
            : 'border-slate-300 dark:border-slate-700',
        )}
      />

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
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
    </SectionCard>
  )
}
