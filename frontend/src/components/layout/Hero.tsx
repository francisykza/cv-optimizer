import { LockKeyhole } from 'lucide-react'

import { cn } from '../../lib/format'

/** Trazo de rotulador que se dibuja al cargar la página (única animación automática de la web). */
function Marker({ color, delay, children }: { color: 'green' | 'amber' | 'blue'; delay: string; children: string }) {
  return (
    <span className={cn('marker animate-marker', `marker-${color}`)} style={{ animationDelay: delay }}>
      {children}
    </span>
  )
}

const LEGEND = [
  { color: 'bg-marker-green', text: 'Reformulado a partir de lo que ya pone tu CV' },
  { color: 'bg-marker-amber', text: 'No aparece en tu CV: te avisamos para que lo revises' },
  { color: 'bg-marker-blue', text: 'Añadido por ti, solo si lo dominas' },
]

export function Hero() {
  return (
    <section className="mx-auto grid max-w-6xl gap-12 px-4 pt-12 pb-14 sm:px-6 sm:pt-16 lg:grid-cols-[1.1fr_1fr] lg:items-center lg:gap-16 lg:pt-20 lg:pb-20">
      <div>
        <h1 className="max-w-[15ch] text-4xl leading-[1.08] font-semibold tracking-tight text-balance sm:text-5xl lg:text-[3.5rem]">
          Adapta tu CV a cada oferta sin inventar nada.
        </h1>
        <p className="mt-6 max-w-[52ch] text-lg leading-relaxed text-pretty text-slate-600 dark:text-slate-300">
          Sube tu currículum en PDF y pega la oferta. Lo reescribimos con las palabras clave que buscan los filtros
          ATS, usando solo lo que ya aparece en tu CV, y te decimos qué te falta.
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
            Tu PDF se procesa en memoria y no se guarda.
          </p>
        </div>
      </div>

      {/* Demo: un fragmento de CV corregido con los tres rotuladores de la app. */}
      <figure aria-label="Ejemplo de CV optimizado" className="mx-auto w-full max-w-md lg:max-w-none">
        <div className="sheet px-7 py-8 font-serif text-[15px] leading-relaxed sm:px-10 sm:py-10 lg:rotate-[0.6deg]">
          <p className="text-xl font-semibold">Laura Pérez Gil</p>
          <p className="text-slate-600 dark:text-slate-400">Auxiliar administrativa en Sevilla</p>

          <p className="mt-6 border-b border-slate-200 pb-1 font-semibold dark:border-slate-700">Resumen profesional</p>
          <p className="mt-2">
            Auxiliar administrativa con experiencia en contabilidad y gestión laboral,{' '}
            <Marker color="amber" delay="1.5s">
              orientada a resultados
            </Marker>
            .
          </p>
          <p className="mt-1 font-sans text-xs text-amber-800 italic dark:text-amber-300">
            Revisa esto: no aparece en tu CV original.
          </p>

          <p className="mt-6 border-b border-slate-200 pb-1 font-semibold dark:border-slate-700">Experiencia</p>
          <p className="mt-2">
            <Marker color="green" delay="0.5s">
              Gestión de la facturación y la contabilidad
            </Marker>{' '}
            de clientes con Contanet.
          </p>

          <p className="mt-6 border-b border-slate-200 pb-1 font-semibold dark:border-slate-700">Habilidades</p>
          <p className="mt-2">
            Contanet, Excel, paquete Office,{' '}
            <Marker color="blue" delay="1s">
              carnet de conducir
            </Marker>
          </p>
        </div>

        <figcaption>
          <ul className="mt-6 space-y-2 text-sm text-slate-600 dark:text-slate-400">
            {LEGEND.map(({ color, text }) => (
              <li key={text} className="flex items-center gap-3">
                <span className={cn('h-3 w-6 shrink-0 rounded-[2px]', color, 'dark:opacity-60')} aria-hidden />
                {text}
              </li>
            ))}
          </ul>
        </figcaption>
      </figure>
    </section>
  )
}
