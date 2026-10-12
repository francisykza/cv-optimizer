import { useCallback, useState } from 'react'

// sessionStorage (se borra al cerrar la pestaña) y solo si el usuario lo pide.
// Nunca localStorage: la clave no debe sobrevivir a la sesión.
const STORAGE_KEY = 'cv-optimizer:byok-key'

function readStored(): string {
  try {
    return sessionStorage.getItem(STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

function writeStored(value: string | null): void {
  try {
    if (value) sessionStorage.setItem(STORAGE_KEY, value)
    else sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    /* almacenamiento no disponible (modo privado, etc.): se trabaja solo en memoria */
  }
}

export function useByokKey() {
  const [apiKey, setApiKeyState] = useState<string>(readStored)
  const [remember, setRememberState] = useState<boolean>(() => readStored() !== '')

  const setApiKey = useCallback(
    (value: string) => {
      setApiKeyState(value)
      if (remember) writeStored(value.trim() || null)
    },
    [remember],
  )

  const setRemember = useCallback(
    (value: boolean) => {
      setRememberState(value)
      writeStored(value ? apiKey.trim() || null : null)
    },
    [apiKey],
  )

  const clear = useCallback(() => {
    setApiKeyState('')
    writeStored(null)
  }, [])

  return { apiKey, setApiKey, remember, setRemember, clear }
}
