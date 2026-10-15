import { Code2, Eye, Lightbulb, Mail, RotateCcw, ShieldAlert } from 'lucide-react'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'

import { flyToMark } from '../../lib/flyToMark'
import { canAnimate } from '../../lib/motion'
import { cn, formatNumber } from '../../lib/format'
import {
  containsSkill,
  experienceEntries,
  experienceNote,
  gapLabel,
  injectExperience,
  injectSkill,
} from '../../lib/injectSkill'
import type { HighlightGroup } from '../../lib/rehypeHighlightTerms'
import { UNGROUNDED_CODES, type MatchReport, type OptimizeResponse } from '../../types/api'
import { Clipboard } from '../ui/Clipboard'
import { AtsSuggestions } from './AtsSuggestions'
import { CopyButton } from './CopyButton'
import { DownloadMenu } from './DownloadMenu'
import { type ExperienceNote, GapList } from './GapList'
import { InsightList } from './InsightList'
import { KeywordList } from './KeywordList'
import { MarkdownPreview } from './MarkdownPreview'
import { MatchScoreCard } from './MatchScoreCard'
import { PitchPanel } from './PitchPanel'
import { WarningsPanel } from './WarningsPanel'

type Tab = 'preview' | 'markdown' | 'pitch'

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
  // Requisitos de la oferta en los que el usuario declara experiencia real, con su explicación.
  const [notes, setNotes] = useState<ExperienceNote[]>([])
  const previewRef = useRef<HTMLDivElement>(null)
  const { meta } = result
  const base = result.optimized_markdown
  const pitch = result.application_pitch?.trim() ?? ''
  const entries = useMemo(() => experienceEntries(base), [base])

  const markdown = useMemo(
    () => notes.reduce((md, n) => injectExperience(md, n.gap, n.note, n.target), added.reduce(injectSkill, base)),
    [added, notes, base],
  )
  /** Algo que no estaba en el CV del servidor y ahora sí: solo puede haberlo añadido el usuario. */
  const addedByUser = (term: string) => !containsSkill(base, term) && containsSkill(markdown, term)
  const suggestions = (result.ats_suggestions ?? []).filter((s) => !addedByUser(s))
  const gaps = result.gaps.filter((g) => !notes.some((n) => n.gap === g) && !addedByUser(gapLabel(g)))
  const match = useMemo(() => withUserAdditions(result.match, base, markdown), [result.match, base, markdown])

  const handleAddSkill = (skill: string, source?: HTMLElement) => {
    if (source) flyToMark(source, () => previewRef.current, skill)
    setAdded((prev) => (prev.includes(skill) ? prev : [...prev, skill]))
    toast.success('Habilidad añadida al currículum')
  }
  const handleRemoveSkill = (skill: string) => setAdded((prev) => prev.filter((s) => s !== skill))
  const handleAddNote = (note: ExperienceNote) => {
    setNotes((prev) => [...prev.filter((n) => n.gap !== note.gap), note])
    toast.success('Experiencia añadida al currículum')
  }
  const handleRemoveNote = (gap: string) => setNotes((prev) => prev.filter((n) => n.gap !== gap))

  const ungrounded = result.warnings.filter((w) => UNGROUNDED_CODES.has(w.code))
  const changes = result.changes ?? []
  // Solo para la vista previa: copiar y descargar usan siempre el Markdown sin marcas.
  const highlightGroups: HighlightGroup[] = [
    {
      kind: 'ungrounded',
      terms: ungrounded.map((w) => w.term).filter((t): t is string => Boolean(t)),
    },
    {
      kind: 'added',
      terms: [...added, ...notes.map((n) => experienceNote(n.gap, n.note, n.target))],
    },
    ...(showChanges ? [{ kind: 'change' as const, terms: changes }] : []),
  ]

  // Al llegar el resultado, el CV "se imprime" bajo la pinza y los rotuladores repasan los cambios.
  const scanRef = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const sheet = previewRef.current
    if (!canAnimate(sheet)) return
    const height = sheet.getBoundingClientRect().height
    const duration = Math.min(1600, 700 + height / 2)
    sheet.animate([{ clipPath: 'inset(0 0 100% 0)' }, { clipPath: 'inset(0 0 0% 0)' }], {
      duration,
      easing: 'cubic-bezier(0.3, 0.7, 0.2, 1)',
    })
    scanRef.current?.animate(
      [
        { transform: 'translateY(0)', opacity: 1 },
        { transform: `translateY(${height}px)`, opacity: 1, offset: 0.92 },
        { transform: `translateY(${height}px)`, opacity: 0 },
      ],
      { duration, easing: 'cubic-bezier(0.3, 0.7, 0.2, 1)', fill: 'forwards' },
    )
    sheet.querySelectorAll<HTMLElement>('mark').forEach((mark, i) => {
      mark.animate([{ backgroundSize: '0% 100%' }, { backgroundSize: '100% 100%' }], {
        duration: 420,
        delay: duration * 0.55 + Math.min(i * 45, 1400),
        easing: 'cubic-bezier(0.45, 0, 0.25, 1)',
        fill: 'backwards',
      })
    })
  }, [])

  /** Lleva al usuario al primer resaltado del término en la vista previa y lo hace parpadear. */
  const locate = (term: string) => {
    setTab('preview')
    requestAnimationFrame(() => {
      const marks = previewRef.current?.querySelectorAll<HTMLElement>('mark[data-kind="ungrounded"]') ?? []
      const target = [...marks].find((m) => m.dataset.term === term)
      if (!target) return
      target.scrollIntoView({ behavior: 'smooth', block: 'center' })
      target.animate([{ boxShadow: '0 0 0 0 rgb(245 158 11 / 0.9)' }, { boxShadow: '0 0 0 8px rgb(245 158 11 / 0)' }], {
        duration: 700,
        iterations: 2,
      })
    })
  }

  return (
    <div className="animate-fade-in-up">
      <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Tu CV optimizado</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            Generado con {meta.model} en {(meta.latency_ms / 1000).toFixed(1).replace('.', ',')} s (
            {formatNumber(meta.tokens.input + meta.tokens.output)} tokens),{' '}
            {meta.mode === 'byok' ? 'con tu API key' : 'en modo gratuito'}.
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
          className="mb-6 flex items-start gap-3 rounded-md bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-200 dark:ring-amber-500/25"
        >
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            <strong className="font-semibold">Revisa este CV antes de usarlo.</strong> Hemos marcado{' '}
            {ungrounded.length === 1 ? '1 dato que no aparece' : `${ungrounded.length} datos que no aparecen`} en tu CV
            original. La IA no ha podido corregirlo
            {ungrounded.length === 1 ? '' : 's'} automáticamente.
          </p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="card overflow-hidden">
          <div className="flex flex-wrap items-end justify-between gap-x-4 border-b border-slate-200 px-3 pt-3 dark:border-slate-800">
            <div role="tablist" aria-label="Formato del resultado" className="-mb-px flex gap-1 overflow-x-auto">
              {(
                [
                  {
                    id: 'preview',
                    label: 'Vista previa',
                    short: 'Vista previa',
                    icon: Eye,
                  },
                  {
                    id: 'markdown',
                    label: 'Markdown',
                    short: 'Markdown',
                    icon: Code2,
                  },
                  {
                    id: 'pitch',
                    label: 'Pitch para la oferta',
                    short: 'Pitch',
                    icon: Mail,
                  },
                ] as const
              )
                .filter(({ id }) => id !== 'pitch' || pitch)
                .map(({ id, label, short, icon: Icon }) => (
                  <button
                    key={id}
                    type="button"
                    role="tab"
                    id={`tab-${id}`}
                    aria-selected={tab === id}
                    aria-controls={`panel-${id}`}
                    onClick={() => setTab(id)}
                    className={cn(
                      'focus-ring inline-flex shrink-0 items-center gap-2 rounded-t-lg border-b-2 px-2.5 py-2.5 text-sm font-medium whitespace-nowrap transition sm:gap-2.5 sm:px-4',
                      tab === id
                        ? 'border-cobalt-600 text-cobalt-700 dark:border-cobalt-400 dark:text-cobalt-300'
                        : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200',
                    )}
                  >
                    <Icon className="size-4" aria-hidden />
                    <span className="sm:hidden">{short}</span>
                    <span className="hidden sm:inline">{label}</span>
                  </button>
                ))}
            </div>
            {tab === 'preview' && changes.length > 0 && (
              <ChangesToggle
                checked={showChanges}
                onChange={setShowChanges}
                count={changes.length}
                added={added.length + notes.length > 0}
              />
            )}
          </div>

          <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            {tab === 'pitch' ? (
              <PitchPanel pitch={pitch} />
            ) : tab === 'preview' ? (
              <div className="bg-desk p-3 sm:p-6 dark:bg-slate-950/60">
                {/* El CV como hoja sujeta en el tablero de pinza */}
                <Clipboard className="mx-auto max-w-3xl">
                  <div ref={previewRef} className="sheet relative px-6 pt-11 pb-8 sm:px-14 sm:pt-14 sm:pb-14">
                    <div ref={scanRef} className="print-scan" aria-hidden />
                    <MarkdownPreview markdown={markdown} highlightGroups={highlightGroups} />
                  </div>
                </Clipboard>
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
          <KeywordList match={match} added={match.matched_keywords.filter(addedByUser)} />
          <GapList
            gaps={gaps}
            notes={notes}
            entries={entries}
            onAddNote={handleAddNote}
            onRemoveNote={handleRemoveNote}
          />
          <InsightList title="Cambios realizados" items={result.changes_summary} icon={Lightbulb} tone="cobalt" />
        </aside>
      </div>
    </div>
  )
}

/** Lo que añade el usuario (sugerencias o experiencia) pasa de "falta" a "cubierta" si contiene una
 *  palabra clave de la oferta, y la puntuación se recalcula igual que en el backend (cubiertas / total). */
function withUserAdditions(match: MatchReport, base: string, markdown: string): MatchReport {
  if (markdown === base) return match
  const total = match.matched_keywords.length + match.missing_keywords.length
  const nowCovered = match.missing_keywords.filter((kw) => !containsSkill(base, kw) && containsSkill(markdown, kw))
  if (nowCovered.length === 0) return match
  const matched = [...match.matched_keywords, ...nowCovered]
  return {
    ...match,
    matched_keywords: matched,
    missing_keywords: match.missing_keywords.filter((kw) => !nowCovered.includes(kw)),
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
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 pt-1 pb-3 text-xs text-slate-600 dark:text-slate-400">
      <label className="inline-flex cursor-pointer items-center gap-2.5 font-medium">
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
        <span className="flex flex-wrap items-center gap-x-4 gap-y-1" aria-hidden>
          <span className="flex items-center gap-2">
            <span className="h-2.5 w-4 rounded-[2px] bg-marker-green" />
            Reformulado
          </span>
          <span className="flex items-center gap-2">
            <span className="h-2.5 w-4 rounded-[2px] bg-marker-amber" />
            No está en tu CV
          </span>
          {added && (
            <span className="flex items-center gap-2">
              <span className="h-2.5 w-4 rounded-[2px] bg-marker-blue" />
              Añadido por ti
            </span>
          )}
        </span>
      )}
    </div>
  )
}
