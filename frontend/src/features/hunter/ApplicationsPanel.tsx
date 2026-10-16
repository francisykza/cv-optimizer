import { Download, LoaderCircle, Plus, Search } from 'lucide-react'
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import toast from 'react-hot-toast'

import { downloadBlob } from '../../lib/export/download'
import { cn } from '../../lib/format'
import { ApplicationCard } from './ApplicationCard'
import { flushOutbox, newApplicationId, outbox, STATUS_LABEL } from './applications'
import { HunterError, hunterApi } from './hunterClient'
import type { ApplicationItem, ApplicationsPage, ApplicationStats, ApplicationStatus, ApplicationUpdate } from './types'

interface ApplicationsPanelProps {
  token: string
  /** 401 o API apagada: lo resuelve la vista (vuelve a pedir el token o enseña cómo arrancarla). */
  onConnectionError: (error: HunterError) => void
}

const percent = (part: number, total: number) => (total ? Math.round((100 * part) / total) : 0)

/** Resumen: cuántas, con qué compatibilidad y cuántas han tenido respuesta, por tramos de %. */
function Summary({ stats }: { stats: ApplicationStats }) {
  const figures: { value: string; label: string }[] = [
    { value: String(stats.total), label: stats.total === 1 ? 'candidatura' : 'candidaturas' },
    { value: String(stats.last_7_days), label: 'esta semana' },
    { value: stats.avg_ats_after === null ? '—' : `${stats.avg_ats_after} %`, label: 'compatibilidad media' },
    {
      value: String(stats.responded),
      label: `con respuesta${stats.total ? ` (${percent(stats.responded, stats.total)} %)` : ''}`,
    },
    { value: String(stats.interviews), label: stats.interviews === 1 ? 'entrevista' : 'entrevistas' },
  ]
  const bands = stats.by_band.filter((b) => b.total > 0)
  return (
    <section className="card p-5 sm:p-6" aria-label="Resumen de tus candidaturas">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-5">
        {figures.map((f) => (
          <div key={f.label}>
            <dt className="sr-only">{f.label}</dt>
            <dd>
              <span className="block font-serif text-2xl font-semibold tabular-nums">{f.value}</span>
              <span className="text-sm text-slate-600 dark:text-slate-300">{f.label}</span>
            </dd>
          </div>
        ))}
      </dl>
      {stats.total >= 3 && bands.length > 0 && (
        <div className="mt-5 border-t border-slate-200 pt-4 dark:border-slate-800">
          <h3 className="text-sm font-semibold">¿Responden más cuando el CV encaja más?</h3>
          <ul className="mt-2 space-y-1.5 text-sm">
            {bands.map((b) => (
              <li key={b.label} className="grid grid-cols-[minmax(0,11rem)_1fr_auto] items-center gap-3">
                <span className="truncate text-slate-600 dark:text-slate-300">{b.label}</span>
                <span className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800" aria-hidden>
                  <span
                    className="block h-full rounded-full bg-emerald-500"
                    style={{ width: `${percent(b.responded, b.total)}%` }}
                  />
                </span>
                <span className="tabular-nums text-slate-600 dark:text-slate-300">
                  {b.responded} de {b.total}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {stats.stale > 0 && (
        <p className="mt-4 text-sm text-amber-800 dark:text-amber-300">
          {stats.stale === 1
            ? '1 candidatura lleva más de 3 semanas sin noticias.'
            : `${stats.stale} candidaturas llevan más de 3 semanas sin noticias.`}
        </p>
      )}
    </section>
  )
}

interface ManualForm {
  company: string
  title: string
  url: string
  date: string
  score: string
  notes: string
}

const today = () => new Date().toISOString().slice(0, 10)
const EMPTY_FORM = (): ManualForm => ({ company: '', title: '', url: '', date: today(), score: '', notes: '' })

/** Alta a mano: ofertas a las que te inscribiste sin pasar por el Optimizador. */
function AddForm({ onSave, onCancel }: { onSave: (form: ManualForm) => Promise<void>; onCancel: () => void }) {
  const id = useId()
  const [form, setForm] = useState<ManualForm>(EMPTY_FORM)
  const [busy, setBusy] = useState(false)
  const field = (key: keyof ManualForm) => ({
    id: `${id}-${key}`,
    value: form[key],
    onChange: (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value })),
  })
  const input =
    'focus-ring mt-1 h-10 w-full rounded-md border border-slate-300 bg-paper px-3 text-sm dark:border-slate-700 dark:bg-slate-950'

  return (
    <form
      className="card space-y-4 p-5 sm:p-6"
      aria-label="Añadir candidatura"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        try {
          await onSave(form)
          setForm(EMPTY_FORM())
        } catch {
          // El error ya se ha mostrado; el formulario conserva lo escrito.
        } finally {
          setBusy(false)
        }
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor={`${id}-company`} className="text-sm font-medium">
            Empresa
          </label>
          <input {...field('company')} required maxLength={200} autoFocus className={input} />
        </div>
        <div>
          <label htmlFor={`${id}-title`} className="text-sm font-medium">
            Puesto
          </label>
          <input {...field('title')} required maxLength={300} className={input} />
        </div>
        <div>
          <label htmlFor={`${id}-url`} className="text-sm font-medium">
            Enlace a la oferta <span className="font-normal text-slate-500">(opcional)</span>
          </label>
          <input {...field('url')} type="url" placeholder="https://" maxLength={2048} className={input} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor={`${id}-date`} className="text-sm font-medium">
              Fecha
            </label>
            <input {...field('date')} type="date" required max={today()} className={input} />
          </div>
          <div>
            <label htmlFor={`${id}-score`} className="text-sm font-medium">
              Compatibilidad <span className="font-normal text-slate-500">(%)</span>
            </label>
            <input {...field('score')} type="number" min={0} max={100} inputMode="numeric" className={input} />
          </div>
        </div>
      </div>
      <div>
        <label htmlFor={`${id}-notes`} className="text-sm font-medium">
          Notas <span className="font-normal text-slate-500">(opcional)</span>
        </label>
        <textarea
          {...field('notes')}
          rows={2}
          maxLength={4000}
          className="focus-ring mt-1 block w-full rounded-md border border-slate-300 bg-paper px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        />
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="focus-ring inline-flex h-9 items-center gap-2 rounded-md bg-cobalt-600 px-4 text-sm font-semibold text-white transition hover:bg-cobalt-700 disabled:opacity-60"
        >
          {busy && <LoaderCircle className="size-4 animate-spin" aria-hidden />}
          Guardar candidatura
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="focus-ring h-9 rounded-md px-3 text-sm font-medium text-slate-600 transition hover:bg-white dark:text-slate-300 dark:hover:bg-slate-900"
        >
          Cancelar
        </button>
      </div>
    </form>
  )
}

const FILTERS: { value: ApplicationStatus | ''; label: string }[] = [
  { value: '', label: 'Todas' },
  ...(Object.entries(STATUS_LABEL) as [ApplicationStatus, string][]).map(([value, label]) => ({ value, label })),
]

/** Pestaña "Candidaturas" del Buscador (SPEC §18.4). */
export function ApplicationsPanel({ token, onConnectionError }: ApplicationsPanelProps) {
  const [page, setPage] = useState<ApplicationsPage | null>(null)
  const [status, setStatus] = useState<ApplicationStatus | ''>('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [waiting, setWaiting] = useState(() => outbox.list().length)
  const request = useRef(0)
  const statusId = useId()
  const searchId = useId()

  const fail = useCallback(
    (err: unknown, fallback: string) => {
      if (err instanceof HunterError && (err.status === 401 || err.code === 'OFFLINE')) onConnectionError(err)
      else toast.error(err instanceof Error ? err.message : fallback)
    },
    [onConnectionError],
  )

  const load = useCallback(async () => {
    const id = ++request.current
    try {
      const next = await hunterApi.applications(token, { status: status || undefined, q: query || undefined })
      if (id === request.current) setPage(next)
    } catch (err) {
      if (id === request.current) fail(err, 'No se pudieron cargar tus candidaturas.')
    } finally {
      if (id === request.current) setLoading(false)
    }
  }, [token, status, query, fail])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), query ? 300 : 0)
    return () => window.clearTimeout(timer)
  }, [load, query])

  const replace = (item: ApplicationItem) =>
    setPage((p) => (p ? { ...p, items: p.items.map((i) => (i.id === item.id ? item : i)) } : p))

  const change = async (item: ApplicationItem, changes: ApplicationUpdate) => {
    setBusy(item.id)
    try {
      replace(await hunterApi.updateApplication(token, item.id, changes))
      void load() // el resumen cambia con el estado
    } catch (err) {
      fail(err, 'No se pudo guardar el cambio.')
    } finally {
      setBusy(null)
    }
  }

  const remove = async (item: ApplicationItem) => {
    if (!window.confirm(`¿Borrar la candidatura a «${item.title}» en ${item.company}? No se puede deshacer.`)) return
    setBusy(item.id)
    try {
      await hunterApi.deleteApplication(token, item.id)
      await load()
    } catch (err) {
      fail(err, 'No se pudo borrar.')
    } finally {
      setBusy(null)
    }
  }

  const exportCsv = async () => {
    setExporting(true)
    try {
      downloadBlob(await hunterApi.exportApplications(token), 'candidaturas.csv')
    } catch (err) {
      fail(err, 'No se pudo exportar.')
    } finally {
      setExporting(false)
    }
  }

  const addManual = async (form: ManualForm) => {
    try {
      await hunterApi.createApplication(token, {
        id: newApplicationId(),
        source: 'manual',
        company: form.company.trim(),
        title: form.title.trim(),
        url: form.url.trim() || null,
        // Mediodía: ningún huso horario lo cambia de día.
        applied_at: new Date(`${form.date}T12:00:00`).toISOString(),
        ats_score_after: form.score === '' ? null : Math.max(0, Math.min(100, Math.round(Number(form.score)))),
        notes: form.notes.trim(),
      })
      setAdding(false)
      toast.success('Candidatura guardada')
      await load()
    } catch (err) {
      fail(err, 'No se pudo guardar la candidatura.')
      throw err
    }
  }

  const retryWaiting = async () => {
    const saved = await flushOutbox(token)
    setWaiting(outbox.list().length)
    if (saved) {
      toast.success(saved === 1 ? 'Candidatura guardada' : `${saved} candidaturas guardadas`)
      await load()
    }
  }

  const empty = !loading && page !== null && page.total === 0

  return (
    <div className="space-y-4">
      {page && page.stats.total > 0 && <Summary stats={page.stats} />}

      {waiting > 0 && (
        <p className="card flex flex-wrap items-center gap-x-3 gap-y-1 p-4 text-sm">
          {waiting === 1
            ? '1 candidatura espera en este navegador a que la API la guarde.'
            : `${waiting} candidaturas esperan en este navegador a que la API las guarde.`}
          <button
            type="button"
            onClick={() => void retryWaiting()}
            className="focus-ring rounded font-medium text-cobalt-700 underline-offset-2 hover:underline dark:text-cobalt-300"
          >
            Guardarlas ahora
          </button>
        </p>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor={statusId} className="text-sm text-slate-600 dark:text-slate-400">
              Estado
            </label>
            <select
              id={statusId}
              value={status}
              onChange={(e) => setStatus(e.target.value as ApplicationStatus | '')}
              className="focus-ring mt-1 block h-9 rounded-md border border-slate-300 bg-paper px-2.5 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              {FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
          <div className="relative w-full sm:w-56">
            <label htmlFor={searchId} className="sr-only">
              Buscar por empresa, puesto o nota
            </label>
            <Search className="pointer-events-none absolute top-2.5 left-3 size-4 text-slate-400" aria-hidden />
            <input
              id={searchId}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Empresa, puesto o nota"
              className="focus-ring h-9 w-full rounded-md border border-slate-300 bg-paper pr-3 pl-9 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void exportCsv()}
            disabled={exporting || !page?.stats.total}
            className="focus-ring inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm font-medium text-ink ring-1 ring-slate-300 transition hover:bg-white disabled:opacity-50 dark:text-slate-100 dark:ring-slate-700 dark:hover:bg-slate-900"
          >
            {exporting ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
            ) : (
              <Download className="size-4" aria-hidden />
            )}
            Exportar a Excel
          </button>
          <button
            type="button"
            onClick={() => setAdding((a) => !a)}
            aria-expanded={adding}
            className={cn(
              'focus-ring inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm font-semibold transition',
              adding
                ? 'bg-ink text-white dark:bg-white dark:text-slate-900'
                : 'bg-cobalt-600 text-white hover:bg-cobalt-700',
            )}
          >
            <Plus className="size-4" aria-hidden />
            Añadir a mano
          </button>
        </div>
      </div>

      {adding && <AddForm onSave={addManual} onCancel={() => setAdding(false)} />}

      <div className="space-y-4" aria-busy={loading}>
        {loading && !page && (
          <p className="flex items-center gap-2 text-sm text-slate-500" role="status">
            <LoaderCircle className="size-4 animate-spin" aria-hidden /> Cargando tus candidaturas…
          </p>
        )}
        {empty && (
          <p className="card p-5 text-sm leading-6 text-slate-600 dark:text-slate-300">
            {status || query
              ? 'Ninguna candidatura coincide con el filtro.'
              : 'Aún no has apuntado ninguna candidatura. Cuando te inscribas en una oferta, pulsa «Me he inscrito con este CV» en el Optimizador o «Ya me he inscrito» en su ficha del Buscador. También puedes añadirla a mano.'}
          </p>
        )}
        {page?.items.map((item) => (
          <ApplicationCard
            key={item.id}
            app={item}
            busy={busy === item.id}
            onChange={(changes) => void change(item, changes)}
            onDelete={() => void remove(item)}
            loadDetail={() => hunterApi.application(token, item.id)}
          />
        ))}
      </div>
    </div>
  )
}
