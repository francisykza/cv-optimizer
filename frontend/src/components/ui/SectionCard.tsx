import type { ReactNode } from 'react'

import { cn } from '../../lib/format'

interface SectionCardProps {
  step?: number
  title: string
  description?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}

/** Tarjeta con encabezado numerado para cada paso del formulario. */
export function SectionCard({ step, title, description, action, children, className }: SectionCardProps) {
  return (
    <section className={cn('card flex flex-col p-5 sm:p-6', className)}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          {step !== undefined && (
            <span
              className="flex size-7 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-semibold text-white dark:bg-white dark:text-slate-900"
              aria-hidden
            >
              {step}
            </span>
          )}
          <div>
            <h2 className="text-base font-semibold tracking-tight">{title}</h2>
            {description && <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">{description}</p>}
          </div>
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}
