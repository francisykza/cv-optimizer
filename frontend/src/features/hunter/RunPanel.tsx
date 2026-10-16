import { LoaderCircle, Search } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { cn } from '../../lib/format'
import { HunterError, hunterApi } from './hunterClient'
import type { Run, SourceRun } from './types'

const SITE: Record<string, string> = {
  linkedin: 'LinkedIn',
  indeed: 'Indeed',
  google: 'Google Jobs',
  remotive: 'Remotive',
  arbeitnow: 'Arbeitnow',
}

const SOURCE_STATE: Record<SourceRun['status'], { text: string; tone: string }> = {
  ok: { text: 'bien', tone: 'text-emerald-700 dark:text-emerald-400' },
  empty: { text: 'sin ofertas nuevas', tone: 'text-slate-500 dark:text-slate-400' },
  blocked: { text: 'nos ha bloqueado', tone: 'text-amber-700 dark:text-amber-400' },
  timeout: { text: 'no respondió', tone: 'text-amber-700 dark:text-amber-400' },
  error: { text: 'falló', tone: 'text-rose-700 dark:text-rose-400' },
  skipped_breaker_open: { text: 'en pausa', tone: 'text-slate-500 dark:text-slate-400' },
}

const POLL_MS = 2000

function when(iso: string | null): string {
  if (!iso) return ''
  return new Intl.DateTimeFormat('es-ES', { weekday: 'long', hour: '2-digit', minute: '2-digit' }).format(new Date(iso))
}

function summary(run: Run): string {
  const c = run.counts
  const parts: string[] = []
  if (run.mode !== 'judge_only') parts.push(`${c.new} ofertas nuevas de ${c.fetched} leídas`)
  if (run.mode !== 'ingest_only') parts.push(`${c.judged} juzgadas por la IA`)
  parts.push(c.pending_judge ? `${c.pending_judge} esperan al juez` : 'ninguna pendiente')
  return parts.join(', ')
}

interface RunPanelProps {
  token: string
  onFinished: () => void
  onAuthError: (error: HunterError) => void
}

/** "Buscar ofertas ahora" y el resultado de la última búsqueda, fuente a fuente. */
export function RunPanel({ token, onFinished, onAuthError }: RunPanelProps) {
  const [run, setRun] = useState<Run | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const poll = useRef<number | null>(null)

  const stopPolling = () => {
    if (poll.current !== null) window.clearTimeout(poll.current)
    poll.current = null
  }

  const follow = useCallback(
    (id: string) => {
      setActiveId(id)
      const tick = async () => {
        try {
          const current = await hunterApi.run(token, id)
          setRun(current)
          if (current.status === 'running') {
            poll.current = window.setTimeout(tick, POLL_MS)
          } else {
            setActiveId(null)
            onFinished()
          }
        } catch (err) {
          if (err instanceof HunterError && err.status === 401) onAuthError(err)
          else poll.current = window.setTimeout(tick, POLL_MS * 2)
        }
      }
      void tick()
    },
    [token, onFinished, onAuthError],
  )

  useEffect(() => {
    let cancelled = false
    hunterApi
      .runs(token)
      .then(([last]) => {
        if (cancelled || !last) return
        setRun(last)
        if (last.status === 'running') follow(last.id)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
      stopPolling()
    }
  }, [token, follow])

  const start = async () => {
    setStarting(true)
    setError(null)
    try {
      const { run_id } = await hunterApi.startRun(token)
      follow(run_id)
    } catch (err) {
      if (err instanceof HunterError && err.status === 401) onAuthError(err)
      setError(err instanceof Error ? err.message : 'No se pudo empezar la búsqueda.')
    } finally {
      setStarting(false)
    }
  }

  const running = activeId !== null || run?.status === 'running'

  return (
    <section
      className="card flex flex-col gap-4 p-5 sm:flex-row sm:items-start sm:justify-between sm:p-6"
      aria-live="polite"
    >
      <div className="min-w-0 space-y-2 text-sm">
        {running ? (
          <p className="flex items-center gap-2 font-medium">
            <LoaderCircle className="size-4 animate-spin text-cobalt-600" aria-hidden />
            Buscando en los portales y pasando las ofertas por tus reglas. Tarda unos minutos.
          </p>
        ) : run ? (
          <p>
            <span className="font-medium">Última búsqueda, {when(run.finished_at ?? run.started_at)}:</span>{' '}
            {summary(run)}.
          </p>
        ) : (
          <p className="text-slate-600 dark:text-slate-300">Todavía no has buscado ofertas desde aquí.</p>
        )}
        {run && run.sources.length > 0 && (
          <ul className="flex flex-wrap gap-x-4 gap-y-1">
            {run.sources.map((s) => (
              <li key={s.source}>
                {SITE[s.source] ?? s.source}{' '}
                <span className={cn('font-medium', SOURCE_STATE[s.status].tone)} title={s.error_message ?? undefined}>
                  {SOURCE_STATE[s.status].text}
                </span>
              </li>
            ))}
          </ul>
        )}
        {run?.error && !running && <p className="text-amber-800 dark:text-amber-300">{run.error}</p>}
        {error && (
          <p className="text-rose-700 dark:text-rose-400" role="alert">
            {error}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={start}
        disabled={running || starting}
        className="focus-ring inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md bg-cobalt-600 px-4 text-sm font-semibold text-white transition hover:bg-cobalt-700 disabled:opacity-60"
      >
        {running || starting ? (
          <LoaderCircle className="size-4 animate-spin" aria-hidden />
        ) : (
          <Search className="size-4" aria-hidden />
        )}
        {running ? 'Buscando…' : 'Buscar ofertas ahora'}
      </button>
    </section>
  )
}
