import { KeyRound, LoaderCircle, PlugZap } from 'lucide-react'
import { useId, useState } from 'react'

import { HUNTER_URL } from './hunterClient'

export type GateState = 'checking' | 'offline' | 'needs-token' | 'no-token-configured'

interface ConnectionGateProps {
  state: GateState
  tokenError?: string | null
  onRetry: () => void
  onToken: (token: string, remember: boolean) => void
}

function Command({ children }: { children: string }) {
  return (
    <code className="block overflow-x-auto rounded-md bg-ink px-3 py-2 font-mono text-[13px] text-slate-100">
      {children}
    </code>
  )
}

/** Lo que se ve mientras la vista no puede hablar con la API local: cómo arrancarla o el token. */
export function ConnectionGate({ state, tokenError, onRetry, onToken }: ConnectionGateProps) {
  const inputId = useId()
  const [token, setToken] = useState('')
  const [remember, setRemember] = useState(true)

  if (state === 'checking') {
    return (
      <p className="card flex items-center gap-2 p-5 text-sm text-slate-600 dark:text-slate-300" role="status">
        <LoaderCircle className="size-4 animate-spin" aria-hidden />
        Conectando con la API local…
      </p>
    )
  }

  if (state === 'offline' || state === 'no-token-configured') {
    return (
      <section className="card max-w-2xl space-y-4 p-5 sm:p-6" aria-labelledby={`${inputId}-t`}>
        <h2 id={`${inputId}-t`} className="flex items-center gap-2 text-base font-semibold">
          <PlugZap className="size-5 text-cobalt-600" aria-hidden />
          {state === 'offline' ? 'La API local no está arrancada' : 'La API local no tiene token'}
        </h2>
        <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">
          El Buscador lee las ofertas de tu equipo, no de internet. Abre una terminal en la carpeta{' '}
          <code className="font-mono">hunter</code> y ejecuta:
        </p>
        {state === 'no-token-configured' && <Command>.venv\Scripts\python -m hunter init</Command>}
        <Command>.venv\Scripts\python -m hunter serve</Command>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Debe quedar escuchando en <code className="font-mono">{HUNTER_URL}</code>. Si usas la web publicada, Chrome te
          pedirá permiso para acceder a la red local: acéptalo.
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="focus-ring h-9 rounded-md bg-cobalt-600 px-4 text-sm font-semibold text-white transition hover:bg-cobalt-700"
        >
          Volver a comprobar
        </button>
      </section>
    )
  }

  return (
    <form
      className="card max-w-xl space-y-4 p-5 sm:p-6"
      onSubmit={(e) => {
        e.preventDefault()
        if (token.trim()) onToken(token.trim(), remember)
      }}
    >
      <h2 className="flex items-center gap-2 text-base font-semibold">
        <KeyRound className="size-5 text-cobalt-600" aria-hidden />
        Conecta con tu API local
      </h2>
      <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">
        Pega el valor de <code className="font-mono">HUNTER_TOKEN</code> de tu archivo{' '}
        <code className="font-mono">hunter/.env</code>. Solo se usa para hablar con tu propio equipo.
      </p>
      <div>
        <label htmlFor={inputId} className="text-sm font-medium">
          Token local
        </label>
        <input
          id={inputId}
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={token}
          onChange={(e) => setToken(e.target.value)}
          aria-invalid={Boolean(tokenError)}
          aria-describedby={tokenError ? `${inputId}-err` : undefined}
          className="focus-ring mt-1 h-10 w-full rounded-md border border-slate-300 bg-paper px-3 font-mono text-sm dark:border-slate-700 dark:bg-slate-950"
        />
        {tokenError && (
          <p id={`${inputId}-err`} className="mt-1.5 text-sm text-rose-700 dark:text-rose-400" role="alert">
            {tokenError}
          </p>
        )}
      </div>
      <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
        <input
          type="checkbox"
          checked={remember}
          onChange={(e) => setRemember(e.target.checked)}
          className="size-4 accent-cobalt-600"
        />
        Recordarlo en este navegador
      </label>
      <button
        type="submit"
        disabled={!token.trim()}
        className="focus-ring h-9 rounded-md bg-cobalt-600 px-4 text-sm font-semibold text-white transition hover:bg-cobalt-700 disabled:opacity-50"
      >
        Conectar
      </button>
    </form>
  )
}
