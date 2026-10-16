import { useEffect, useState } from 'react'

import { flushOutbox } from './applications'
import { hunterApi, tokenStore } from './hunterClient'

export type LocalApiState = 'unknown' | 'online' | 'offline'

// La API que arranca el acceso directo se apaga sola tras 30 min sin peticiones: con la web abierta,
// este latido la mantiene encendida, y cuando se cierra la pestaña se apaga sola un rato después.
export const KEEPALIVE_MS = 2 * 60 * 1000

/**
 * Estado de la API local del Buscador mientras la web está abierta (solo con el Buscador activado).
 * Cada respuesta envía también las candidaturas que esperaban en la cola del navegador.
 */
export function useLocalApi(enabled: boolean, onFlushed?: (saved: number) => void): LocalApiState {
  const [state, setState] = useState<LocalApiState>('unknown')

  useEffect(() => {
    if (!enabled) return
    let timer: number | undefined
    let cancelled = false
    const ping = async () => {
      window.clearTimeout(timer)
      try {
        await hunterApi.health()
        if (cancelled) return
        setState('online')
        const token = tokenStore.get()
        if (token) {
          const saved = await flushOutbox(token)
          if (saved && !cancelled) onFlushed?.(saved)
        }
      } catch {
        if (!cancelled) setState('offline')
      }
      if (!cancelled) timer = window.setTimeout(ping, KEEPALIVE_MS)
    }
    void ping()
    // Al volver a la pestaña se comprueba enseguida (el acceso directo puede haberla arrancado).
    const onFocus = () => void ping()
    window.addEventListener('focus', onFocus)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      window.removeEventListener('focus', onFocus)
    }
    // onFlushed solo avisa: no debe reiniciar el latido.
  }, [enabled])

  return state
}
