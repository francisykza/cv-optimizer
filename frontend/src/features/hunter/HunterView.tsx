import { LoaderCircle, Power, Search } from 'lucide-react'
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import toast from 'react-hot-toast'

import { cn } from '../../lib/format'
import { writeHandoff } from '../../lib/handoff'
import { animationsSupported, EASE_HAND, wait } from '../../lib/motion'
import { navigate, routeSection } from '../../lib/route'
import { ApplicationsPanel } from './ApplicationsPanel'
import { flushOutbox, newApplicationId, registerApplication } from './applications'
import { ConnectionGate, type GateState } from './ConnectionGate'
import { HunterError, hunterApi, tokenStore } from './hunterClient'
import { JobCard } from './JobCard'
import { takePairCode } from './pairing'
import { RulesEditor } from './RulesEditor'
import { RunPanel } from './RunPanel'
import type { AppStatus, JobItem, JobsView, Run } from './types'

type JobsTab = Exclude<JobsView, 'all'>
type Tab = JobsTab | 'applications' | 'rules'

const TABS: { id: Tab; label: string }[] = [
  { id: 'ranked', label: 'Para ti' },
  { id: 'applications', label: 'Candidaturas' },
  { id: 'pending', label: 'Pendientes del juez' },
  { id: 'discarded', label: 'Descartadas' },
  { id: 'failed', label: 'Sin juicio' },
  { id: 'rules', label: 'Reglas de Oro' },
]

const EMPTY: Record<JobsTab, string> = {
  ranked: 'Aún no hay ofertas que superen tu nota mínima. Lanza una búsqueda o baja la nota en Reglas de Oro.',
  pending: 'No queda nada esperando al juez.',
  discarded: 'Ninguna oferta descartada en las dos últimas semanas.',
  failed: 'El juez ha podido leer todas las ofertas.',
}

const isJobsTab = (tab: Tab): tab is JobsTab => tab !== 'applications' && tab !== 'rules'

const saved = (n: number) =>
  n === 1
    ? 'La candidatura que esperaba en este navegador ya está en tus candidaturas'
    : `Las ${n} candidaturas que esperaban en este navegador ya están en tus candidaturas`

/** Vista "Buscador": tu ranking de ofertas, juzgadas en tu equipo por el Job Hunter. */
export default function HunterView() {
  const [gate, setGate] = useState<GateState | 'ready'>('checking')
  const [token, setToken] = useState(tokenStore.get())
  const [tokenError, setTokenError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>(() => (routeSection() === 'candidaturas' ? 'applications' : 'ranked'))
  const [query, setQuery] = useState('')
  const [jobs, setJobs] = useState<JobItem[]>([])
  const [total, setTotal] = useState(0)
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState<Record<string, 'send' | 'status' | 'rejudge'>>({})
  const [autoShutdown, setAutoShutdown] = useState<number | null>(null)
  const [stopping, setStopping] = useState(false)
  // Ofertas que la IA ha puntuado desde que se cargó la lista (la búsqueda sigue en marcha).
  const [fresh, setFresh] = useState(0)
  const searchId = useId()
  const request = useRef(0)
  const tokenRef = useRef(token)
  const followedRun = useRef<string | null>(null)
  const lastJudged = useRef(0)
  const shownJudged = useRef(0)

  useEffect(() => {
    tokenRef.current = token
  })

  const authFailed = useCallback(
    (err: HunterError) => {
      if (err.code === 'HUNTER_TOKEN_MISSING') {
        setGate('no-token-configured')
        return
      }
      tokenStore.clear()
      setToken('')
      setTokenError(token ? 'Ese token no coincide con el de hunter/.env.' : null)
      setGate('needs-token')
    },
    [token],
  )

  const connectionError = useCallback(
    (err: HunterError) => {
      if (err.status === 401) authFailed(err)
      else setGate('offline')
    },
    [authFailed],
  )

  // Comprueba la API y, si el acceso directo trae un código de un solo uso, lo canjea por el token.
  const connect = useCallback(async () => {
    setGate('checking')
    let health
    try {
      health = await hunterApi.health()
    } catch {
      setGate('offline')
      return
    }
    if (!health.token_configured) {
      setGate('no-token-configured')
      return
    }
    setAutoShutdown(health.auto_shutdown_minutes ?? null)
    const code = takePairCode()
    if (code) {
      try {
        const { token: paired } = await hunterApi.pair(code)
        tokenStore.set(paired, true)
        tokenRef.current = paired
        setTokenError(null)
        setToken(paired)
        setGate('ready')
        const n = await flushOutbox(paired)
        if (n) toast.success(saved(n))
        return
      } catch (err) {
        if (!tokenRef.current) setTokenError(err instanceof Error ? err.message : null)
      }
    }
    setGate(tokenRef.current ? 'ready' : 'needs-token')
  }, [])

  useEffect(() => {
    void connect()
  }, [connect])

  const load = useCallback(
    async (append: boolean) => {
      if (gate !== 'ready' || !isJobsTab(tab)) return
      const id = ++request.current
      setLoading(true)
      try {
        const page = await hunterApi.jobs(token, { view: tab, q: query || undefined, cursor: append ? cursor : null })
        if (id !== request.current) return
        setJobs((prev) => (append ? [...prev, ...page.items] : page.items))
        setTotal(page.total)
        setCursor(page.next_cursor)
        if (!append) {
          shownJudged.current = lastJudged.current
          setFresh(0)
        }
      } catch (err) {
        if (err instanceof HunterError && (err.status === 401 || err.code === 'OFFLINE')) connectionError(err)
        else toast.error(err instanceof Error ? err.message : 'No se pudieron cargar las ofertas.')
      } finally {
        if (id === request.current) setLoading(false)
      }
    },
    [gate, tab, token, query, cursor, connectionError],
  )

  // Recarga al cambiar de pestaña o de búsqueda (con una pausa corta mientras se escribe).
  useEffect(() => {
    const timer = window.setTimeout(() => void load(false), query ? 300 : 0)
    return () => window.clearTimeout(timer)
    // Sin `load` en las dependencias: cambia con el cursor y aquí siempre se pide la primera página.
  }, [gate, tab, query, token])

  // Mientras la IA puntúa, avisa de las ofertas nuevas sin mover la lista que estás leyendo.
  const onProgress = useCallback((run: Run) => {
    lastJudged.current = run.counts.judged
    if (followedRun.current !== run.id) {
      followedRun.current = run.id // la lista recién cargada ya incluye lo puntuado hasta ahora
      shownJudged.current = run.counts.judged
      return
    }
    if (run.status === 'running') setFresh(Math.max(0, run.counts.judged - shownJudged.current))
  }, [])

  // Si no había nada que mirar, las nuevas se muestran directamente.
  useEffect(() => {
    if (fresh > 0 && tab === 'ranked' && jobs.length === 0) void load(false)
    // Solo cuando llegan ofertas nuevas.
  }, [fresh])

  const replaceJob = (updated: JobItem) => setJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)))
  const mark = (id: string, action?: 'send' | 'status' | 'rejudge') =>
    setBusy((prev) => {
      const next = { ...prev }
      if (action) next[id] = action
      else delete next[id]
      return next
    })

  const onStatus = async (job: JobItem, status: AppStatus) => {
    mark(job.id, 'status')
    try {
      replaceJob(await hunterApi.setStatus(token, job.id, status))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo guardar.')
    } finally {
      mark(job.id)
    }
  }

  const onApplied = async (job: JobItem) => {
    mark(job.id, 'status')
    try {
      const result = await registerApplication({
        id: newApplicationId(),
        source: 'hunter',
        job_id: job.id,
        company: job.company,
        title: job.title,
        url: job.sources[0]?.url ?? null,
        location: job.location,
        judge_score: job.verdict?.match_score ?? null,
      })
      replaceJob({ ...job, app_status: 'applied' })
      toast.success(
        result === 'saved'
          ? 'Apuntada en tus candidaturas'
          : 'Apuntada en este navegador: pasará a tus candidaturas cuando la API responda',
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo apuntar la candidatura.')
    } finally {
      mark(job.id)
    }
  }

  const onRejudge = async (job: JobItem) => {
    mark(job.id, 'rejudge')
    try {
      const updated = await hunterApi.rejudge(token, job.id)
      replaceJob(updated)
      toast.success(updated.verdict ? `Nueva nota: ${updated.verdict.match_score}` : 'El juez sigue sin poder leerla.')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'El juez no ha respondido.')
    } finally {
      mark(job.id)
    }
  }

  const onSend = async (job: JobItem, card: HTMLElement | null) => {
    mark(job.id, 'send')
    try {
      const handoff = await hunterApi.handoff(token, job.id)
      if (!handoff.complete) {
        toast.error(
          'Solo tenemos un extracto de esta oferta. Ábrela en "Más detalle" y pega el texto completo en el Optimizador.',
          {
            duration: 7000,
          },
        )
        return
      }
      writeHandoff({
        text: handoff.text,
        title: handoff.title,
        company: handoff.company,
        sourceUrl: handoff.source_url ?? undefined,
        language: handoff.language ?? undefined,
        location: job.location || undefined,
        jobId: job.id,
        matchScore: job.verdict?.match_score,
      })
      // La ficha se levanta de la mesa camino del Optimizador.
      if (card && animationsSupported()) {
        const lift = card.animate(
          [
            { transform: 'none', opacity: 1 },
            { transform: 'translateY(-36px) rotate(-2.5deg) scale(0.97)', opacity: 0 },
          ],
          { duration: 420, easing: EASE_HAND, fill: 'forwards' },
        )
        // Nunca se espera más de medio segundo: si el navegador frena las animaciones (pestaña en
        // segundo plano, ahorro de energía), la navegación no puede quedarse colgada de ellas.
        await Promise.race([lift.finished.catch(() => undefined), wait(500)])
      }
      navigate('optimizar')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo preparar la oferta.')
    } finally {
      mark(job.id)
    }
  }

  const shutdown = async () => {
    setStopping(true)
    try {
      await hunterApi.shutdown(token)
      toast.success('API local apagada. Para volver, abre «Buscador de empleo» desde el escritorio.')
      setGate('offline')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo apagar.')
    } finally {
      setStopping(false)
    }
  }

  return (
    <section aria-labelledby="hunter-title" className="mx-auto max-w-4xl space-y-6 px-4 pt-8 pb-16 sm:px-6">
      <div>
        <h1 id="hunter-title" className="font-serif text-3xl font-semibold tracking-tight text-balance">
          Ofertas que merecen tu tiempo
        </h1>
        <p className="mt-2 max-w-2xl text-[15px] leading-7 text-slate-600 dark:text-slate-300">
          Tu equipo busca en los portales, descarta lo que no cumple tus reglas y una IA puntúa el resto contra tu
          perfil. Cada señal lleva su cita de la oferta.
        </p>
        {gate === 'ready' && (
          <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500 dark:text-slate-400">
            <span>
              {autoShutdown
                ? `La API local se apaga sola ${autoShutdown} minutos después de cerrar el Buscador.`
                : 'La API local está encendida.'}
            </span>
            <button
              type="button"
              onClick={() => void shutdown()}
              disabled={stopping}
              className="focus-ring inline-flex items-center gap-1 rounded font-medium text-slate-600 underline-offset-2 hover:text-ink hover:underline disabled:opacity-60 dark:text-slate-300 dark:hover:text-white"
            >
              <Power className="size-3.5" aria-hidden />
              Apagar ahora
            </button>
          </p>
        )}
      </div>

      {gate !== 'ready' ? (
        <ConnectionGate
          state={gate}
          tokenError={tokenError}
          onRetry={() => void connect()}
          onToken={(value, remember) => {
            tokenStore.set(value, remember)
            setTokenError(null)
            setToken(value)
            setGate('ready')
          }}
        />
      ) : (
        <>
          <RunPanel
            token={token}
            onFinished={() => void load(false)}
            onAuthError={authFailed}
            onProgress={onProgress}
          />

          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div role="tablist" aria-label="Ofertas" className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.id}
                  onClick={() => setTab(t.id)}
                  className={cn(
                    'focus-ring h-9 shrink-0 rounded-md px-3 text-sm font-medium transition',
                    tab === t.id
                      ? 'bg-ink text-white dark:bg-white dark:text-slate-900'
                      : 'text-slate-600 hover:bg-white dark:text-slate-300 dark:hover:bg-slate-900',
                  )}
                >
                  {t.label}
                  {tab === t.id && isJobsTab(t.id) && !loading && (
                    <span className="ml-1.5 tabular-nums opacity-70">{total}</span>
                  )}
                </button>
              ))}
            </div>
            {isJobsTab(tab) && (
              <div className="relative sm:w-64">
                <label htmlFor={searchId} className="sr-only">
                  Buscar por puesto, empresa o lugar
                </label>
                <Search className="pointer-events-none absolute top-2.5 left-3 size-4 text-slate-400" aria-hidden />
                <input
                  id={searchId}
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Puesto, empresa o lugar"
                  className="focus-ring h-9 w-full rounded-md border border-slate-300 bg-paper pr-3 pl-9 text-sm dark:border-slate-700 dark:bg-slate-900"
                />
              </div>
            )}
          </div>

          {tab === 'rules' ? (
            <RulesEditor token={token} onSaved={() => setTab('ranked')} />
          ) : tab === 'applications' ? (
            <ApplicationsPanel token={token} onConnectionError={connectionError} />
          ) : (
            <div className="space-y-4" aria-busy={loading}>
              {fresh > 0 && tab === 'ranked' && jobs.length > 0 && (
                <button
                  type="button"
                  onClick={() => void load(false)}
                  className="focus-ring mx-auto flex items-center gap-2 rounded-full bg-ink px-4 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-ink/90 dark:bg-white dark:text-slate-900"
                >
                  {fresh === 1 ? 'La IA ha puntuado 1 oferta más' : `La IA ha puntuado ${fresh} ofertas más`}
                  <span aria-hidden>·</span> Actualizar la lista
                </button>
              )}
              {loading && jobs.length === 0 && (
                <p className="flex items-center gap-2 text-sm text-slate-500" role="status">
                  <LoaderCircle className="size-4 animate-spin" aria-hidden /> Cargando ofertas…
                </p>
              )}
              {!loading && jobs.length === 0 && (
                <p className="card p-5 text-sm leading-6 text-slate-600 dark:text-slate-300">
                  {query ? `Nada coincide con «${query}».` : EMPTY[tab]}
                </p>
              )}
              {jobs.map((job) => (
                <JobCard
                  key={job.id}
                  job={job}
                  busy={busy[job.id] ?? null}
                  onSend={(j, card) => void onSend(j, card)}
                  onStatus={(j, s) => void onStatus(j, s)}
                  onRejudge={(j) => void onRejudge(j)}
                  onApplied={(j) => void onApplied(j)}
                />
              ))}
              {cursor && (
                <button
                  type="button"
                  onClick={() => void load(true)}
                  disabled={loading}
                  className="focus-ring mx-auto block h-9 rounded-md px-4 text-sm font-medium text-cobalt-700 ring-1 ring-slate-300 transition hover:bg-white disabled:opacity-60 dark:text-cobalt-300 dark:ring-slate-700"
                >
                  Ver más ofertas
                </button>
              )}
            </div>
          )}
        </>
      )}
    </section>
  )
}
