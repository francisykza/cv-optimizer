import { describe, expect, it } from 'vitest'

import { markdownToBlocks, suggestedFileName } from './markdownToBlocks'
import { blocksToDocx } from './toDocx'
import { blocksToPdfDefinition } from './toPdf'

const CV = `# Ana García López
Desarrolladora Backend · Madrid

## Experiencia
### Desarrolladora Python — Acme Software SL
*2021 – Actualidad*
- Diseño de APIs REST con **FastAPI** y PostgreSQL.
  - Subtarea anidada
- Reducción de la latencia un 30%.

## Habilidades
| Área | Tecnologías |
|---|---|
| Backend | Python, FastAPI |

![foto](foto.png)
<script>alert(1)</script>
`

describe('markdownToBlocks', () => {
  const blocks = markdownToBlocks(CV)

  it('convierte encabezados, párrafos y viñetas con formato en línea', () => {
    expect(blocks[0]).toEqual({ type: 'heading', level: 1, runs: [{ text: 'Ana García López' }] })
    expect(blocks).toContainEqual({ type: 'heading', level: 2, runs: [{ text: 'Experiencia' }] })
    expect(blocks).toContainEqual({ type: 'paragraph', runs: [{ text: '2021 – Actualidad', italic: true }] })
    expect(blocks).toContainEqual({
      type: 'bullet',
      level: 0,
      runs: [{ text: 'Diseño de APIs REST con ' }, { text: 'FastAPI', bold: true }, { text: ' y PostgreSQL.' }],
    })
    expect(blocks).toContainEqual({ type: 'bullet', level: 1, runs: [{ text: 'Subtarea anidada' }] })
  })

  it('aplana tablas y descarta imágenes y HTML (no aptos para ATS)', () => {
    expect(blocks).toContainEqual({ type: 'paragraph', runs: [{ text: 'Backend · Python, FastAPI' }] })
    const allText = JSON.stringify(blocks)
    expect(allText).not.toContain('foto')
    expect(allText).not.toContain('script')
  })

  it('genera el nombre de archivo a partir del nombre del candidato, sin tildes', () => {
    expect(suggestedFileName(blocks)).toBe('CV_Ana_Garcia_Lopez_optimizado')
    expect(suggestedFileName(markdownToBlocks('Sin encabezado'))).toBe('cv-optimizado')
  })
})

describe('blocksToPdfDefinition', () => {
  it('produce texto real y nunca imágenes (legible por ATS)', () => {
    const definition = blocksToPdfDefinition(markdownToBlocks(CV), 'CV Ana')
    const json = JSON.stringify(definition)
    expect(json).toContain('Ana García López')
    expect(json).toContain('"text":"FastAPI","bold":true')
    expect(json).not.toContain('"image"')
    expect(definition.pageSize).toBe('A4')
  })
})

describe('blocksToDocx', () => {
  it('genera un .docx válido (un ZIP) con los encabezados como estilos de Word', async () => {
    const { Packer, Document } = await import('docx')
    expect(Packer).toBeDefined()
    expect(Document).toBeDefined()

    const blob = await blocksToDocx(markdownToBlocks(CV), 'CV Ana')
    // El Blob de jsdom no implementa arrayBuffer(); FileReader sí.
    const bytes = new Uint8Array(
      await new Promise<ArrayBuffer>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(reader.result as ArrayBuffer)
        reader.onerror = () => reject(reader.error)
        reader.readAsArrayBuffer(blob)
      }),
    )
    expect(String.fromCharCode(bytes[0], bytes[1])).toBe('PK')

    const JSZip = (await import('jszip')).default
    const zip = await JSZip.loadAsync(bytes)
    const xml = await zip.file('word/document.xml')!.async('string')
    expect(xml).toContain('Ana García López')
    expect(xml).toContain('w:val="Heading1"')
    expect(xml).toContain('w:val="Heading2"')
    expect(xml).toContain('<w:numPr>') // viñetas reales de Word
  })
})
