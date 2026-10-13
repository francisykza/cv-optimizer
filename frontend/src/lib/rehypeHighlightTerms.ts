// Plugin rehype mínimo: envuelve en <mark data-kind="…"> las apariciones de los términos indicados.
// Se ejecuta DESPUÉS de rehype-sanitize, así que solo añade marcas sobre contenido ya saneado.
// Solo afecta a la vista previa: copiar y descargar parten siempre del Markdown sin marcas.

export type HighlightKind = 'ungrounded' | 'change'

export interface HighlightGroup {
  kind: HighlightKind
  terms: string[]
}

// Si un término está en los dos grupos, gana el aviso de "no está en tu CV".
const PRIORITY: Record<HighlightKind, number> = { ungrounded: 2, change: 1 }

interface TextNode {
  type: 'text'
  value: string
}
interface ElementNode {
  type: 'element'
  tagName: string
  properties: Record<string, unknown>
  children: HastNode[]
}
type HastNode = TextNode | ElementNode | { type: string; children?: HastNode[] }

const SKIP_TAGS = new Set(['code', 'pre', 'mark'])

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function buildTermsRegExp(terms: string[]): RegExp | null {
  const unique = [...new Set(terms.map((t) => t.trim()).filter((t) => t.length > 0))]
  if (unique.length === 0) return null
  // Los términos más largos primero, para que "Universidad X" gane a "X".
  unique.sort((a, b) => b.length - a.length)
  return new RegExp(`(?<![\\p{L}\\p{N}])(${unique.map(escapeRegExp).join('|')})(?![\\p{L}\\p{N}])`, 'giu')
}

interface TermInfo {
  term: string
  kind: HighlightKind
}

function buildLookup(groups: HighlightGroup[]): Map<string, TermInfo> {
  const lookup = new Map<string, TermInfo>()
  for (const { kind, terms } of groups) {
    for (const raw of terms) {
      const term = raw.trim()
      if (!term) continue
      const key = term.toLowerCase()
      const existing = lookup.get(key)
      if (!existing || PRIORITY[kind] > PRIORITY[existing.kind]) lookup.set(key, { term, kind })
    }
  }
  return lookup
}

function splitText(node: TextNode, pattern: RegExp, lookup: Map<string, TermInfo>): HastNode[] {
  const parts: HastNode[] = []
  let last = 0
  for (const match of node.value.matchAll(pattern)) {
    const index = match.index ?? 0
    const info = lookup.get(match[0].toLowerCase())
    if (!info) continue
    if (index > last) parts.push({ type: 'text', value: node.value.slice(last, index) })
    parts.push({
      type: 'element',
      tagName: 'mark',
      properties: { dataTerm: info.term, dataKind: info.kind },
      children: [{ type: 'text', value: match[0] }],
    })
    last = index + match[0].length
  }
  if (parts.length === 0) return [node]
  if (last < node.value.length) parts.push({ type: 'text', value: node.value.slice(last) })
  return parts
}

function walk(node: HastNode, pattern: RegExp, lookup: Map<string, TermInfo>): void {
  if (!('children' in node) || !node.children) return
  if (node.type === 'element' && SKIP_TAGS.has((node as ElementNode).tagName)) return
  node.children = node.children.flatMap((child) =>
    child.type === 'text' ? splitText(child as TextNode, pattern, lookup) : (walk(child, pattern, lookup), [child]),
  )
}

export function rehypeHighlightTerms(options: { groups: HighlightGroup[] }) {
  const lookup = buildLookup(options.groups)
  const pattern = buildTermsRegExp([...lookup.values()].map((info) => info.term))
  return (tree: HastNode) => {
    if (pattern) walk(tree, pattern, lookup)
  }
}
