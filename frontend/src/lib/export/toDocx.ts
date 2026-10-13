import type { Block, TextRun as Run } from './markdownToBlocks'

const HEADING_SIZES = { 1: 32, 2: 24, 3: 22 } as const // medios puntos: 16 / 12 / 11 pt
const CM = 567 // twips por centímetro

/** Genera un .docx con estilos nativos de Word (Heading 1/2/3 y viñetas reales): es lo que
 *  usan los ATS para reconocer las secciones. La librería se carga solo al exportar. */
export async function blocksToDocx(blocks: Block[], title: string): Promise<Blob> {
  const { AlignmentType, BorderStyle, Document, HeadingLevel, Packer, Paragraph, TextRun } = await import('docx')

  const runs = (items: Run[]) =>
    items.map((r) => new TextRun({ text: r.text, bold: r.bold, italics: r.italic }))

  const headingLevels = { 1: HeadingLevel.HEADING_1, 2: HeadingLevel.HEADING_2, 3: HeadingLevel.HEADING_3 }

  const paragraphs = blocks.map((block) => {
    switch (block.type) {
      case 'heading':
        return new Paragraph({
          heading: headingLevels[block.level],
          children: runs(block.runs),
          ...(block.level === 2 && {
            border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: 'CBD5E1', space: 2 } },
          }),
        })
      case 'bullet':
        return new Paragraph({ bullet: { level: Math.min(block.level, 2) }, children: runs(block.runs) })
      default:
        return new Paragraph({ children: runs(block.runs) })
    }
  })

  const doc = new Document({
    title,
    creator: 'CV-Optimizer',
    styles: {
      default: {
        document: {
          run: { font: 'Calibri', size: 22, color: '1F2937' },
          paragraph: { spacing: { after: 80, line: 276 } },
        },
        ...Object.fromEntries(
          ([1, 2, 3] as const).map((level) => [
            `heading${level}`,
            {
              run: { font: 'Calibri', size: HEADING_SIZES[level], bold: true, color: level === 2 ? '3730A3' : '111827' },
              paragraph: { spacing: { before: level === 1 ? 0 : 240, after: 100 } },
            },
          ]),
        ),
      },
    },
    sections: [
      {
        properties: {
          page: { margin: { top: 2 * CM, bottom: 2 * CM, left: 2 * CM, right: 2 * CM } },
        },
        children: paragraphs.length ? paragraphs : [new Paragraph({ alignment: AlignmentType.LEFT, children: [] })],
      },
    ],
  })

  return Packer.toBlob(doc)
}
