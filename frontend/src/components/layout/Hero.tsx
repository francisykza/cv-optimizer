import { LockKeyhole } from 'lucide-react'

import { HeroDemo } from './HeroDemo'

export function Hero() {
  return (
    <section className="mx-auto grid max-w-6xl overflow-x-clip gap-12 px-4 pt-12 pb-14 sm:px-6 sm:pt-16 lg:grid-cols-[1.1fr_1fr] lg:items-center lg:gap-16 lg:pt-20 lg:pb-20">
      <div>
        <h1 className="max-w-[15ch] text-4xl leading-[1.08] font-semibold tracking-tight text-balance sm:text-5xl lg:text-[3.5rem]">
          Adapta tu CV a cada oferta sin inventar nada.
        </h1>
        <p className="mt-6 max-w-[52ch] text-lg leading-relaxed text-pretty text-slate-600 dark:text-slate-300">
          Sube tu currículum en PDF y pega la oferta. Lo reescribimos con las palabras clave que buscan los filtros ATS,
          usando solo lo que ya aparece en tu CV, y te decimos qué te falta.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-4">
          <a
            href="#optimizar"
            className="focus-ring inline-flex h-12 items-center rounded-md bg-cobalt-600 px-6 text-base font-semibold text-white transition-colors hover:bg-cobalt-700 dark:bg-cobalt-500 dark:hover:bg-cobalt-400"
          >
            Empezar con mi CV
          </a>
          <p className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <LockKeyhole className="size-4 shrink-0" aria-hidden />
            Tu PDF se procesa en memoria y no se guarda en ningún servidor.
          </p>
        </div>
      </div>

      {/* Demo: un CV que se corrige solo con los tres rotuladores de la app. */}
      <HeroDemo />
    </section>
  )
}
