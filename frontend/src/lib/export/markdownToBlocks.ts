import type { List, PhrasingContent, Root, RootContent } from 'mdast'
import remarkGfm from 'remark-gfm'
import remarkParse from 'remark-parse'
import { unified } from 'unified'

/** Representación intermedia del CV, común a los exportadores DOCX y PDF.
 *  Solo contiene lo que un ATS lee bien: encabezados, párrafos y viñetas con negrita/cursiva. */
export interface TextRun {
  text: string
  bold?: boolean
  italic?: boolean
}

export type Block =
  | { type: 'heading'; level: 1 | 2 | 3; runs: TextRun[] }
  | { type: 'paragraph'; runs: TextRun[] }
  | { type: 'bullet'; level: number; runs: TextRun[] }

function inline(nodes: PhrasingContent[], marks: { bold?: boolean; italic?: boolean } = {}): TextRun[] {
  const runs: TextRun[] = []
  for (const node of nodes) {
    switch (node.type) {
      case 'text':
      case 'inlineCode':
        runs.push({ text: node.value, ...marks })
        break
      case 'strong':
        runs.push(...inline(node.children, { ...marks, bold: true }))
        break
      case 'emphasis':
        runs.push(...inline(node.children, { ...marks, italic: true }))
        break
      case 'delete':
      case 'link':
        runs.push(...inline(node.children, marks)) // del enlace solo interesa el texto visible
        break
      case 'break':
        runs.push({ text: ' ', ...marks })
        break
      default:
        break // imágenes, HTML, notas: no aptos para ATS
    }
  }
  return mergeRuns(runs)
}

/** Une tramos contiguos con el mismo formato (menos nodos en el documento final). */
function mergeRuns(runs: TextRun[]): TextRun[] {
  const merged: TextRun[] = []
  for (const run of runs) {
    const last = merged.at(-1)
    if (last && Boolean(last.bold) === Boolean(run.bold) && Boolean(last.italic) === Boolean(run.italic)) {
      last.text += run.text
    } else {
      merged.push({ ...run })
    }
  }
  return merged.filter((r) => r.text.length > 0)
}

function listBlocks(list: List, level: number): Block[] {
  const blocks: Block[] = []
  for (const item of list.children) {
    for (const child of item.children) {
      if (child.type === 'paragraph') blocks.push({ type: 'bullet', level, runs: inline(child.children) })
      else if (child.type === 'list') blocks.push(...listBlocks(child, level + 1))
    }
  }
  return blocks
}

function toBlocks(node: RootContent): Block[] {
  switch (node.type) {
    case 'heading':
      return [{ type: 'heading', level: Math.min(node.depth, 3) as 1 | 2 | 3, runs: inline(node.children) }]
    case 'paragraph':
      return [{ type: 'paragraph', runs: inline(node.children) }]
    case 'list':
      return listBlocks(node, 0)
    case 'blockquote':
      return node.children.flatMap(toBlocks)
    case 'code':
      return [{ type: 'paragraph', runs: [{ text: node.value }] }]
    case 'table':
      // Los ATS leen mal las tablas: cada fila se convierte en un párrafo "celda · celda".
      return node.children.map((row) => ({
        type: 'paragraph' as const,
        runs: mergeRuns(
          row.children.flatMap((cell, i) => [...(i ? [{ text: ' · ' }] : []), ...inline(cell.children)]),
        ),
      }))
    default:
      return [] // separadores, HTML incrustado, etc.
  }
}

export function markdownToBlocks(markdown: string): Block[] {
  const tree = unified().use(remarkParse).use(remarkGfm).parse(markdown) as Root
  return tree.children.flatMap(toBlocks).filter((b) => b.runs.length > 0)
}

export function plainText(runs: TextRun[]): string {
  return runs.map((r) => r.text).join('')
}

/** "CV_Ana_Garcia_Lopez_optimizado" a partir del primer encabezado H1 (el nombre del candidato). */
export function suggestedFileName(blocks: Block[]): string {
  const h1 = blocks.find((b) => b.type === 'heading' && b.level === 1)
  const name = h1
    ? plainText(h1.runs)
        .normalize('NFKD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^A-Za-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '')
        .slice(0, 60)
    : ''
  return name ? `CV_${name}_optimizado` : 'cv-optimizado'
}
