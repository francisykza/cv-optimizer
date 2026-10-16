import { JOB_OFFER_MAX_CHARS, JOB_OFFER_MIN_CHARS } from './constants'

/**
 * Puente Buscador → Optimizador (SPEC del hunter §10.3). La oferta viaja por sessionStorage y no
 * por la URL: puede tener hasta 15 000 caracteres. Se consume una sola vez y caduca a los 10 min.
 */
export interface OfferHandoff {
  version: 1
  text: string
  title: string
  company: string
  sourceUrl?: string
  language?: 'es' | 'en'
  createdAt: number
  // Desde la SPEC 0.4.0 (opcionales, compatibles con la versión 1): para volver a la oferta y para
  // apuntar la candidatura enlazada a su ficha del Buscador.
  location?: string
  jobId?: string
  matchScore?: number
}

export const HANDOFF_KEY = 'cvopt:handoff'
export const HANDOFF_MAX_AGE_MS = 10 * 60 * 1000

export function writeHandoff(handoff: Omit<OfferHandoff, 'version' | 'createdAt'>): boolean {
  const value: OfferHandoff = { ...handoff, version: 1, createdAt: Date.now() }
  try {
    sessionStorage.setItem(HANDOFF_KEY, JSON.stringify(value))
    return true
  } catch {
    return false
  }
}

function isHandoff(value: unknown, now: number): value is OfferHandoff {
  if (!value || typeof value !== 'object') return false
  const h = value as Record<string, unknown>
  return (
    h.version === 1 &&
    typeof h.text === 'string' &&
    h.text.trim().length >= JOB_OFFER_MIN_CHARS &&
    h.text.length <= JOB_OFFER_MAX_CHARS &&
    typeof h.title === 'string' &&
    typeof h.company === 'string' &&
    typeof h.createdAt === 'number' &&
    now - h.createdAt >= 0 &&
    now - h.createdAt <= HANDOFF_MAX_AGE_MS &&
    (h.language === undefined || h.language === 'es' || h.language === 'en') &&
    (h.sourceUrl === undefined || typeof h.sourceUrl === 'string') &&
    (h.location === undefined || typeof h.location === 'string') &&
    (h.jobId === undefined || typeof h.jobId === 'string') &&
    (h.matchScore === undefined || (typeof h.matchScore === 'number' && h.matchScore >= 0 && h.matchScore <= 100))
  )
}

/** Lee y BORRA el traspaso. Devuelve null si no hay, si está caducado o si no tiene la forma esperada. */
export function consumeHandoff(now: number = Date.now()): OfferHandoff | null {
  let raw: string | null = null
  try {
    raw = sessionStorage.getItem(HANDOFF_KEY)
    sessionStorage.removeItem(HANDOFF_KEY)
  } catch {
    return null
  }
  if (!raw) return null
  try {
    const parsed: unknown = JSON.parse(raw)
    return isHandoff(parsed, now) ? parsed : null
  } catch {
    return null
  }
}
