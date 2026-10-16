import { Bookmark, ChevronDown, ExternalLink, LoaderCircle, RotateCcw, Send, X } from 'lucide-react'
import { forwardRef, useId, useState } from 'react'

import { cn } from '../../lib/format'
import { ScoreMark } from './ScoreMark'
import type { AppStatus, Flag, JobItem } from './types'

const MODALITY: Record<JobItem['modality'], string> = {
  remote: 'remoto',
  hybrid: 'híbrido',
  onsite: 'presencial',
  unknown: 'modalidad sin indicar',
}

const STATUS_NOTE: Partial<Record<AppStatus, string>> = {
  saved: 'Guardada',
  sent_to_optimizer: 'Enviada al Optimizador',
  applied: 'Inscrito',
  dismissed: 'Descartada por ti',
}

const SITE: Record<string, string> = {
  linkedin: 'LinkedIn',
  indeed: 'Indeed',
  google: 'Google Jobs',
  remotive: 'Remotive',
  arbeitnow: 'Arbeitnow',
}

function published(days: number): string {
  if (days <= 0) return 'publicada hoy'
  if (days === 1) return 'publicada ayer'
  return `publicada hace ${days} días`
}

export interface JobCardActions {
  onSend: (job: JobItem, card: HTMLElement | null) => void
  onStatus: (job: JobItem, status: AppStatus) => void
  onRejudge: (job: JobItem) => void
}

interface JobCardProps extends JobCardActions {
  job: JobItem
  busy?: 'send' | 'status' | 'rejudge' | null
}

function FlagLine({ flag, tone }: { flag: Flag; tone: 'green' | 'amber' }) {
  return (
    <li className="leading-relaxed">
      <span className={cn('marker', tone === 'green' ? 'marker-green' : 'marker-amber')}>{flag.text}</span>
    </li>
  )
}

function Quote({ flag }: { flag: Flag }) {
  if (!flag.evidence) return null
  return (
    <p className="mt-1 text-[13px] text-slate-600">
      <span className="font-serif italic">«{flag.evidence}»</span>
      {!flag.evidence_verified && <span className="ml-1.5 text-xs text-slate-400">(sin cita verificable)</span>}
    </p>
  )
}

const fold = (s: string) =>
  s
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()

/** La cita del descarte solo se muestra si añade algo al título y a la ubicación ("«berlin»" no). */
function informativeQuote(job: JobItem): string | null {
  const text = job.guillotine?.matched_text?.trim()
  if (!text || text.length < 16) return null
  const quote = fold(text)
  if (quote === fold(job.title) || fold(job.location).includes(quote)) return null
  return text
}

/** Descartadas: ficha compacta. Lo que importa es por qué, para detectar reglas demasiado duras. */
const DiscardedCard = forwardRef<HTMLElement, { job: JobItem; where: string }>(function DiscardedCard(
  { job, where },
  ref,
) {
  const titleId = useId()
  const quote = informativeQuote(job)
  return (
    <article ref={ref} className="ficha px-4 py-3 sm:px-5" aria-labelledby={titleId}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 id={titleId} className="font-serif text-base leading-snug font-semibold">
          {job.title}
        </h3>
        {job.sources[0] && (
          <a
            href={job.sources[0].url}
            target="_blank"
            rel="noopener noreferrer"
            className="focus-ring inline-flex items-center gap-1 rounded text-sm text-cobalt-700 underline-offset-2 hover:underline"
          >
            Ver oferta
            <ExternalLink className="size-3.5" aria-hidden />
          </a>
        )}
      </div>
      <p className="text-sm text-slate-600">{where}</p>
      {job.guillotine?.rule_label && (
        <p className="mt-1.5 text-sm leading-6">
          <span className="marker marker-amber">{job.guillotine.rule_label}</span>
          {quote && <span className="ml-2 font-serif text-[13px] italic text-slate-600">«{quote}»</span>}
        </p>
      )}
    </article>
  )
})

export const JobCard = forwardRef<HTMLElement, JobCardProps>(function JobCard(
  { job, busy, onSend, onStatus, onRejudge },
  ref,
) {
  const [open, setOpen] = useState(false)
  const detailId = useId()
  const v = job.verdict
  // "Remote, remoto": si la ubicación ya dice que es remoto, no se repite la modalidad.
  const saysRemote = job.modality === 'remote' && /remot/i.test(job.location)
  const where = [
    job.company,
    job.location || 'ubicación sin indicar',
    ...(saysRemote ? [] : [MODALITY[job.modality]]),
  ].join(', ')
  const note = STATUS_NOTE[job.app_status]
  const red = v ? v.red_flags.map((f) => ({ f, tone: 'amber' as const })) : []
  const green = v ? v.green_flags.map((f) => ({ f, tone: 'green' as const })) : []
  // Vista previa equilibrada: dos alertas y una a favor (si las hay). Al abrir, el detalle las muestra todas.
  const preview = [...red.slice(0, 2), ...green.slice(0, 1)]
  const flags = [...preview, ...[...red.slice(2), ...green.slice(1)].slice(0, 3 - preview.length)]

  if (job.stage === 'discarded') return <DiscardedCard ref={ref} job={job} where={where} />

  return (
    <article
      ref={ref}
      className={cn('ficha p-4 sm:p-5', job.app_status === 'dismissed' && 'ficha-dismissed')}
      aria-labelledby={`${detailId}-title`}
    >
      <div className="flex flex-col gap-1 sm:flex-row sm:gap-5">
        {v ? (
          <ScoreMark score={v.match_score} verdict={v.verdict} className="-ml-1 sm:ml-0" />
        ) : (
          <div className="flex h-[4.5rem] w-24 shrink-0 items-center justify-center text-center text-xs leading-tight text-slate-500">
            {job.judge_status === 'pending' && 'Pendiente del juez'}
            {job.judge_status === 'judge_failed' && 'El juez no pudo leerla'}
          </div>
        )}

        <div className="min-w-0 flex-1">
          <header className="ficha-head">
            <h3 id={`${detailId}-title`} className="font-serif text-lg leading-snug font-semibold text-pretty">
              {job.title}
            </h3>
            <p className="mt-0.5 text-sm text-slate-600">
              {where}. <span className="text-slate-500">{published(job.days_published)}</span>
              {job.times_seen > 2 && <span className="text-slate-500">, vista {job.times_seen} veces</span>}
            </p>
          </header>

          {v && <p className="mt-3 text-[15px] leading-7">{v.summary}</p>}

          {job.judge_status === 'judge_failed' && job.judge_error && (
            <p className="mt-3 text-sm text-slate-600">{job.judge_error}</p>
          )}

          {flags.length > 0 && !open && (
            <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
              {flags.map(({ f, tone }) => (
                <FlagLine key={`${tone}-${f.text}`} flag={f} tone={tone} />
              ))}
            </ul>
          )}

          {open && (
            <div id={detailId} className="mt-4 space-y-4 text-sm">
              {v && (v.red_flags.length > 0 || v.green_flags.length > 0) && (
                <div className="grid gap-4 sm:grid-cols-2">
                  {(
                    [
                      ['Alertas', v.red_flags],
                      ['A favor', v.green_flags],
                    ] as const
                  ).map(([title, list]) =>
                    list.length ? (
                      <div key={title}>
                        <h4 className="font-semibold">{title}</h4>
                        <ul className="mt-1 space-y-2">
                          {list.map((f) => (
                            <li key={f.text}>
                              {f.text}
                              <Quote flag={f} />
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null,
                  )}
                </div>
              )}
              {v && (
                <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-[auto_1fr]">
                  <dt className="font-semibold">Stack que usarías</dt>
                  <dd>{v.stack_core.join(', ') || 'No se distingue en la oferta'}</dd>
                  <dt className="font-semibold">Stack de relleno</dt>
                  <dd>{v.stack_inflated.join(', ') || 'Nada que parezca inflado'}</dd>
                  <dt className="font-semibold">Te falta</dt>
                  <dd>{v.missing_must_haves.join(', ') || 'Nada imprescindible'}</dd>
                </dl>
              )}
              <p className="flex flex-wrap gap-x-4 gap-y-1">
                {job.sources.map((s) => (
                  <a
                    key={s.url}
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="focus-ring inline-flex items-center gap-1 rounded text-cobalt-700 underline-offset-2 hover:underline"
                  >
                    Ver en {SITE[s.site] ?? s.site}
                    <ExternalLink className="size-3.5" aria-hidden />
                  </a>
                ))}
              </p>
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {
              <button
                type="button"
                onClick={(e) => onSend(job, e.currentTarget.closest('article'))}
                disabled={busy === 'send'}
                className="focus-ring inline-flex h-9 items-center gap-2 rounded-md bg-cobalt-600 px-3.5 text-sm font-semibold text-white transition hover:bg-cobalt-700 disabled:opacity-60"
              >
                {busy === 'send' ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden />
                ) : (
                  <Send className="size-4" aria-hidden />
                )}
                Enviar al Optimizador
              </button>
            }
            {job.app_status !== 'saved' && (
              <button
                type="button"
                onClick={() => onStatus(job, 'saved')}
                disabled={busy === 'status'}
                className="focus-ring inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-sm font-medium text-ink ring-1 ring-slate-300 transition hover:bg-slate-50 disabled:opacity-60"
              >
                <Bookmark className="size-4" aria-hidden />
                Guardar
              </button>
            )}
            {job.app_status !== 'applied' && (
              <button
                type="button"
                onClick={() => onStatus(job, 'applied')}
                disabled={busy === 'status'}
                className="focus-ring h-9 rounded-md px-3 text-sm font-medium text-ink ring-1 ring-slate-300 transition hover:bg-slate-50 disabled:opacity-60"
              >
                Ya me he inscrito
              </button>
            )}
            {job.stage === 'judge_failed' && (
              <button
                type="button"
                onClick={() => onRejudge(job)}
                disabled={busy === 'rejudge'}
                className="focus-ring inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-sm font-medium text-ink ring-1 ring-slate-300 transition hover:bg-slate-50 disabled:opacity-60"
              >
                {busy === 'rejudge' ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden />
                ) : (
                  <RotateCcw className="size-4" aria-hidden />
                )}
                Reintentar juicio
              </button>
            )}
            {job.app_status === 'dismissed' ? (
              <button
                type="button"
                onClick={() => onStatus(job, 'none')}
                className="focus-ring h-9 rounded-md px-3 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
              >
                Recuperar
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onStatus(job, 'dismissed')}
                disabled={busy === 'status'}
                className="focus-ring inline-flex h-9 items-center gap-1 rounded-md px-3 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-60"
              >
                <X className="size-4" aria-hidden />
                No me interesa
              </button>
            )}
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              aria-controls={detailId}
              className="focus-ring ml-auto inline-flex h-9 items-center gap-1 rounded-md px-2 text-sm font-medium text-cobalt-700 transition hover:bg-cobalt-50"
            >
              {open ? 'Menos detalle' : 'Más detalle'}
              <ChevronDown className={cn('size-4 transition-transform', open && 'rotate-180')} aria-hidden />
            </button>
          </div>
          {note && <p className="mt-2 text-xs font-medium text-slate-500">{note}</p>}
        </div>
      </div>
    </article>
  )
})
