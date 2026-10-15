// Añade una habilidad a la sección de habilidades del CV en Markdown (función pura).
// La usa el panel de sugerencias ATS: el CV visible se deriva aplicándola sobre el Markdown del
// servidor, así que quitar una habilidad es solo volver a calcularlo sin ella.

import { buildTermsRegExp } from './rehypeHighlightTerms'

const SKILLS_HEADING = /^(#{2,3})\s+.*\b(habilidades|competencias|conocimientos|aptitudes|herramientas|skills|tools)\b/i
const ENGLISH_HEADINGS = /^#{2,3}\s+(experience|education|skills|summary|profile|work)\b/im
const HEADING = /^(#{1,6})\s/
const LIST_ITEM = /^(\s*[-*+])\s+/

/** Sin tildes ni mayúsculas, igual que el backend (match_scorer.contains). */
const fold = (text: string) => text.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase()

export function containsSkill(markdown: string, skill: string): boolean {
  return buildTermsRegExp([fold(skill)])?.test(fold(markdown)) ?? false
}

/** Etiqueta corta de un requisito: "Inglés C1 (el CV indica B2)" -> "Inglés C1". */
export function gapLabel(gap: string): string {
  return gap
    .replace(/\s*\([^)]*\)/g, '')
    .replace(/[.:;]+$/, '')
    .trim()
}

/** Destino por defecto de la experiencia que añade el usuario. El resto son líneas de puesto. */
export const SKILLS_TARGET = 'skills'

/** Texto que se añade al CV cuando el usuario confirma que tiene experiencia en un requisito.
 *  En Habilidades: "Requisito: cómo lo usó". Bajo un puesto: una viñeta normal que conserva el
 *  requisito (para el ATS) si la frase no lo menciona ya. */
export function experienceNote(gap: string, note: string, target: string = SKILLS_TARGET): string {
  const label = gapLabel(gap)
  const text = note.trim().replace(/\.$/, '')
  if (target === SKILLS_TARGET) return `${label}: ${text}`
  const sentence = text.charAt(0).toUpperCase() + text.slice(1)
  return containsSkill(sentence, label) ? sentence : `${sentence} (${label})`
}

export function injectSkill(markdown: string, skill: string): string {
  return inject(markdown, skill.trim(), false)
}

/** Añade la experiencia del usuario en Habilidades o como viñeta del puesto elegido (`target` es
 *  la línea del puesto, tal como la devuelve `experienceEntries`). */
export function injectExperience(markdown: string, gap: string, note: string, target: string = SKILLS_TARGET): string {
  if (target !== SKILLS_TARGET) {
    const result = injectIntoEntry(markdown, target, experienceNote(gap, note, target))
    if (result !== null) return result
  }
  return inject(markdown, experienceNote(gap, note), true)
}

const EXPERIENCE_HEADING = /^(#{1,3})\s+.*(experien|trayectoria|employment|work history|empleo)/i
const BOLD_TITLE = /^\s*\*\*[^*]+\*\*/

export interface ExperienceEntry {
  /** Línea exacta del puesto en el Markdown (identifica el destino). */
  line: string
  /** Texto legible: "Gestoria Sur SL - Auxiliar administrativa (2022 - Actualidad)". */
  label: string
}

/** Puestos de la sección de experiencia: subtítulos (### Puesto) o líneas en negrita. */
export function experienceEntries(markdown: string): ExperienceEntry[] {
  const lines = markdown.split('\n')
  const start = lines.findIndex((line) => EXPERIENCE_HEADING.test(line))
  if (start === -1) return []
  const level = lines[start].match(HEADING)![1].length
  const entries: ExperienceEntry[] = []
  for (let i = start + 1; i < lines.length; i++) {
    const heading = lines[i].match(HEADING)
    if (heading && heading[1].length <= level) break
    if (heading || (BOLD_TITLE.test(lines[i]) && !LIST_ITEM.test(lines[i]))) {
      const label = lines[i]
        .replace(/^#{1,6}\s+/, '')
        .replace(/\*\*|__|\*/g, '')
        .trim()
      if (label) entries.push({ line: lines[i], label })
    }
  }
  return entries
}

function injectIntoEntry(markdown: string, entryLine: string, text: string): string | null {
  if (containsSkill(markdown, text)) return markdown
  const lines = markdown.split('\n')
  const start = lines.indexOf(entryLine)
  if (start === -1) return null
  // El bloque del puesto acaba en el siguiente encabezado o en el siguiente puesto en negrita.
  let end = lines.length
  for (let i = start + 1; i < lines.length; i++) {
    if (HEADING.test(lines[i]) || (BOLD_TITLE.test(lines[i]) && !LIST_ITEM.test(lines[i]))) {
      end = i
      break
    }
  }
  let last = end - 1
  while (last > start && lines[last].trim() === '') last--
  const marker = LIST_ITEM.test(lines[last]) ? lines[last].match(LIST_ITEM)![1] : '-'
  lines.splice(last + 1, 0, `${marker} ${text}`)
  return lines.join('\n')
}

function inject(markdown: string, term: string, asListItem: boolean): string {
  if (!term || containsSkill(markdown, term)) return markdown

  const lines = markdown.split('\n')
  const headingIndex = lines.findIndex((line) => SKILLS_HEADING.test(line))

  if (headingIndex === -1) {
    const title = ENGLISH_HEADINGS.test(markdown) ? 'Skills' : 'Habilidades'
    return `${markdown.trimEnd()}\n\n## ${title}\n\n- ${term}\n`
  }

  // La sección acaba en el siguiente encabezado del mismo nivel o superior.
  const level = lines[headingIndex].match(HEADING)![1].length
  let end = lines.length
  for (let i = headingIndex + 1; i < lines.length; i++) {
    const heading = lines[i].match(HEADING)
    if (heading && heading[1].length <= level) {
      end = i
      break
    }
  }

  let last = end - 1
  while (last > headingIndex && lines[last].trim() === '') last--

  if (last === headingIndex) {
    lines.splice(headingIndex + 1, 0, '', `- ${term}`)
  } else if (LIST_ITEM.test(lines[last])) {
    const marker = lines[last].match(LIST_ITEM)![1]
    lines.splice(last + 1, 0, `${marker} ${term}`)
  } else if (asListItem) {
    // Una frase no cabe en una lista separada por comas: va en su propia viñeta.
    lines.splice(last + 1, 0, '', `- ${term}`)
  } else {
    // Párrafo con habilidades separadas por comas ("Excel, Word, Contanet.").
    lines[last] = `${lines[last].replace(/[.;]?\s*$/, '')}, ${term}`
  }
  return lines.join('\n')
}
