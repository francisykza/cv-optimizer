// Añade una habilidad a la sección de habilidades del CV en Markdown (función pura).
// La usa el panel de sugerencias ATS: el CV visible se deriva aplicándola sobre el Markdown del
// servidor, así que quitar una habilidad es solo volver a calcularlo sin ella.

import { buildTermsRegExp } from './rehypeHighlightTerms'

const SKILLS_HEADING =
  /^(#{2,3})\s+.*\b(habilidades|competencias|conocimientos|aptitudes|herramientas|skills|tools)\b/i
const ENGLISH_HEADINGS = /^#{2,3}\s+(experience|education|skills|summary|profile|work)\b/im
const HEADING = /^(#{1,6})\s/
const LIST_ITEM = /^(\s*[-*+])\s+/

export function containsSkill(markdown: string, skill: string): boolean {
  return buildTermsRegExp([skill])?.test(markdown) ?? false
}

export function injectSkill(markdown: string, skill: string): string {
  const term = skill.trim()
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
  } else {
    // Párrafo con habilidades separadas por comas ("Excel, Word, Contanet.").
    lines[last] = `${lines[last].replace(/[.;]?\s*$/, '')}, ${term}`
  }
  return lines.join('\n')
}
