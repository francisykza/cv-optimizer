import { LoaderCircle } from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import toast from 'react-hot-toast'

import { HunterError, hunterApi } from './hunterClient'
import type { GoldenRules, SimulationReport } from './types'

const splitTerms = (value: string) =>
  value
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)

function TermsField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string
  hint: string
  value: string[]
  onChange: (terms: string[]) => void
}) {
  const id = useId()
  const [text, setText] = useState(value.join(', '))
  useEffect(() => setText(value.join(', ')), [value])
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <p id={`${id}-h`} className="text-xs text-slate-500 dark:text-slate-400">
        {hint}
      </p>
      <textarea
        id={id}
        rows={2}
        value={text}
        aria-describedby={`${id}-h`}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => onChange(splitTerms(text))}
        className="focus-ring mt-1 w-full resize-y rounded-md border border-slate-300 bg-paper px-3 py-2 text-sm leading-6 dark:border-slate-700 dark:bg-slate-950"
      />
    </div>
  )
}

function NumberField({
  label,
  hint,
  value,
  min,
  max,
  onChange,
}: {
  label: string
  hint: string
  value: number | null
  min: number
  max: number
  onChange: (n: number | null) => void
}) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <p id={`${id}-h`} className="text-xs text-slate-500 dark:text-slate-400">
        {hint}
      </p>
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        value={value ?? ''}
        aria-describedby={`${id}-h`}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        className="focus-ring mt-1 h-10 w-28 rounded-md border border-slate-300 bg-paper px-3 text-sm tabular-nums dark:border-slate-700 dark:bg-slate-950"
      />
    </div>
  )
}

interface RulesEditorProps {
  token: string
  onSaved: () => void
}

/** Reglas de Oro: los campos que más se tocan, "ver qué cambiaría" antes de guardar y JSON para el resto. */
export function RulesEditor({ token, onSaved }: RulesEditorProps) {
  const [rules, setRules] = useState<GoldenRules | null>(null)
  const [version, setVersion] = useState('')
  const [json, setJson] = useState<string | null>(null)
  const [report, setReport] = useState<SimulationReport | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const [busy, setBusy] = useState<'simulate' | 'save' | null>(null)

  useEffect(() => {
    hunterApi
      .rules(token)
      .then((r) => {
        setRules(r.rules)
        setVersion(r.version)
      })
      .catch((err: Error) => setErrors([err.message]))
  }, [token])

  if (!rules) {
    return errors.length ? (
      <p className="card p-5 text-sm text-rose-700 dark:text-rose-400">{errors[0]}</p>
    ) : (
      <p className="card flex items-center gap-2 p-5 text-sm">
        <LoaderCircle className="size-4 animate-spin" aria-hidden /> Cargando tus reglas…
      </p>
    )
  }

  const update = (patch: (r: GoldenRules) => GoldenRules) => {
    setRules((r) => (r ? patch(structuredClone(r)) : r))
    setReport(null)
  }

  /** Las reglas a enviar: las del JSON si se está editando en crudo. */
  const current = (): GoldenRules | null => {
    if (json === null) return rules
    try {
      return JSON.parse(json) as GoldenRules
    } catch {
      setErrors(['El JSON no es válido: revisa comas y comillas.'])
      return null
    }
  }

  const handle = async (kind: 'simulate' | 'save') => {
    const draft = current()
    if (!draft) return
    setBusy(kind)
    setErrors([])
    try {
      if (kind === 'simulate') {
        setReport(await hunterApi.simulate(token, draft))
      } else {
        const saved = await hunterApi.saveRules(token, draft)
        setVersion(saved.version)
        setRules(draft)
        setJson(null)
        setReport(null)
        toast.success(
          `Reglas guardadas. ${saved.now_pending_judge} ofertas vuelven a la cola del juez y ${saved.now_discarded} pasan a descartadas.`,
        )
        onSaved()
      }
    } catch (err) {
      if (err instanceof HunterError && err.details?.length) {
        setErrors(err.details.map((d) => `${d.path}: ${d.message}`))
      } else {
        setErrors([err instanceof Error ? err.message : 'No se pudo completar la operación.'])
      }
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="card space-y-6 p-5 sm:p-6" aria-labelledby="rules-title">
      <div>
        <h2 id="rules-title" className="text-base font-semibold">
          Reglas de Oro
        </h2>
        <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
          Lo que no cumpla estas reglas se descarta sin gastar tokens. Ante la duda, la oferta pasa.
        </p>
      </div>

      {json === null ? (
        <div className="grid gap-5 md:grid-cols-2">
          <NumberField
            label="Años de experiencia que aceptas como máximo"
            hint="Se descartan las que piden más. Vacío: no se mira."
            value={rules.experience.max_years_required}
            min={0}
            max={30}
            onChange={(n) => update((r) => ({ ...r, experience: { ...r.experience, max_years_required: n } }))}
          />
          <NumberField
            label="Nota mínima para salir en tu ranking"
            hint="Las que el juez puntúa por debajo quedan fuera de la vista principal."
            value={rules.judge.min_score_to_show}
            min={0}
            max={100}
            onChange={(n) => update((r) => ({ ...r, judge: { ...r.judge, min_score_to_show: n ?? 0 } }))}
          />
          <TermsField
            label="Dónde aceptas ir a la oficina"
            hint="Municipios, separados por comas. Fuera de ellos, solo remoto."
            value={rules.location.onsite_allowed_areas}
            onChange={(t) => update((r) => ({ ...r, location: { ...r.location, onsite_allowed_areas: t } }))}
          />
          <TermsField
            label="Palabras del título que descartan la oferta"
            hint="Por ejemplo senior, lead o manager."
            value={rules.seniority.exclude_title_terms}
            onChange={(t) => update((r) => ({ ...r, seniority: { exclude_title_terms: t } }))}
          />
          <TermsField
            label="Términos imprescindibles"
            hint="La oferta debe mencionar al menos uno."
            value={rules.required_any.terms}
            onChange={(t) => update((r) => ({ ...r, required_any: { ...r.required_any, terms: t } }))}
          />
          <TermsField
            label="Empresas que no quieres ver"
            hint="Nombres separados por comas."
            value={rules.blacklists.companies}
            onChange={(t) => update((r) => ({ ...r, blacklists: { ...r.blacklists, companies: t } }))}
          />
          <label className="flex items-center gap-2 text-sm md:col-span-2">
            <input
              type="checkbox"
              checked={rules.location.accept_remote}
              onChange={(e) => update((r) => ({ ...r, location: { ...r.location, accept_remote: e.target.checked } }))}
              className="size-4 accent-cobalt-600"
            />
            Acepto puestos en remoto
          </label>
        </div>
      ) : (
        <div>
          <label htmlFor="rules-json" className="text-sm font-medium">
            Todas las reglas (JSON)
          </label>
          <textarea
            id="rules-json"
            value={json}
            onChange={(e) => {
              setJson(e.target.value)
              setReport(null)
            }}
            spellCheck={false}
            rows={22}
            className="focus-ring mt-1 w-full rounded-md border border-slate-300 bg-paper p-3 font-mono text-[13px] leading-5 dark:border-slate-700 dark:bg-slate-950"
          />
        </div>
      )}

      {errors.length > 0 && (
        <ul className="space-y-1 text-sm text-rose-700 dark:text-rose-400" role="alert">
          {errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}

      {report && (
        <div className="rounded-md bg-desk p-4 text-sm leading-6 dark:bg-slate-950" role="status">
          <p>
            Con estas reglas pasarían <strong>{report.proposed.kept}</strong> de las {report.total} ofertas de la última
            semana. Ahora pasan {report.current.kept}.
          </p>
          {report.newly_discarded.length > 0 && (
            <>
              <p className="mt-2 font-medium">Dejarías de ver:</p>
              <ul className="list-disc pl-5">
                {report.newly_discarded.slice(0, 5).map((j) => (
                  <li key={j.job_id}>
                    {j.title}, {j.company}. <span className="text-slate-500">{j.rule_label}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {report.newly_kept.length > 0 && (
            <>
              <p className="mt-2 font-medium">Recuperarías:</p>
              <ul className="list-disc pl-5">
                {report.newly_kept.slice(0, 5).map((j) => (
                  <li key={j.job_id}>
                    {j.title}, {j.company}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void handle('simulate')}
          disabled={busy !== null}
          className="focus-ring inline-flex h-9 items-center gap-2 rounded-md px-3.5 text-sm font-medium ring-1 ring-slate-300 transition hover:bg-slate-50 disabled:opacity-60 dark:ring-slate-700 dark:hover:bg-slate-800"
        >
          {busy === 'simulate' && <LoaderCircle className="size-4 animate-spin" aria-hidden />}
          Ver qué cambiaría
        </button>
        <button
          type="button"
          onClick={() => void handle('save')}
          disabled={busy !== null}
          className="focus-ring inline-flex h-9 items-center gap-2 rounded-md bg-cobalt-600 px-3.5 text-sm font-semibold text-white transition hover:bg-cobalt-700 disabled:opacity-60"
        >
          {busy === 'save' && <LoaderCircle className="size-4 animate-spin" aria-hidden />}
          Guardar reglas
        </button>
        <button
          type="button"
          onClick={() => {
            setErrors([])
            setReport(null)
            if (json === null) {
              setJson(JSON.stringify(rules, null, 2))
              return
            }
            const parsed = current() // conserva lo editado en el JSON
            if (parsed) {
              setRules(parsed)
              setJson(null)
            }
          }}
          className="focus-ring ml-auto h-9 rounded-md px-2 text-sm font-medium text-cobalt-700 transition hover:bg-cobalt-50 dark:text-cobalt-300 dark:hover:bg-slate-800"
        >
          {json === null ? 'Editar todas las reglas' : 'Volver al formulario'}
        </button>
        <span className="w-full text-xs text-slate-500 dark:text-slate-400">Versión activa {version}</span>
      </div>
    </section>
  )
}
