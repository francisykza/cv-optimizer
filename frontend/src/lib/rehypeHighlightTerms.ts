// Plugin rehype mínimo: envuelve en <mark> las apariciones de los términos indicados.
// Se ejecuta DESPUÉS de rehype-sanitize, así que solo añade marcas sobre contenido ya saneado.

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

function splitText(node: TextNode, pattern: RegExp, lookup: Map<string, string>): HastNode[] {
  const parts: HastNode[] = []
  let last = 0
  for (const match of node.value.matchAll(pattern)) {
    const index = match.index ?? 0
    if (index > last) parts.push({ type: 'text', value: node.value.slice(last, index) })
    parts.push({
      type: 'element',
      tagName: 'mark',
      properties: { dataTerm: lookup.get(match[0].toLowerCase()) ?? match[0] },
      children: [{ type: 'text', value: match[0] }],
    })
    last = index + match[0].length
  }
  if (parts.length === 0) return [node]
  if (last < node.value.length) parts.push({ type: 'text', value: node.value.slice(last) })
  return parts
}

function walk(node: HastNode, pattern: RegExp, lookup: Map<string, string>): void {
  if (!('children' in node) || !node.children) return
  if (node.type === 'element' && SKIP_TAGS.has((node as ElementNode).tagName)) return
  node.children = node.children.flatMap((child) =>
    child.type === 'text' ? splitText(child as TextNode, pattern, lookup) : (walk(child, pattern, lookup), [child]),
  )
}

export function rehypeHighlightTerms(options: { terms: string[] }) {
  const pattern = buildTermsRegExp(options.terms)
  const lookup = new Map(options.terms.map((t) => [t.trim().toLowerCase(), t]))
  return (tree: HastNode) => {
    if (pattern) walk(tree, pattern, lookup)
  }
}
