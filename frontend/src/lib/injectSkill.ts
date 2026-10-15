// Añade una habilidad a la sección de habilidades del CV en Markdown (función pura).
// La usa el panel de sugerencias ATS: el CV visible se deriva aplicándola sobre el Markdown del
// servidor, así que quitar una habilidad es solo volver a calcularlo sin ella.

import { buildTermsRegExp } from './rehypeHighlightTerms'

const SKILLS_HEADING =
  /^(#{2,3})\s+.*\b(habilidades|competencias|conocimientos|aptitudes|herramientas|skills|tools)\b/i
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
  return gap.replace(/\s*\([^)]*\)/g, '').replace(/[.:;]+$/, '').trim()
}

/** Texto que se añade al CV cuando el usuario confirma que tiene experiencia en un requisito. */
export function experienceNote(gap: string, note: string): string {
  return `${gapLabel(gap)}: ${note.trim().replace(/\.$/, '')}`
}

export function injectSkill(markdown: string, skill: string): string {
  return inject(markdown, skill.trim(), false)
}

/** Añade "Requisito: cómo lo usaste" como viñeta propia en la sección de habilidades. */
export function injectExperience(markdown: string, gap: string, note: string): string {
  return inject(markdown, experienceNote(gap, note), true)
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
