import type { Content, TDocumentDefinitions, TVirtualFileSystem } from 'pdfmake/interfaces'

import type { Block, TextRun } from './markdownToBlocks'

const PAGE_WIDTH = 595.28 // A4 en puntos
const MARGIN = 56 // ~2 cm
const CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

const text = (runs: TextRun[]) => runs.map((r) => ({ text: r.text, bold: r.bold, italics: r.italic }))

/** Definición pdfmake del CV. Función pura (testeable): solo texto y líneas vectoriales, nunca
 *  imágenes, para que el PDF tenga texto real que los ATS puedan extraer. */
export function blocksToPdfDefinition(blocks: Block[], title: string): TDocumentDefinitions {
  const content: Content[] = []
  let bullets: { level: number; items: Content[] } | null = null

  const flushBullets = () => {
    if (bullets) content.push({ ul: bullets.items, margin: [bullets.level * 14, 0, 0, 6] })
    bullets = null
  }

  for (const block of blocks) {
    if (block.type === 'bullet') {
      if (bullets && bullets.level !== block.level) flushBullets()
      bullets ??= { level: block.level, items: [] }
      bullets.items.push({ text: text(block.runs) })
      continue
    }
    flushBullets()
    if (block.type === 'heading') {
      content.push({ text: text(block.runs), style: `h${block.level}` })
      if (block.level === 2) {
        content.push({
          canvas: [{ type: 'line', x1: 0, y1: 0, x2: CONTENT_WIDTH, y2: 0, lineWidth: 0.6, lineColor: '#CBD5E1' }],
          margin: [0, 0, 0, 6],
        })
      }
    } else {
      content.push({ text: text(block.runs), margin: [0, 0, 0, 6] })
    }
  }
  flushBullets()

  return {
    info: { title, creator: 'CV-Optimizer' },
    pageSize: 'A4',
    pageMargins: [MARGIN, MARGIN, MARGIN, MARGIN],
    content,
    defaultStyle: { font: 'Roboto', fontSize: 10.5, lineHeight: 1.25, color: '#1F2937' },
    styles: {
      h1: { fontSize: 20, bold: true, color: '#111827', margin: [0, 0, 0, 4] },
      h2: { fontSize: 11.5, bold: true, color: '#3730A3', margin: [0, 12, 0, 3] },
      h3: { fontSize: 11, bold: true, color: '#111827', margin: [0, 6, 0, 2] },
    },
  }
}

/** Renderiza el PDF en el navegador. pdfmake y sus fuentes (~2 MB) se cargan solo al exportar. */
export async function blocksToPdf(blocks: Block[], title: string): Promise<Blob> {
  const [pdfMakeModule, vfsModule] = await Promise.all([
    import('pdfmake/build/pdfmake'),
    import('pdfmake/build/vfs_fonts'),
  ])
  // Son módulos CommonJS: según el bundler llegan como `default` o como el propio módulo.
  const pdfMake = pdfMakeModule.default ?? pdfMakeModule
  const vfs: TVirtualFileSystem = vfsModule.default ?? (vfsModule as unknown as TVirtualFileSystem)
  pdfMake.addVirtualFileSystem(vfs)
  pdfMake.setFonts({
    Roboto: {
      normal: 'Roboto-Regular.ttf',
      bold: 'Roboto-Medium.ttf',
      italics: 'Roboto-Italic.ttf',
      bolditalics: 'Roboto-MediumItalic.ttf',
    },
  })
  return pdfMake.createPdf(blocksToPdfDefinition(blocks, title)).getBlob()
}
