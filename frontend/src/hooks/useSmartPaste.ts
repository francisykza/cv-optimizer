import { type ClipboardEvent, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

import { appendBlock, cleanPastedText, insertText, isSingleUrl, PASTE_MAX_CHARS } from '../lib/pasteText'
import { ApiError, extractJobUrl } from '../services/api'

export type SmartPasteState =
  | { kind: 'idle' }
  | { kind: 'url' }
  | { kind: 'ocr'; phase: 'loading' | 'recognizing'; progress: number }

export interface SmartPasteNotice {
  tone: 'info' | 'warning'
  text: string
}

const TRUNCATED_NOTICE = `Hemos recortado la oferta a ${PASTE_MAX_CHARS.toLocaleString('es-ES')} caracteres. Revisa que no falten los requisitos.`
const OCR_FAILED = 'No hemos podido leer texto en la captura. Prueba con una imagen más nítida o copia el texto.'

/**
 * "Textarea inteligente": intercepta el pegado según lo que haya en el portapapeles.
 * - Un único enlace: el backend lee la oferta (Jina Reader).
 * - Una imagen sin texto: OCR en el navegador; el texto se añade al final (varias capturas).
 * - Texto (p. ej. Ctrl+A en la web de la oferta): se limpia y se limita a PASTE_MAX_CHARS.
 */
export function useSmartPaste(value: string, onChange: (value: string) => void) {
  const [state, setState] = useState<SmartPasteState>({ kind: 'idle' })
  const [notice, setNotice] = useState<SmartPasteNotice | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  // El valor puede cambiar mientras se lee una URL o una captura: se añade sobre el más reciente.
  const valueRef = useRef(value)
  useLayoutEffect(() => {
    valueRef.current = value
  })

  useEffect(() => () => controllerRef.current?.abort(), [])

  const appendResult = useCallback(
    (text: string) => {
      const result = appendBlock(valueRef.current, cleanPastedText(text))
      onChange(result.value)
      setNotice(result.truncated ? { tone: 'info', text: TRUNCATED_NOTICE } : null)
    },
    [onChange],
  )

  const readUrl = useCallback(
    async (url: string) => {
      const controller = new AbortController()
      controllerRef.current = controller
      setState({ kind: 'url' })
      try {
        appendResult(await extractJobUrl(url, controller.signal))
      } catch (err) {
        if (controller.signal.aborted) return
        const message = err instanceof ApiError ? err.message : 'No se ha podido leer el enlace.'
        setNotice({ tone: 'warning', text: message })
      } finally {
        if (!controller.signal.aborted) setState({ kind: 'idle' })
      }
    },
    [appendResult],
  )

  const readImage = useCallback(
    async (image: Blob) => {
      setState({ kind: 'ocr', phase: 'loading', progress: 0 })
      try {
        const { recognizeImage } = await import('../lib/ocr')
        const text = await recognizeImage(image, ({ phase, progress }) => setState({ kind: 'ocr', phase, progress }))
        if (cleanPastedText(text).length === 0) setNotice({ tone: 'warning', text: OCR_FAILED })
        else appendResult(text)
      } catch {
        setNotice({ tone: 'warning', text: OCR_FAILED })
      } finally {
        setState({ kind: 'idle' })
      }
    },
    [appendResult],
  )

  const onPaste = useCallback(
    (event: ClipboardEvent<HTMLTextAreaElement>) => {
      if (state.kind !== 'idle') {
        event.preventDefault()
        return
      }
      const data = event.clipboardData
      const text = data.getData('text/plain')

      // Word o Excel copian también una imagen junto al texto: si hay texto, manda el texto.
      if (!text.trim()) {
        const image = [...data.items].find((item) => item.kind === 'file' && item.type.startsWith('image/'))
        const file = image?.getAsFile()
        if (file) {
          event.preventDefault()
          setNotice(null)
          void readImage(file)
        }
        return
      }

      if (isSingleUrl(text)) {
        event.preventDefault()
        setNotice(null)
        void readUrl(text.trim())
        return
      }

      const textarea = event.currentTarget
      const cleaned = cleanPastedText(text)
      const result = insertText(value, textarea.selectionStart, textarea.selectionEnd, cleaned)
      // Pegado normal: se deja actuar al navegador (conserva el deshacer nativo).
      if (cleaned === text && !result.truncated) return

      event.preventDefault()
      onChange(result.value)
      setNotice(result.truncated ? { tone: 'info', text: TRUNCATED_NOTICE } : null)
      requestAnimationFrame(() => textarea.setSelectionRange(result.caret, result.caret))
    },
    [state.kind, value, onChange, readImage, readUrl],
  )

  return { onPaste, state, busy: state.kind !== 'idle', notice, dismissNotice: () => setNotice(null) }
}
