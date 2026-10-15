import { Check, Copy } from 'lucide-react'

import { useCopyToClipboard } from '../../hooks/useCopyToClipboard'
import { cn } from '../../lib/format'

export function CopyButton({
  text,
  className,
  label = 'Copiar al portapapeles',
}: {
  text: string
  className?: string
  label?: string
}) {
  const { copy, state } = useCopyToClipboard()
  const copied = state === 'copied'

  return (
    <button
      type="button"
      onClick={() => copy(text)}
      className={cn(
        'focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold shadow-sm transition-all duration-200',
        copied
          ? 'bg-emerald-600 text-white shadow-emerald-600/20'
          : 'bg-slate-900 text-white hover:bg-slate-700 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200',
        className,
      )}
    >
      <span className="relative size-4">
        <Copy
          className={cn('absolute inset-0 size-4 transition-all duration-200', copied ? 'scale-50 opacity-0' : 'scale-100 opacity-100')}
          aria-hidden
        />
        <Check
          className={cn('absolute inset-0 size-4 transition-all duration-200', copied ? 'scale-100 opacity-100' : 'scale-50 opacity-0')}
          aria-hidden
        />
      </span>
      <span aria-live="polite">
        {copied ? '¡Copiado!' : state === 'error' ? 'No se pudo copiar' : label}
      </span>
    </button>
  )
}
