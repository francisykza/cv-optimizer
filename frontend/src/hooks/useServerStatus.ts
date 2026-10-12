import { useEffect, useState } from 'react'

import { checkHealth } from '../services/api'

export type ServerState = 'checking' | 'waking' | 'online' | 'offline'

const WAKING_THRESHOLD_MS = 3000

/** Hace ping a /health al cargar. En el plan gratuito de Render el primer arranque tarda
 *  30-60 s: así el servidor se despierta mientras el usuario rellena el formulario. */
export function useServerStatus() {
  const [state, setState] = useState<ServerState>('checking')
  const [serverKeyAvailable, setServerKeyAvailable] = useState<boolean | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const wakingTimer = window.setTimeout(() => setState('waking'), WAKING_THRESHOLD_MS)

    checkHealth(controller.signal)
      .then((health) => {
        setServerKeyAvailable(health.server_llm_available)
        setState('online')
      })
      .catch(() => {
        if (!controller.signal.aborted) setState('offline')
      })
      .finally(() => window.clearTimeout(wakingTimer))

    return () => {
      controller.abort()
      window.clearTimeout(wakingTimer)
    }
  }, [])

  return { state, serverKeyAvailable }
}
