import { ChevronDown, Download, FileCode2, FileText, FileType2, LoaderCircle } from 'lucide-react'
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'

import { exportCv, type ExportFormat } from '../../lib/export/download'
import { cn } from '../../lib/format'

const OPTIONS: { format: ExportFormat; label: string; hint: string; icon: typeof FileText; recommended?: boolean }[] = [
  { format: 'docx', label: 'Word (.docx)', hint: 'El formato que mejor leen todos los ATS', icon: FileType2, recommended: true },
  { format: 'pdf', label: 'PDF', hint: 'Con texto real, legible por los ATS modernos', icon: FileText },
  { format: 'md', label: 'Markdown (.md)', hint: 'Texto plano para editar', icon: FileCode2 },
]

/** Menú de descarga. Exporta siempre el Markdown limpio: nunca incluye los resaltados de la vista previa. */
export function DownloadMenu({ markdown }: { markdown: string }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<ExportFormat | null>(null)
  const [error, setError] = useState<string | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const itemsRef = useRef<(HTMLButtonElement | null)[]>([])
  const menuId = useId()

  useEffect(() => {
    if (!open) return
    itemsRef.current[0]?.focus()
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  const choose = async (format: ExportFormat) => {
    setOpen(false)
    setError(null)
    setBusy(format)
    try {
      await exportCv(markdown, format)
    } catch {
      setError('No se pudo generar el archivo. Inténtalo de nuevo.')
    } finally {
      setBusy(null)
    }
  }

  const onMenuKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const items = itemsRef.current.filter(Boolean) as HTMLButtonElement[]
    const index = items.indexOf(document.activeElement as HTMLButtonElement)
    if (e.key === 'Escape') {
      setOpen(false)
      rootRef.current?.querySelector<HTMLButtonElement>('button')?.focus()
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const next = (index + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length
      items[next]?.focus()
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={busy !== null}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        className="focus-ring inline-flex h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium shadow-sm transition hover:bg-slate-50 disabled:cursor-wait disabled:opacity-70 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
      >
        {busy ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : <Download className="size-4" aria-hidden />}
        <span aria-live="polite">{busy ? 'Generando…' : 'Descargar'}</span>
        <ChevronDown className={cn('size-4 transition-transform', open && 'rotate-180')} aria-hidden />
      </button>

      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label="Formato de descarga"
          onKeyDown={onMenuKeyDown}
          className="absolute right-0 z-20 mt-2 w-72 origin-top-right animate-fade-in-up rounded-md border border-slate-200 bg-white p-1.5 shadow-lg shadow-slate-900/10 dark:border-slate-700 dark:bg-slate-900"
        >
          {OPTIONS.map(({ format, label, hint, icon: Icon, recommended }, i) => (
            <button
              key={format}
              ref={(el) => {
                itemsRef.current[i] = el
              }}
              type="button"
              role="menuitem"
              onClick={() => void choose(format)}
              className="focus-ring flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-slate-50 focus:bg-slate-50 dark:hover:bg-slate-800 dark:focus:bg-slate-800"
            >
              <Icon className="mt-0.5 size-4 shrink-0 text-cobalt-600 dark:text-cobalt-400" aria-hidden />
              <span className="min-w-0">
                <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
                  {label}
                  {recommended && (
                    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
                      Recomendado para ATS
                    </span>
                  )}
                </span>
                <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">{hint}</span>
              </span>
            </button>
          ))}
        </div>
      )}

      {error && (
        <p role="alert" className="absolute right-0 mt-2 w-64 text-right text-xs text-rose-600 dark:text-rose-400">
          {error}
        </p>
      )}
    </div>
  )
}
