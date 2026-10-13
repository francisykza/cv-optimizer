import { act, fireEvent, render, renderHook, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Toaster } from 'react-hot-toast'
import { describe, expect, it, vi } from 'vitest'

import { useByokKey } from '../hooks/useByokKey'
import type { OptimizeResponse } from '../types/api'
import { FileUploader } from './FileUploader'
import { AtsSuggestions } from './result/AtsSuggestions'
import { ResultViewer } from './result/ResultViewer'

const RESULT: OptimizeResponse = {
  request_id: 'req-1',
  optimized_markdown: '# Ana García\n\n## Experiencia\n- APIs con **FastAPI**\n\n<script>alert(1)</script>',
  match: { score_before: 40, score_after: 70, matched_keywords: ['Python', 'FastAPI'], missing_keywords: ['Kubernetes'], soft_skills: [] },
  gaps: ['Kubernetes'],
  changes_summary: ['Resumen orientado a backend.'],
  warnings: [],
  changes: [],
  ats_suggestions: [],
  quality: 'ok',
  meta: {
    mode: 'server',
    provider: 'groq',
    model: 'llama-3.3-70b-versatile',
    prompt_version: 'v1',
    latency_ms: 4200,
    tokens: { input: 1000, output: 500 },
    pdf_pages: 1,
  },
}

describe('FileUploader', () => {
  it('acepta un PDF', async () => {
    const onFileChange = vi.fn()
    render(<FileUploader file={null} onFileChange={onFileChange} />)

    const pdf = new File(['%PDF-1.4'], 'cv.pdf', { type: 'application/pdf' })
    await userEvent.upload(screen.getByTestId('file-input'), pdf)

    expect(onFileChange).toHaveBeenCalledWith(pdf)
  })

  it('rechaza archivos que no son PDF al soltarlos', () => {
    const onFileChange = vi.fn()
    render(<FileUploader file={null} onFileChange={onFileChange} />)

    const png = new File(['x'], 'foto.png', { type: 'image/png' })
    fireEvent.drop(screen.getByRole('button', { name: /arrastrar el cv/i }), { dataTransfer: { files: [png] } })

    expect(onFileChange).toHaveBeenCalledWith(null)
    expect(screen.getByRole('alert')).toHaveTextContent('Solo se admiten archivos PDF')
  })

  it('rechaza PDFs de más de 5 MB', async () => {
    const onFileChange = vi.fn()
    render(<FileUploader file={null} onFileChange={onFileChange} />)

    const big = new File([new Uint8Array(6 * 1024 * 1024)], 'cv.pdf', { type: 'application/pdf' })
    await userEvent.upload(screen.getByTestId('file-input'), big)

    expect(onFileChange).toHaveBeenCalledWith(null)
    expect(screen.getByRole('alert')).toHaveTextContent('el máximo es 5 MB')
  })
})

describe('ResultViewer', () => {
  it('renderiza el Markdown sin ejecutar HTML embebido', () => {
    const { container } = render(<ResultViewer result={RESULT} onReset={() => {}} />)

    expect(screen.getByRole('heading', { name: 'Ana García' })).toBeInTheDocument()
    expect(screen.getByText('FastAPI', { selector: 'strong' })).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(screen.getByText('70%')).toBeInTheDocument()
  })

  it('confirma la verificación cuando no hay datos inventados', () => {
    render(<ResultViewer result={RESULT} onReset={() => {}} />)
    expect(screen.getByText('Verificación anti-invención')).toBeInTheDocument()
    expect(document.querySelector('mark')).toBeNull()
  })

  it('resalta en la vista previa los datos no respaldados y pide revisión', () => {
    const result: OptimizeResponse = {
      ...RESULT,
      optimized_markdown: '# Ana García\n\n- Reduje la latencia un 45% con **Kubernetes**.',
      quality: 'needs_review',
      warnings: [
        { code: 'UNGROUNDED_METRIC', message: "La cifra '45%' no aparece.", term: '45', snippet: null },
        { code: 'GAP_LEAKED', message: "'Kubernetes' no aparece.", term: 'Kubernetes', snippet: null },
        { code: 'FORMAT', message: 'Contiene tablas.', term: 'tabla', snippet: null },
      ],
    }
    render(<ResultViewer result={result} onReset={() => {}} />)

    const marks = [...document.querySelectorAll('mark')].map((m) => [m.textContent, m.dataset.term])
    expect(marks).toEqual([
      ['45', '45'],
      ['Kubernetes', 'Kubernetes'],
    ])
    expect(screen.getByText('Revisa 2 datos')).toBeInTheDocument()
    expect(screen.getByText('Revisa este CV antes de usarlo.')).toBeInTheDocument()
    expect(screen.getByText('Contiene tablas.')).toBeInTheDocument() // FORMAT: aviso, no resaltado
  })

  it('resalta en verde las reformulaciones y se puede desactivar', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    const result: OptimizeResponse = {
      ...RESULT,
      optimized_markdown: '# Ana García\n\n- Diseñé APIs con **FastAPI** y Kubernetes.',
      changes: ['Diseñé', 'Kubernetes'], // "Kubernetes" también está en ámbar: debe ganar el ámbar
      warnings: [{ code: 'GAP_LEAKED', message: 'x', term: 'Kubernetes', snippet: null }],
      quality: 'needs_review',
    }
    render(<ResultViewer result={result} onReset={() => {}} />)

    const kinds = () => Object.fromEntries([...document.querySelectorAll('mark')].map((m) => [m.textContent, m.dataset.kind]))
    expect(kinds()).toEqual({ Diseñé: 'change', Kubernetes: 'ungrounded' })

    await user.click(screen.getByRole('switch', { name: /resaltar cambios/i }))
    expect(kinds()).toEqual({ Kubernetes: 'ungrounded' }) // el ámbar no se oculta nunca

    // Copiar usa siempre el Markdown limpio, sin marcas.
    await user.click(screen.getByRole('button', { name: /copiar al portapapeles/i }))
    expect(writeText).toHaveBeenCalledWith(result.optimized_markdown)
  })

  it('muestra las afirmaciones del resumen sin respaldo como avisos', () => {
    const claim = 'Orientada a la mejora continua'
    const result: OptimizeResponse = {
      ...RESULT,
      optimized_markdown: `# Ana

## Resumen profesional
${claim}.`,
      warnings: [{ code: 'UNGROUNDED_CLAIM', message: 'x', term: claim, snippet: null }],
      quality: 'needs_review',
    }
    render(<ResultViewer result={result} onReset={() => {}} />)

    expect(screen.getByText('Afirmación')).toBeInTheDocument()
    expect(document.querySelector('mark[data-kind="ungrounded"]')).toHaveTextContent(claim)
  })

  it('muestra las competencias personales aparte y el aviso de palabra clave perdida', () => {
    const result: OptimizeResponse = {
      ...RESULT,
      match: { ...RESULT.match, soft_skills: ['proactiva', 'dinámica'] },
      warnings: [{ code: 'KEYWORD_DROPPED', message: "'Contanet' estaba en tu CV original…", term: 'Contanet', snippet: null }],
    }
    render(<ResultViewer result={result} onReset={() => {}} />)

    const soft = screen.getByRole('list', { name: 'Competencias personales' })
    expect(soft).toHaveTextContent('proactiva')
    expect(screen.getByRole('list', { name: 'Palabras clave' })).not.toHaveTextContent('proactiva')
    expect(screen.getByText(/no cuentan en la puntuación/)).toBeInTheDocument()
    // Perder una keyword es informativo: no pide revisar el CV ni se resalta en ámbar.
    expect(screen.getByText(/'Contanet' estaba en tu CV original/)).toBeInTheDocument()
    expect(screen.getByText('Verificación anti-invención')).toBeInTheDocument()
    expect(document.querySelector('mark[data-kind="ungrounded"]')).toBeNull()
  })

  it('añade una sugerencia ATS al CV con un clic y se puede quitar', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    const result: OptimizeResponse = {
      ...RESULT,
      optimized_markdown: '# Ana García\n\n## Habilidades\n- Python\n- FastAPI',
      match: { ...RESULT.match, missing_keywords: ['Kubernetes', 'Docker'] },
      ats_suggestions: ['Kubernetes', 'Docker'],
    }
    render(
      <>
        <ResultViewer result={result} onReset={() => {}} />
        <Toaster />
      </>,
    )

    await user.click(screen.getByRole('button', { name: 'Añadir Kubernetes al CV' }))

    // El chip desaparece, la habilidad entra en la sección y se resalta en azul.
    expect(screen.queryByRole('button', { name: 'Añadir Kubernetes al CV' })).toBeNull()
    expect(document.querySelector('mark[data-kind="added"]')).toHaveTextContent('Kubernetes')
    expect(await screen.findByText('Habilidad añadida al currículum')).toBeInTheDocument()
    // Puntuación recalculada: 3 de 4 palabras clave cubiertas.
    expect(screen.getByText('75%')).toBeInTheDocument()

    // Copiar (y descargar) usan el CV con la habilidad, sin marcas.
    await user.click(screen.getByRole('button', { name: /copiar al portapapeles/i }))
    expect(writeText).toHaveBeenCalledWith('# Ana García\n\n## Habilidades\n- Python\n- FastAPI\n- Kubernetes')

    await user.click(screen.getByRole('button', { name: 'Quitar Kubernetes del CV' }))
    expect(screen.getByRole('button', { name: 'Añadir Kubernetes al CV' })).toBeInTheDocument()
    expect(document.querySelector('mark[data-kind="added"]')).toBeNull()
  })

  it('no muestra el panel de sugerencias si no hay ninguna', () => {
    render(<ResultViewer result={RESULT} onReset={() => {}} />)
    expect(screen.queryByText('Sugerencias ATS')).toBeNull()
  })

  it('ofrece la descarga en Word, PDF y Markdown', async () => {
    const user = userEvent.setup()
    render(<ResultViewer result={RESULT} onReset={() => {}} />)

    await user.click(screen.getByRole('button', { name: /descargar/i }))
    const items = screen.getAllByRole('menuitem').map((i) => i.textContent)
    expect(items[0]).toMatch(/Word \(\.docx\).*Recomendado para ATS/)
    expect(items[1]).toMatch(/PDF/)
    expect(items[2]).toMatch(/Markdown/)

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('copia el Markdown al portapapeles', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    render(<ResultViewer result={RESULT} onReset={() => {}} />)

    await user.click(screen.getByRole('button', { name: /copiar al portapapeles/i }))

    expect(writeText).toHaveBeenCalledWith(RESULT.optimized_markdown)
    expect(await screen.findByText('¡Copiado!')).toBeInTheDocument()
  })

  it('usa el método alternativo si el navegador deniega el permiso del portapapeles', async () => {
    const user = userEvent.setup()
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new DOMException('denied', 'NotAllowedError'))
    const execCommand = vi.fn(() => true)
    Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true })
    render(<ResultViewer result={RESULT} onReset={() => {}} />)

    await user.click(screen.getByRole('button', { name: /copiar al portapapeles/i }))

    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(await screen.findByText('¡Copiado!')).toBeInTheDocument()
  })
})

describe('AtsSuggestions', () => {
  it('no permite añadir mientras está desactivado', async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn()
    render(<AtsSuggestions suggestions={['SAP']} added={[]} onAdd={onAdd} onRemove={() => {}} disabled />)

    await user.click(screen.getByRole('button', { name: 'Añadir SAP al CV' }))
    expect(onAdd).not.toHaveBeenCalled()
  })
})

describe('useByokKey', () => {
  it('no guarda la clave salvo que el usuario lo pida, y nunca en localStorage', () => {
    const { result } = renderHook(() => useByokKey())

    act(() => result.current.setApiKey('gsk_secret'))
    expect(sessionStorage.length).toBe(0)

    act(() => result.current.setRemember(true))
    expect(Object.values({ ...sessionStorage })).toContain('gsk_secret')

    act(() => result.current.clear())
    expect(sessionStorage.length).toBe(0)
    expect(localStorage.length).toBe(0)
  })
})
