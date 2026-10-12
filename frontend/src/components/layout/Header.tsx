import type { ServerState } from '../../hooks/useServerStatus'
import { cn } from '../../lib/format'
import { Logo } from '../ui/Logo'

const STATUS: Record<ServerState, { label: string; dot: string; text: string }> = {
  checking: { label: 'Conectando…', dot: 'bg-slate-400 animate-pulse', text: 'text-slate-500' },
  waking: { label: 'Despertando servidor…', dot: 'bg-amber-500 animate-pulse', text: 'text-amber-700 dark:text-amber-400' },
  online: { label: 'Servidor operativo', dot: 'bg-emerald-500', text: 'text-emerald-700 dark:text-emerald-400' },
  offline: { label: 'Servidor no disponible', dot: 'bg-rose-500', text: 'text-rose-700 dark:text-rose-400' },
}

const REPO_URL = import.meta.env.VITE_REPO_URL as string | undefined

export function Header({ serverState }: { serverState: ServerState }) {
  const status = STATUS[serverState]

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-white/75 backdrop-blur-lg dark:border-slate-800/70 dark:bg-slate-950/75">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <a href="#" className="focus-ring flex items-center gap-2.5 rounded-lg" aria-label="CV-Optimizer, inicio">
          <Logo className="size-8" />
          <span className="text-[15px] font-semibold tracking-tight">
            CV<span className="text-indigo-600 dark:text-indigo-400">-Optimizer</span>
          </span>
        </a>

        <div className="flex items-center gap-3">
          <div
            className={cn(
              'flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium dark:border-slate-800 dark:bg-slate-900',
              status.text,
            )}
            role="status"
            aria-live="polite"
          >
            <span className={cn('size-2 rounded-full', status.dot)} aria-hidden />
            <span className="hidden sm:inline">{status.label}</span>
          </div>

          {REPO_URL && (
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="focus-ring flex size-9 items-center justify-center rounded-lg text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
              aria-label="Código fuente en GitHub"
            >
              <svg viewBox="0 0 24 24" className="size-5" fill="currentColor" aria-hidden>
                <path d="M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.37-3.88-1.37-.52-1.33-1.28-1.69-1.28-1.69-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.19 1.76 1.19 1.03 1.76 2.69 1.25 3.35.96.1-.75.4-1.25.73-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.83 1.19 3.09 0 4.42-2.7 5.39-5.26 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5Z" />
              </svg>
            </a>
          )}
        </div>
      </div>
    </header>
  )
}
