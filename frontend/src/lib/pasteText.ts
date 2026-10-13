// Utilidades puras del "textarea inteligente" de la oferta (pegar texto, enlaces o capturas).

/** Límite del texto pegado: protege el límite de tokens por minuto (TPM) de Groq. */
export const PASTE_MAX_CHARS = 10_000

const SINGLE_URL = /^https?:\/\/[^\s<>"']+$/i

/** ¿El portapapeles contiene solo un enlace (y no un texto que incluye enlaces)? */
export function isSingleUrl(text: string): boolean {
  const trimmed = text.trim()
  if (!SINGLE_URL.test(trimmed)) return false
  try {
    return Boolean(new URL(trimmed).hostname)
  } catch {
    return false
  }
}

/** Limpia texto copiado de una web con Ctrl+A: espacios repetidos, líneas en blanco múltiples,
 *  tabulaciones y espacios de ancho cero. El ruido de menús y pies lo ignora el LLM (prompt v4). */
export function cleanPastedText(text: string): string {
  return text
    .replace(/\r\n?/g, '\n')
    .replace(/[​-‍﻿]/g, '')
    .split('\n')
    .map((line) => line.replace(/[ \t ]+/g, ' ').trim())
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export interface InsertResult {
  value: string
  /** Posición del cursor tras el texto insertado. */
  caret: number
  truncated: boolean
}

/** Inserta `text` en la selección actual sin que el total supere `max` caracteres. */
export function insertText(value: string, start: number, end: number, text: string, max = PASTE_MAX_CHARS): InsertResult {
  const before = value.slice(0, start)
  const after = value.slice(end)
  const room = Math.max(0, max - before.length - after.length)
  const inserted = text.slice(0, room)
  return { value: before + inserted + after, caret: before.length + inserted.length, truncated: inserted.length < text.length }
}

/** Añade un bloque al final (texto de una URL o de una captura), separado por una línea en blanco. */
export function appendBlock(value: string, block: string, max = PASTE_MAX_CHARS): InsertResult {
  const base = value.trimEnd()
  const separator = base ? '\n\n' : ''
  // Sin sitio ni para el separador: no se toca el texto (nunca se supera el máximo).
  if (base.length + separator.length >= max) return { value, caret: value.length, truncated: block.length > 0 }
  return insertText(base + separator, base.length + separator.length, base.length + separator.length, block, max)
}
