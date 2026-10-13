import { Code2, Eye, FileCheck2, Lightbulb, RotateCcw, ShieldAlert } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'

import { cn, formatNumber } from '../../lib/format'
import { injectSkill } from '../../lib/injectSkill'
import type { HighlightGroup } from '../../lib/rehypeHighlightTerms'
import { UNGROUNDED_CODES, type MatchReport, type OptimizeResponse } from '../../types/api'
import { AtsSuggestions } from './AtsSuggestions'
import { CopyButton } from './CopyButton'
import { DownloadMenu } from './DownloadMenu'
import { InsightList } from './InsightList'
import { KeywordList } from './KeywordList'
import { MarkdownPreview } from './MarkdownPreview'
import { MatchScoreCard } from './MatchScoreCard'
import { WarningsPanel } from './WarningsPanel'

type Tab = 'preview' | 'markdown'

interface ResultViewerProps {
  result: OptimizeResponse
  onReset: () => void
}

export function ResultViewer({ result, onReset }: ResultViewerProps) {
  const [tab, setTab] = useState<Tab>('preview')
  const [showChanges, setShowChanges] = useState(true)
  // Habilidades sugeridas que el usuario ha decidido añadir. El CV visible se deriva del Markdown
  // del servidor: quitar una es volver a calcularlo sin ella, sin riesgo de corromper el texto.
  const [added, setAdded] = useState<string[]>([])
  const previewRef = useRef<HTMLDivElement>(null)
  const { meta } = result

  const markdown = useMemo(() => added.reduce(injectSkill, result.optimized_markdown), [added, result.optimized_markdown])
  const suggestions = (result.ats_suggestions ?? []).filter((s) => !added.includes(s))
  const match = useMemo(() => withAddedSkills(result.match, added), [result.match, added])

  const handleAddSkill = (skill: string) => {
    setAdded((prev) => (prev.includes(skill) ? prev : [...prev, skill]))
    toast.success('Habilidad añadida al currículum')
  }
  const handleRemoveSkill = (skill: string) => setAdded((prev) => prev.filter((s) => s !== skill))

  const ungrounded = result.warnings.filter((w) => UNGROUNDED_CODES.has(w.code))
  const changes = result.changes ?? []
  // Solo para la vista previa: copiar y descargar usan siempre el Markdown sin marcas.
  const highlightGroups: HighlightGroup[] = [
    { kind: 'ungrounded', terms: ungrounded.map((w) => w.term).filter((t): t is string => Boolean(t)) },
    { kind: 'added', terms: added },
    ...(showChanges ? [{ kind: 'change' as const, terms: changes }] : []),
  ]

  /** Lleva al usuario al primer resaltado del término en la vista previa y lo hace parpadear. */
  const locate = (term: string) => {
    setTab('preview')
    requestAnimationFrame(() => {
      const marks = previewRef.current?.querySelectorAll<HTMLElement>('mark[data-kind="ungrounded"]') ?? []
      const target = [...marks].find((m) => m.dataset.term === term)
      if (!target) return
      target.scrollIntoView({ behavior: 'smooth', block: 'center' })
      target.animate(
        [{ boxShadow: '0 0 0 0 rgb(245 158 11 / 0.9)' }, { boxShadow: '0 0 0 8px rgb(245 158 11 / 0)' }],
        { duration: 700, iterations: 2 },
      )
    })
  }

  return (
    <div className="animate-fade-in-up">
      <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="flex items-center gap-2 text-sm font-medium text-emerald-700 dark:text-emerald-400">
            <FileCheck2 className="size-4" aria-hidden /> Optimización completada
          </p>
          <h2 className="mt-1 text-2xl font-bold tracking-tight">Tu CV optimizado</h2>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {meta.model} · {(meta.latency_ms / 1000).toFixed(1)} s ·{' '}
            {formatNumber(meta.tokens.input + meta.tokens.output)} tokens ·{' '}
            {meta.mode === 'byok' ? 'con tu API key' : 'modo gratuito'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <CopyButton text={markdown} />
          <DownloadMenu markdown={markdown} />
          <button
            type="button"
            onClick={onReset}
            className="focus-ring inline-flex h-10 items-center gap-2 rounded-lg px-3 text-sm font-medium text-slate-600 transition hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            <RotateCcw className="size-4" aria-hidden /> Empezar de nuevo
          </button>
        </div>
      </div>

      {result.quality === 'needs_review' && (
        <div
          role="status"
          className="mb-6 flex items-start gap-3 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-200 dark:ring-amber-500/25"
        >
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            <strong className="font-semibold">Revisa este CV antes de usarlo.</strong> Hemos marcado{' '}
            {ungrounded.length === 1 ? '1 dato que no aparece' : `${ungrounded.length} datos que no aparecen`} en tu
            CV original. La IA no ha podido corregirlo{ungrounded.length === 1 ? '' : 's'} automáticamente.
          </p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="card overflow-hidden">
          <div className="flex flex-wrap items-end justify-between gap-x-4 border-b border-slate-200 px-3 pt-3 dark:border-slate-800">
          <div role="tablist" aria-label="Formato del resultado" className="flex gap-1">
            {(
              [
                { id: 'preview', label: 'Vista previa', icon: Eye },
                { id: 'markdown', label: 'Markdown', icon: Code2 },
              ] as const
            ).map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                role="tab"
                id={`tab-${id}`}
                aria-selected={tab === id}
                aria-controls={`panel-${id}`}
                onClick={() => setTab(id)}
                className={cn(
                  'focus-ring -mb-px inline-flex items-center gap-2 rounded-t-lg border-b-2 px-4 py-2.5 text-sm font-medium transition',
                  tab === id
                    ? 'border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300'
                    : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200',
                )}
              >
                <Icon className="size-4" aria-hidden /> {label}
              </button>
            ))}
          </div>
          {tab === 'preview' && changes.length > 0 && (
            <ChangesToggle checked={showChanges} onChange={setShowChanges} count={changes.length} added={added.length > 0} />
          )}
          </div>

          <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            {tab === 'preview' ? (
              <div className="bg-slate-100/60 p-3 sm:p-6 dark:bg-slate-950/40">
                {/* "Hoja" de papel para que se perciba como un documento */}
                <div
                  ref={previewRef}
                  className="mx-auto max-w-3xl rounded-lg bg-white px-6 py-8 shadow-md shadow-slate-900/5 ring-1 ring-slate-200 sm:px-12 sm:py-12 dark:bg-slate-900 dark:ring-slate-800"
                >
                  <MarkdownPreview markdown={markdown} highlightGroups={highlightGroups} />
                </div>
              </div>
            ) : (
              <pre className="max-h-[70vh] overflow-auto bg-slate-950 p-5 font-mono text-[13px] leading-relaxed whitespace-pre-wrap text-slate-200">
                <code>{markdown}</code>
              </pre>
            )}
          </div>
        </div>

        <aside className="space-y-6" aria-label="Informe de compatibilidad">
          <AtsSuggestions suggestions={suggestions} added={added} onAdd={handleAddSkill} onRemove={handleRemoveSkill} />
          <WarningsPanel warnings={result.warnings} onLocate={locate} />
          <MatchScoreCard match={match} />
          <KeywordList match={match} added={added} />
          <InsightList
            title="Lo que pide la oferta y no está en tu CV"
            description="No lo hemos añadido porque no aparece en tu CV original. Si lo tienes, inclúyelo tú mismo."
            items={result.gaps}
            icon={ShieldAlert}
            tone="amber"
          />
          <InsightList title="Cambios realizados" items={result.changes_summary} icon={Lightbulb} tone="indigo" />
        </aside>
      </div>
    </div>
  )
}

/** Las habilidades que añade el usuario pasan de "faltan" a "cubiertas" y la puntuación se
 *  recalcula igual que en el backend (cubiertas / total). */
function withAddedSkills(match: MatchReport, added: string[]): MatchReport {
  if (added.length === 0) return match
  const total = match.matched_keywords.length + match.missing_keywords.length
  const matched = [...match.matched_keywords, ...match.missing_keywords.filter((kw) => added.includes(kw))]
  return {
    ...match,
    matched_keywords: matched,
    missing_keywords: match.missing_keywords.filter((kw) => !added.includes(kw)),
    score_after: total ? Math.round((100 * matched.length) / total) : match.score_after,
  }
}

interface ChangesToggleProps {
  checked: boolean
  onChange: (v: boolean) => void
  count: number
  added: boolean
}

function ChangesToggle({ checked, onChange, count, added }: ChangesToggleProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pb-2.5 text-xs text-slate-600 dark:text-slate-400">
      <label className="inline-flex cursor-pointer items-center gap-2 font-medium">
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          aria-label="Resaltar cambios"
          onClick={() => onChange(!checked)}
          className={cn(
            'focus-ring relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors',
            checked ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-700',
          )}
        >
          <span
            className={cn(
              'inline-block size-4 rounded-full bg-white shadow transition-transform',
              checked ? 'translate-x-[18px]' : 'translate-x-0.5',
            )}
          />
        </button>
        Resaltar cambios ({count})
      </label>
      {checked && (
        <span className="flex items-center gap-3" aria-hidden>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-emerald-200 ring-1 ring-emerald-300 dark:bg-emerald-500/30 dark:ring-emerald-500/40" />
            Reformulado
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-amber-200 ring-1 ring-amber-300 dark:bg-amber-400/30 dark:ring-amber-400/40" />
            No está en tu CV
          </span>
          {added && (
            <span className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm bg-sky-100 ring-1 ring-sky-300 dark:bg-sky-500/30 dark:ring-sky-500/40" />
              Añadido por ti
            </span>
          )}
        </span>
      )}
    </div>
  )
}
