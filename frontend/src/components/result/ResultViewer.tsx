import { Code2, Download, Eye, FileCheck2, Lightbulb, RotateCcw, ShieldAlert } from 'lucide-react'
import { useRef, useState } from 'react'

import { cn, formatNumber } from '../../lib/format'
import { UNGROUNDED_CODES, type OptimizeResponse } from '../../types/api'
import { CopyButton } from './CopyButton'
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

function downloadMarkdown(markdown: string) {
  const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = 'cv-optimizado.md'
  link.click()
  URL.revokeObjectURL(url)
}

export function ResultViewer({ result, onReset }: ResultViewerProps) {
  const [tab, setTab] = useState<Tab>('preview')
  const previewRef = useRef<HTMLDivElement>(null)
  const { optimized_markdown: markdown, meta } = result

  const ungrounded = result.warnings.filter((w) => UNGROUNDED_CODES.has(w.code))
  const highlightTerms = ungrounded.map((w) => w.term).filter((t): t is string => Boolean(t))

  /** Lleva al usuario al primer resaltado del término en la vista previa y lo hace parpadear. */
  const locate = (term: string) => {
    setTab('preview')
    requestAnimationFrame(() => {
      const marks = previewRef.current?.querySelectorAll<HTMLElement>('mark[data-term]') ?? []
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
          <button
            type="button"
            onClick={() => downloadMarkdown(markdown)}
            className="focus-ring inline-flex h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium shadow-sm transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
          >
            <Download className="size-4" aria-hidden /> Descargar .md
          </button>
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
          <div role="tablist" aria-label="Formato del resultado" className="flex gap-1 border-b border-slate-200 px-3 pt-3 dark:border-slate-800">
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

          <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            {tab === 'preview' ? (
              <div className="bg-slate-100/60 p-3 sm:p-6 dark:bg-slate-950/40">
                {/* "Hoja" de papel para que se perciba como un documento */}
                <div
                  ref={previewRef}
                  className="mx-auto max-w-3xl rounded-lg bg-white px-6 py-8 shadow-md shadow-slate-900/5 ring-1 ring-slate-200 sm:px-12 sm:py-12 dark:bg-slate-900 dark:ring-slate-800"
                >
                  <MarkdownPreview markdown={markdown} highlightTerms={highlightTerms} />
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
          <WarningsPanel warnings={result.warnings} onLocate={locate} />
          <MatchScoreCard match={result.match} />
          <KeywordList match={result.match} />
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
