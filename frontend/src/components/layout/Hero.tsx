import { LockKeyhole, ShieldCheck, Sparkles, Target } from 'lucide-react'

const FEATURES = [
  {
    icon: ShieldCheck,
    title: 'Sin inventar nada',
    text: 'Solo reformula lo que ya está en tu CV. Lo que te falta se marca como "gap", nunca se añade.',
  },
  {
    icon: Target,
    title: 'Pensado para ATS',
    text: 'Usa la terminología de la oferta y un formato limpio, de una columna, que los ATS leen sin problemas.',
  },
  {
    icon: LockKeyhole,
    title: 'Privado por diseño',
    text: 'Tu PDF se procesa en memoria y no se guarda en ningún servidor ni base de datos.',
  },
]

export function Hero() {
  return (
    <section className="relative isolate overflow-hidden [contain:paint]">
      {/* Fondo: rejilla sutil + halo de color. Ambos son estáticos y van en su propia capa
          (transform-gpu) para que el scroll no los repinte. El halo usa un radial-gradient en
          lugar de filter: blur(), que era muy costoso sobre un elemento de 56rem. */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 transform-gpu bg-[linear-gradient(to_right,rgb(148_163_184/0.12)_1px,transparent_1px),linear-gradient(to_bottom,rgb(148_163_184/0.12)_1px,transparent_1px)] bg-[size:44px_44px] [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,#000_60%,transparent_100%)]"
      />
      <div
        aria-hidden
        className="hero-glow absolute left-1/2 top-[-16rem] -z-10 h-[36rem] w-[64rem] -translate-x-1/2 transform-gpu"
      />

      <div className="mx-auto max-w-6xl px-4 pb-12 pt-14 text-center sm:px-6 sm:pt-20">
        <span className="inline-flex animate-fade-in-up items-center gap-2 rounded-full border border-indigo-200 bg-white/80 px-3.5 py-1 text-xs font-medium text-indigo-700 shadow-sm dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-300">
          <Sparkles className="size-3.5" aria-hidden />
          Optimización de CV con IA · Open source
        </span>

        <h1 className="mx-auto mt-6 max-w-3xl animate-fade-in-up text-4xl font-bold tracking-tight text-balance [animation-delay:60ms] sm:text-5xl lg:text-6xl">
          Adapta tu CV a cada oferta.{' '}
          <span className="bg-gradient-to-r from-indigo-600 via-violet-600 to-fuchsia-500 bg-clip-text text-transparent dark:from-indigo-400 dark:via-violet-400 dark:to-fuchsia-400">
            Sin inventar nada.
          </span>
        </h1>

        <p className="mx-auto mt-5 max-w-2xl animate-fade-in-up text-base text-pretty text-slate-600 [animation-delay:120ms] sm:text-lg dark:text-slate-400">
          Sube tu currículum, pega la oferta y obtén una versión reescrita con las palabras clave que buscan
          los filtros ATS, junto a un informe de compatibilidad y de lo que te falta.
        </p>

        <ul className="mx-auto mt-10 grid max-w-4xl animate-fade-in-up gap-4 text-left [animation-delay:180ms] sm:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <li key={title} className="card p-5">
              <div className="flex size-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 ring-1 ring-indigo-100 dark:bg-indigo-500/10 dark:text-indigo-400 dark:ring-indigo-500/20">
                <Icon className="size-5" aria-hidden />
              </div>
              <h2 className="mt-3 text-sm font-semibold">{title}</h2>
              <p className="mt-1 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{text}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
