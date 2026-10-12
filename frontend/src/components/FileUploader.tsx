import { CheckCircle2, CloudUpload, FileText, TriangleAlert, X } from 'lucide-react'
import { useId, useRef, useState, type DragEvent, type KeyboardEvent } from 'react'

import { MAX_PDF_BYTES, MAX_PDF_MB } from '../lib/constants'
import { cn, formatBytes } from '../lib/format'
import { SectionCard } from './ui/SectionCard'

interface FileUploaderProps {
  file: File | null
  onFileChange: (file: File | null) => void
  disabled?: boolean
}

export function validatePdf(file: File): string | null {
  const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
  if (!isPdf) return 'Solo se admiten archivos PDF.'
  if (file.size > MAX_PDF_BYTES) return `El archivo pesa ${formatBytes(file.size)}; el máximo es ${MAX_PDF_MB} MB.`
  if (file.size === 0) return 'El archivo está vacío.'
  return null
}

export function FileUploader({ file, onFileChange, disabled }: FileUploaderProps) {
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
        <div className="relative flex flex-1 animate-fade-in-up flex-col items-center justify-center rounded-xl border border-emerald-200 bg-emerald-50/50 px-6 py-10 text-center dark:border-emerald-500/20 dark:bg-emerald-500/5">
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
            <div className="flex size-14 items-center justify-center rounded-2xl bg-white text-rose-600 shadow-sm ring-1 ring-slate-200 dark:bg-slate-900 dark:text-rose-400 dark:ring-slate-700">
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
            {formatBytes(file.size)} · Listo para optimizar
          </p>
          <button
            type="button"
            onClick={openPicker}
            disabled={disabled}
            className="focus-ring mt-4 rounded-md text-sm font-medium text-indigo-600 underline-offset-4 hover:underline disabled:opacity-50 dark:text-indigo-400"
          >
            Cambiar archivo
          </button>
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
            'focus-ring group flex flex-1 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-all duration-200',
            dragging
              ? 'scale-[1.01] border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10'
              : error
                ? 'border-rose-300 bg-rose-50/50 dark:border-rose-500/40 dark:bg-rose-500/5'
                : 'border-slate-300 bg-slate-50/50 hover:border-indigo-400 hover:bg-indigo-50/40 dark:border-slate-700 dark:bg-slate-900/40 dark:hover:border-indigo-500/60 dark:hover:bg-indigo-500/5',
            disabled && 'pointer-events-none opacity-60',
          )}
        >
          <div
            className={cn(
              'flex size-14 items-center justify-center rounded-2xl bg-white text-indigo-600 shadow-sm ring-1 ring-slate-200 transition-transform duration-200 group-hover:-translate-y-0.5 dark:bg-slate-900 dark:text-indigo-400 dark:ring-slate-700',
              dragging && '-translate-y-1',
            )}
          >
            <CloudUpload className="size-7" aria-hidden />
          </div>
          <p className="mt-4 text-sm font-medium">
            {dragging ? 'Suelta el archivo aquí' : 'Arrastra tu CV aquí'}
          </p>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            o <span className="font-medium text-indigo-600 dark:text-indigo-400">haz clic para seleccionarlo</span>
          </p>
          <p id={hintId} className="mt-3 text-xs text-slate-400">
            PDF · máximo {MAX_PDF_MB} MB · hasta 5 páginas
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
