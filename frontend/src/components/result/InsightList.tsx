import type { LucideIcon } from 'lucide-react'

import { cn } from '../../lib/format'

interface InsightListProps {
  title: string
  description?: string
  items: string[]
  icon: LucideIcon
  tone: 'amber' | 'indigo'
}

const TONES = {
  amber: 'bg-amber-50 text-amber-600 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20',
  indigo: 'bg-indigo-50 text-indigo-600 ring-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-400 dark:ring-indigo-500/20',
}

export function InsightList({ title, description, items, icon: Icon, tone }: InsightListProps) {
  if (items.length === 0) return null

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2.5">
        <span className={cn('flex size-7 items-center justify-center rounded-md ring-1', TONES[tone])}>
          <Icon className="size-4" aria-hidden />
        </span>
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      {description && <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">{description}</p>}
      <ul className="mt-3 space-y-2">
        {items.map((item) => (
          <li key={item} className="flex gap-2 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
            <span
              className={cn('mt-2 size-1.5 shrink-0 rounded-full', tone === 'amber' ? 'bg-amber-400' : 'bg-indigo-400')}
              aria-hidden
            />
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}
