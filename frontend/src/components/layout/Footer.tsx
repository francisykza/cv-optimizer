import { LockKeyhole } from 'lucide-react'

export function Footer() {
  return (
    <footer className="border-t border-slate-200/70 dark:border-slate-800/70">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-4 py-8 text-sm text-slate-500 sm:flex-row sm:px-6 dark:text-slate-400">
        <p className="flex items-center gap-2">
          <LockKeyhole className="size-4" aria-hidden />
          Tu CV se procesa en memoria y nunca se almacena.
        </p>
        <p>React · Tailwind CSS · FastAPI · Groq</p>
      </div>
    </footer>
  )
}
