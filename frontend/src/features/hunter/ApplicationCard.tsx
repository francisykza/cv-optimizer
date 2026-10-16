import { ExternalLink, LoaderCircle, Pencil, Trash2 } from 'lucide-react'
import { useId, useState } from 'react'

import { MarkdownPreview } from '../../components/result/MarkdownPreview'
import { cn } from '../../lib/format'
import { STATUS_LABEL } from './applications'
import type { ApplicationDetail, ApplicationItem, ApplicationStatus, ApplicationUpdate } from './types'

const DAY = new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'short' })

export function shortDate(iso: string): string {
  return DAY.format(new Date(iso)).replace('.', '')
}

export function daysAgo(iso: string, now: number = Date.now()): string {
  const days = Math.floor((now - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return 'hoy'
  if (days === 1) return 'ayer'
  return `hace ${days} días`
}

/** La compatibilidad del CV enviado, marcada con rotulador: verde si es alta, ámbar si es baja. */
function Compat({ after, before }: { after: number | null; before: number | null }) {
  if (after === null) {
    return (
      <div className="flex h-[4.5rem] w-24 shrink-0 items-center justify-center text-center text-xs leading-tight text-slate-500">
        Sin pasar por el Optimizador
      </div>
    )
  }
  const tone = after >= 80 ? 'marker-green' : after < 60 ? 'marker-amber' : null
  return (
    <div className="flex w-24 shrink-0 flex-col items-center pt-1 text-center">
      <span
        className={cn('font-serif text-[1.7rem] leading-none font-semibold tabular-nums', tone && `marker ${tone}`)}
      >
        {after}&nbsp;%
      </span>
      <span className="mt-1.5 text-[11px] font-medium text-slate-600">CV enviado</span>
      {before !== null && before !== after && (
        <span className="text-[11px] text-slate-500 tabular-nums">antes {before}&nbsp;%</span>
      )}
      <span className="sr-only">Compatibilidad del CV enviado: {after} por ciento</span>
    </div>
  )
}

interface ApplicationCardProps {
  app: ApplicationItem
  busy: boolean
  onChange: (changes: ApplicationUpdate) => void
  onDelete: () => void
  loadDetail: () => Promise<ApplicationDetail>
}

/** Una candidatura: ficha con su compatibilidad, su estado, notas y la copia de la oferta y del CV. */
export function ApplicationCard({ app, busy, onChange, onDelete, loadDetail }: ApplicationCardProps) {
  const id = useId()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(app.notes)
  const [detail, setDetail] = useState<ApplicationDetail | null>(null)
  const [open, setOpen] = useState<'offer' | 'cv' | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const where = [app.company, app.location].filter(Boolean).join(' · ')
  const history = app.events.length > 1 ? app.events : []

  const show = async (what: 'offer' | 'cv') => {
    if (open === what) return setOpen(null)
    setError(null)
    if (!detail) {
      setLoading(true)
      try {
        setDetail(await loadDetail())
      } catch {
        setError('No se ha podido cargar. Inténtalo de nuevo.')
        return
      } finally {
        setLoading(false)
      }
    }
    setOpen(what)
  }

  return (
    <article className="ficha p-4 sm:p-5" aria-labelledby={`${id}-title`}>
      <div className="flex flex-col gap-2 sm:flex-row sm:gap-5">
        <Compat after={app.ats_score_after} before={app.ats_score_before} />

        <div className="min-w-0 flex-1">
          <header className="ficha-head flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
            <div className="min-w-0 sm:flex-1">
              <h3 id={`${id}-title`} className="font-serif text-lg leading-snug font-semibold text-pretty">
                {app.title}
              </h3>
              <p className="mt-0.5 text-sm text-slate-600">
                {where}. <span className="text-slate-500">Enviada el {shortDate(app.applied_at)}</span>
                {app.judge_score !== null && (
                  <span className="text-slate-500">, nota del Buscador {app.judge_score}</span>
                )}
              </p>
            </div>
            <div className="shrink-0">
              <label htmlFor={`${id}-status`} className="sr-only">
                Estado de la candidatura
              </label>
              <select
                id={`${id}-status`}
                value={app.status}
                disabled={busy}
                onChange={(e) => onChange({ status: e.target.value as ApplicationStatus })}
                className="focus-ring h-9 rounded-md border border-slate-300 bg-white px-2.5 text-sm font-medium text-ink disabled:opacity-60"
              >
                {Object.entries(STATUS_LABEL).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </header>

          {history.length > 0 && (
            <p className="mt-2 text-[13px] text-slate-600">
              {history.map((e, i) => (
                <span key={`${e.status}-${e.at}`}>
                  {i > 0 && <span aria-hidden> → </span>}
                  {STATUS_LABEL[e.status]} {shortDate(e.at)}
                </span>
              ))}
            </p>
          )}

          {app.stale && (
            <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <span className="marker marker-amber">Lleva más de 3 semanas sin noticias</span>
              <button
                type="button"
                onClick={() => onChange({ status: 'no_response' })}
                disabled={busy}
                className="focus-ring rounded font-medium text-cobalt-700 underline-offset-2 hover:underline disabled:opacity-60"
              >
                Marcar «Sin respuesta»
              </button>
            </p>
          )}

          {editing ? (
            <form
              className="mt-3 space-y-2"
              onSubmit={(e) => {
                e.preventDefault()
                onChange({ notes: draft.trim() })
                setEditing(false)
              }}
            >
              <label htmlFor={`${id}-notes`} className="text-sm font-medium">
                Notas
              </label>
              <textarea
                id={`${id}-notes`}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                maxLength={4000}
                rows={3}
                autoFocus
                placeholder="Con quién hablaste, fechas de entrevista, qué te preguntaron…"
                className="focus-ring block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-ink"
              />
              <div className="flex gap-2">
                <button
                  type="submit"
                  className="focus-ring h-8 rounded-md bg-ink px-3 text-sm font-semibold text-white transition hover:bg-ink/90"
                >
                  Guardar nota
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDraft(app.notes)
                    setEditing(false)
                  }}
                  className="focus-ring h-8 rounded-md px-3 text-sm font-medium text-slate-600 transition hover:bg-slate-100"
                >
                  Cancelar
                </button>
              </div>
            </form>
          ) : (
            app.notes && <p className="mt-3 text-[15px] leading-7 whitespace-pre-line">{app.notes}</p>
          )}

          <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm">
            {app.url && (
              <a
                href={app.url}
                target="_blank"
                rel="noopener noreferrer"
                className="focus-ring inline-flex items-center gap-1 rounded font-medium text-cobalt-700 underline-offset-2 hover:underline"
              >
                Abrir la oferta
                <ExternalLink className="size-3.5" aria-hidden />
              </a>
            )}
            {app.has_offer_text && (
              <button
                type="button"
                onClick={() => void show('offer')}
                aria-expanded={open === 'offer'}
                className="focus-ring rounded font-medium text-cobalt-700 underline-offset-2 hover:underline"
              >
                {open === 'offer' ? 'Ocultar la oferta guardada' : 'Ver la oferta guardada'}
              </button>
            )}
            {app.has_cv && (
              <button
                type="button"
                onClick={() => void show('cv')}
                aria-expanded={open === 'cv'}
                className="focus-ring rounded font-medium text-cobalt-700 underline-offset-2 hover:underline"
              >
                {open === 'cv' ? 'Ocultar el CV enviado' : 'Ver el CV enviado'}
              </button>
            )}
            {!editing && (
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="focus-ring inline-flex items-center gap-1 rounded font-medium text-slate-600 underline-offset-2 hover:underline"
              >
                <Pencil className="size-3.5" aria-hidden />
                {app.notes ? 'Editar nota' : 'Añadir nota'}
              </button>
            )}
            <button
              type="button"
              onClick={onDelete}
              disabled={busy}
              className="focus-ring ml-auto inline-flex items-center gap-1 rounded font-medium text-slate-500 underline-offset-2 hover:text-rose-700 hover:underline disabled:opacity-60"
            >
              <Trash2 className="size-3.5" aria-hidden />
              Borrar
            </button>
          </p>

          {loading && (
            <p className="mt-2 flex items-center gap-2 text-sm text-slate-500" role="status">
              <LoaderCircle className="size-4 animate-spin" aria-hidden /> Cargando…
            </p>
          )}
          {error && (
            <p className="mt-2 text-sm text-rose-700" role="alert">
              {error}
            </p>
          )}
          {open === 'offer' && detail?.offer_text && (
            <div className="mt-3 max-h-80 overflow-auto rounded-md bg-white px-4 py-3 text-[13px] leading-6 whitespace-pre-wrap ring-1 ring-slate-200">
              {detail.offer_text}
            </div>
          )}
          {open === 'cv' && detail?.cv_markdown && (
            <div className="sheet mt-3 max-h-[28rem] overflow-auto px-5 py-4 sm:px-8 sm:py-6">
              <MarkdownPreview markdown={detail.cv_markdown} />
            </div>
          )}
        </div>
      </div>
    </article>
  )
}
