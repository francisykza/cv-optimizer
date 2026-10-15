// Quita de la oferta los banners de cookies y consentimiento (RGPD) copiados con Ctrl+A.
// Espejo de backend/app/services/consent_filter.py: el backend vuelve a filtrar por si el texto
// llega sin pasar por aquí. Se descartan líneas completas, nunca trozos de una frase.

function fold(text: string): string {
  return text
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
}

const STRONG = [
  'partners use cookies', 'partners process', 'legitimate interest', 'legitimate business interest',
  'cookie identifiers', 'withdraw your consent', 'object to data processing',
  'store and/or access information on a device', 'personalised advertising', 'personalized advertising',
  'personalised ads', 'personalized ads', 'advertising and content measurement', 'audience research',
  'cookie policy', 'cookie settings', 'manage cookies', 'accept all cookies', 'reject all cookies',
  'utilizamos cookies', 'usamos cookies', 'esta web utiliza cookies', 'este sitio web utiliza cookies',
  'politica de cookies', 'configuracion de cookies', 'configurar cookies', 'gestionar cookies',
  'aceptar todas las cookies', 'rechazar todas las cookies', 'aceptar cookies', 'interes legitimo',
  'retirar tu consentimiento', 'publicidad personalizada', 'almacenar o acceder a informacion en un dispositivo',
]
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')
// "we and our 1037 partners", "nuestros 200 socios": el número cambia en cada portal.
const STRONG_RE = new RegExp(`${STRONG.map(escape).join('|')}|\\bour (?:\\d+ )?partners\\b|\\bnuestros (?:\\d+ )?socios\\b`)
const TOPIC = /cookie|consent|consentimiento/
const WEAK = [
  'privacy', 'privacidad', 'partners', 'socios', 'advertising', 'publicidad', 'personal data', 'datos personales',
  'consent', 'consentimiento', 'cookies', 'tracking', 'analytics', 'analitica', 'preferences', 'preferencias',
  'third parties', 'terceros',
]
const BUTTONS = new Set(
  [
    'Aceptar', 'Aceptar todo', 'Aceptar todas', 'Rechazar', 'Rechazar todo', 'Rechazar todas', 'Configurar',
    'Personalizar', 'Más opciones', 'Accept', 'Accept all', 'Reject', 'Reject all', 'Agree', 'I agree',
    'Disagree', 'Manage options', 'More options', 'Learn more', 'Customize',
  ].map(fold),
)

export function isConsentLine(line: string): boolean {
  const folded = fold(line)
  if (!folded) return false
  if (BUTTONS.has(folded.replace(/^[\s.!]+|[\s.!]+$/g, ''))) return true
  if (STRONG_RE.test(folded)) return true
  return TOPIC.test(folded) && WEAK.filter((marker) => folded.includes(marker)).length >= 3
}

export function stripConsentNoise(text: string): string {
  return text
    .split('\n')
    .filter((line) => !isConsentLine(line))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}
