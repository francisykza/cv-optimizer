/**
 * De dónde viene la oferta del paso 2: del Buscador (con su ficha) o de un enlace pegado. Sirve para
 * volver a la oferta original al terminar y para apuntar la candidatura (SPEC del hunter §18.5).
 */
export interface OfferSource {
  from: 'hunter' | 'url'
  url?: string
  title?: string
  company?: string
  location?: string
  /** Id de la oferta en el Buscador: la candidatura queda enlazada a su ficha. */
  jobId?: string
  /** Nota del juez del Buscador (0-100). */
  matchScore?: number
}

/** "linkedin.com" para enseñar a dónde lleva el enlace sin la URL entera. */
export function offerHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

/** Puesto probable: la primera línea de la oferta. El Buscador la escribe "Puesto — Empresa (…)". */
export function guessTitle(text: string): string {
  const first =
    text
      .split('\n')
      .map((line) => line.trim())
      .find(Boolean) ?? ''
  const title = first.split(' — ')[0].trim()
  return title.length >= 3 && title.length <= 120 ? title : ''
}
