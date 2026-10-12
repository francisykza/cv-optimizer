import { useEffect, useState } from 'react'

import { checkHealth } from '../services/api'

export type ServerState = 'checking' | 'waking' | 'online' | 'offline'

const WAKING_THRESHOLD_MS = 3000
const ATTEMPT_TIMEOUT_MS = 15_000
const RETRY_INTERVAL_MS = 5000
// Render (plan gratuito) tarda ~1 min en despertar; damos margen antes de declararlo caído.
const WAKE_UP_BUDGET_MS = 120_000
const OFFLINE_RETRY_INTERVAL_MS = 30_000

/** Hace ping a /health al cargar para despertar Render mientras el usuario rellena el formulario.
 *
 *  Mientras Render arranca un servicio dormido responde con su propia página de carga, sin
 *  cabeceras CORS, y el navegador lo ve como un error de red. Por eso un fallo no significa
 *  "caído": se reintenta mostrando "despertando" y solo tras WAKE_UP_BUDGET_MS se pasa a
 *  "offline", donde se sigue comprobando cada cierto tiempo para recuperarse solo. */
export function useServerStatus() {
  const [state, setState] = useState<ServerState>('checking')
  const [serverKeyAvailable, setServerKeyAvailable] = useState<boolean | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const start = Date.now()
    let timer: number | undefined
    const wakingTimer = window.setTimeout(
      () => setState((s) => (s === 'checking' ? 'waking' : s)),
      WAKING_THRESHOLD_MS,
    )

    const attempt = async () => {
      try {
        const health = await checkHealth(controller.signal, ATTEMPT_TIMEOUT_MS)
        window.clearTimeout(wakingTimer)
        setServerKeyAvailable(health.server_llm_available)
        setState('online')
      } catch {
        if (controller.signal.aborted) return
        const withinBudget = Date.now() - start < WAKE_UP_BUDGET_MS
        setState(withinBudget ? 'waking' : 'offline')
        timer = window.setTimeout(attempt, withinBudget ? RETRY_INTERVAL_MS : OFFLINE_RETRY_INTERVAL_MS)
      }
    }
    void attempt()

    return () => {
      controller.abort()
      window.clearTimeout(wakingTimer)
      window.clearTimeout(timer)
    }
  }, [])

  return { state, serverKeyAvailable }
}
