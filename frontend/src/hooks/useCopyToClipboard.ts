import { useCallback, useEffect, useRef, useState } from 'react'

async function writeText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // Sin Clipboard API (HTTP no seguro) o con el permiso denegado (iframes, navegadores
    // embebidos): se recurre al método clásico con un textarea temporal.
    legacyCopy(text)
  }
}

function legacyCopy(text: string): void {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  const ok = document.execCommand('copy')
  document.body.removeChild(textarea)
  if (!ok) throw new Error('copy failed')
}

export function useCopyToClipboard(resetAfterMs = 2000) {
  const [state, setState] = useState<'idle' | 'copied' | 'error'>('idle')
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const copy = useCallback(
    async (text: string) => {
      try {
        await writeText(text)
        setState('copied')
      } catch {
        setState('error')
      }
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => setState('idle'), resetAfterMs)
    },
    [resetAfterMs],
  )

  return { copy, state }
}
