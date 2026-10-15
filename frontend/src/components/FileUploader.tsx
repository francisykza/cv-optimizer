import { CheckCircle2, CloudUpload, FileText, HardDrive, TriangleAlert, X } from 'lucide-react'
import { useId, useRef, useState, type DragEvent, type KeyboardEvent } from 'react'

import type { CvMemoryStatus } from '../hooks/useCvMemory'
import { MAX_PDF_BYTES, MAX_PDF_MB } from '../lib/constants'
import { cn, formatBytes } from '../lib/format'
import { SectionCard } from './ui/SectionCard'

export interface CvMemoryControls {
  remember: boolean
  status: CvMemoryStatus
  onRememberChange: (remember: boolean) => void
  onForget: () => void
}

interface FileUploaderProps {
  file: File | null
  onFileChange: (file: File | null) => void
  disabled?: boolean
  /** Memoria local opcional del CV (desactivada por defecto). */
  memory?: CvMemoryControls
}

export function validatePdf(file: File): string | null {
  const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
  if (!isPdf) return 'Solo se admiten archivos PDF.'
  if (file.size > MAX_PDF_BYTES) return `El archivo pesa ${formatBytes(file.size)}; el máximo es ${MAX_PDF_MB} MB.`
  if (file.size === 0) return 'El archivo está vacío.'
  return null
}

export function FileUploader({ file, onFileChange, disabled, memory }: FileUploaderProps) {
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const dragDepth = useRef(0)
  const hintId = useId()

  const accept = (candidate: File | undefined) => {
    if (!candidate) return
    const problem = validatePdf(candidate)
    setError(problem)
    onFileChange(problem ? null : candidate)
  }

  const openPicker = () => {
    if (!disabled) inputRef.current?.click()
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    dragDepth.current = 0
    setDragging(false)
    if (!disabled) accept(e.dataTransfer.files[0])
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      openPicker()
    }
  }

  return (
    <SectionCard step={1} title="Sube tu CV" description="En PDF con texto seleccionable (no escaneado).">
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        data-testid="file-input"
        onChange={(e) => {
          accept(e.target.files?.[0])
          e.target.value = '' // permite volver a elegir el mismo archivo
        }}
      />

      {file ? (
        <div className="relative flex flex-1 animate-fade-in-up flex-col items-center justify-center rounded-md border border-emerald-200 bg-emerald-50/50 px-6 py-10 text-center dark:border-emerald-500/20 dark:bg-emerald-500/5">
          <button
            type="button"
            onClick={() => {
              onFileChange(null)
              setError(null)
            }}
            disabled={disabled}
            className="focus-ring absolute right-2.5 top-2.5 flex size-8 items-center justify-center rounded-md text-slate-500 transition hover:bg-white hover:text-rose-600 disabled:opacity-50 dark:hover:bg-slate-800"
            aria-label={`Quitar ${file.name}`}
          >
            <X className="size-4" />
          </button>

          <div className="relative">
            <div className="flex size-14 items-center justify-center rounded-lg bg-white text-rose-600 shadow-sm ring-1 ring-slate-200 dark:bg-slate-900 dark:text-rose-400 dark:ring-slate-700">
              <FileText className="size-7" aria-hidden />
            </div>
            <CheckCircle2
              className="absolute -bottom-1.5 -right-1.5 size-5 rounded-full bg-white text-emerald-500 dark:bg-slate-950"
              aria-hidden
            />
          </div>
          <p className="mt-4 max-w-full truncate text-sm font-medium" title={file.name}>
            {file.name}
          </p>
          <p className="mt-1 text-xs text-emerald-700 dark:text-emerald-400">
            {formatBytes(file.size)}, listo para optimizar
          </p>
          {memory && <MemoryStatus status={memory.status} />}
          <div className="mt-4 flex flex-wrap items-center justify-center gap-x-5 gap-y-2">
            <button
              type="button"
              onClick={openPicker}
              disabled={disabled}
              className="focus-ring rounded-md text-sm font-medium text-cobalt-600 underline-offset-4 hover:underline disabled:opacity-50 dark:text-cobalt-400"
            >
              Cambiar archivo
            </button>
            {memory?.remember && (
              <button
                type="button"
                onClick={memory.onForget}
                disabled={disabled}
                className="focus-ring rounded-md text-sm font-medium text-slate-600 underline-offset-4 hover:text-rose-700 hover:underline disabled:opacity-50 dark:text-slate-400 dark:hover:text-rose-400"
              >
                Olvidar memoria local
              </button>
            )}
          </div>
          {memory && (
            <label className="mt-4 inline-flex cursor-pointer items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={memory.remember}
                onChange={(e) => memory.onRememberChange(e.target.checked)}
                disabled={disabled}
                className="size-4 rounded border-slate-400 accent-cobalt-600"
              />
              Recordar mi CV en este navegador
            </label>
          )}
        </div>
      ) : (
        <div
          role="button"
          tabIndex={disabled ? -1 : 0}
          aria-disabled={disabled}
          aria-describedby={hintId}
          aria-label="Seleccionar o arrastrar el CV en PDF"
          onClick={openPicker}
          onKeyDown={handleKeyDown}
          onDragEnter={(e) => {
            e.preventDefault()
            dragDepth.current += 1
            setDragging(true)
          }}
          onDragLeave={(e) => {
            e.preventDefault()
            dragDepth.current -= 1
            if (dragDepth.current <= 0) setDragging(false)
          }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          className={cn(
            'focus-ring group flex flex-1 cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed px-6 py-10 text-center transition-all duration-200',
            dragging
              ? 'scale-[1.01] border-cobalt-500 bg-cobalt-50 dark:bg-cobalt-500/10'
              : error
                ? 'border-rose-300 bg-rose-50/50 dark:border-rose-500/40 dark:bg-rose-500/5'
                : 'border-slate-300 bg-slate-50/50 hover:border-cobalt-400 hover:bg-cobalt-50/40 dark:border-slate-700 dark:bg-slate-900/40 dark:hover:border-cobalt-500/60 dark:hover:bg-cobalt-500/5',
            disabled && 'pointer-events-none opacity-60',
          )}
        >
          <div
            className={cn(
              'flex size-14 items-center justify-center rounded-lg bg-white text-cobalt-600 shadow-sm ring-1 ring-slate-200 transition-transform duration-200 group-hover:-translate-y-0.5 dark:bg-slate-900 dark:text-cobalt-400 dark:ring-slate-700',
              dragging && '-translate-y-1',
            )}
          >
            <CloudUpload className="size-7" aria-hidden />
          </div>
          <p className="mt-4 text-sm font-medium">
            {dragging ? 'Suelta el archivo aquí' : 'Arrastra tu CV aquí'}
          </p>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            o <span className="font-medium text-cobalt-600 dark:text-cobalt-400">haz clic para seleccionarlo</span>
          </p>
          <p id={hintId} className="mt-3 text-xs text-slate-400">
            PDF de hasta {MAX_PDF_MB} MB y 5 páginas
          </p>
        </div>
      )}

      {error && (
        <p role="alert" className="mt-3 flex items-center gap-1.5 text-sm text-rose-700 dark:text-rose-400">
          <TriangleAlert className="size-4 shrink-0" aria-hidden /> {error}
        </p>
      )}
    </SectionCard>
  )
}

const MEMORY_TEXT: Record<Exclude<CvMemoryStatus, 'off'>, string> = {
  saved: 'Guardado en este navegador',
  restored: 'Recuperado de este navegador',
  error: 'Este navegador no permite guardarlo (¿modo privado?)',
}

function MemoryStatus({ status }: { status: CvMemoryStatus }) {
  if (status === 'off') return null
  return (
    <p
      role="status"
      className={cn(
        'mt-1.5 flex items-center gap-1.5 text-xs',
        status === 'error' ? 'text-amber-700 dark:text-amber-400' : 'text-slate-600 dark:text-slate-400',
      )}
    >
      <HardDrive className="size-3.5" aria-hidden />
      {MEMORY_TEXT[status]}
    </p>
  )
}
