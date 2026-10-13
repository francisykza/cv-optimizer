import { markdownToBlocks, suggestedFileName } from './markdownToBlocks'

export type ExportFormat = 'docx' | 'pdf' | 'md'

export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  // Se libera después de que el navegador haya empezado la descarga.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** Exporta el Markdown limpio (sin resaltados de la interfaz) al formato pedido. */
export async function exportCv(markdown: string, format: ExportFormat): Promise<void> {
  const blocks = markdownToBlocks(markdown)
  const baseName = suggestedFileName(blocks)
  const title = baseName.replace(/_/g, ' ')

  if (format === 'md') {
    downloadBlob(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }), `${baseName}.md`)
  } else if (format === 'docx') {
    const { blocksToDocx } = await import('./toDocx')
    downloadBlob(await blocksToDocx(blocks, title), `${baseName}.docx`)
  } else {
    const { blocksToPdf } = await import('./toPdf')
    downloadBlob(await blocksToPdf(blocks, title), `${baseName}.pdf`)
  }
}
