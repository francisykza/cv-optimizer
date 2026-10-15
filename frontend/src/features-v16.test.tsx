// SDD 1.6: filtro de cookies, memoria local del CV, nivel de ajuste, pitch y experiencia en gaps.
import 'fake-indexeddb/auto'

import { act, render, renderHook, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FileUploader } from './components/FileUploader'
import { ResultViewer } from './components/result/ResultViewer'
import { useCvMemory } from './hooks/useCvMemory'
import { stripConsentNoise } from './lib/consentFilter'
import { forgetCv, loadCv, saveCv } from './lib/cvStore'
import { injectExperience } from './lib/injectSkill'
import { optimizeCv } from './services/api'
import type { OptimizeResponse } from './types/api'

afterEach(async () => {
  vi.restoreAllMocks()
  await forgetCv()
})

describe('stripConsentNoise', () => {
  it('quita el banner de cookies y conserva la oferta', () => {
    const offer = [
      'With your agreement, we and our 1037 partners use cookies or similar technologies to store data.',
      'Personalised advertising and content, advertising and content measurement, audience research',
      'Aceptar todo',
      'Auxiliar administrativo/a',
      'Requisitos: experiencia en RGPD y protección de datos personales.',
    ].join('\n')
    expect(stripConsentNoise(offer)).toBe(
      'Auxiliar administrativo/a\nRequisitos: experiencia en RGPD y protección de datos personales.',
    )
  })
})

describe('memoria local del CV', () => {
  const pdf = () => new File(['%PDF-1.4 contenido'], 'mi-cv.pdf', { type: 'application/pdf' })

  it('guarda, recupera y olvida el PDF en IndexedDB', async () => {
    expect(await saveCv(pdf())).toBe(true)
    const restored = await loadCv()
    expect(restored?.name).toBe('mi-cv.pdf')
    expect(restored?.type).toBe('application/pdf')

    await forgetCv()
    expect(await loadCv()).toBeNull()
  })

  it('está desactivada por defecto y recupera el CV si el usuario la activó', async () => {
    const setFile = vi.fn()
    const first = renderHook(() => useCvMemory(null, setFile))
    await act(async () => {})
    expect(first.result.current.remember).toBe(false)
    expect(setFile).not.toHaveBeenCalled()

    await saveCv(pdf())
    const second = renderHook(() => useCvMemory(null, setFile))
    await waitFor(() => expect(second.result.current.status).toBe('restored'))
    expect(second.result.current.remember).toBe(true)
    expect(setFile.mock.calls[0][0](null).name).toBe('mi-cv.pdf')
  })

  it('el uploader ofrece recordar y olvidar el CV', async () => {
    const user = userEvent.setup()
    function Harness() {
      const [file, setFile] = useState<File | null>(pdf())
      const memory = useCvMemory(file, setFile)
      return (
        <FileUploader
          file={file}
          onFileChange={memory.onFileChosen}
          memory={{
            remember: memory.remember,
            status: memory.status,
            onRememberChange: memory.setRemember,
            onForget: memory.forget,
          }}
        />
      )
    }
    render(<Harness />)

    const checkbox = screen.getByRole('checkbox', { name: 'Recordar mi CV en este navegador' })
    expect(checkbox).not.toBeChecked()
    await user.click(checkbox)
    expect(await screen.findByText('Guardado en este navegador')).toBeInTheDocument()
    expect((await loadCv())?.name).toBe('mi-cv.pdf')

    await user.click(screen.getByRole('button', { name: 'Olvidar memoria local' }))
    expect(checkbox).not.toBeChecked()
    await waitFor(async () => expect(await loadCv()).toBeNull())
  })
})

describe('nivel de ajuste', () => {
  it('se envía al backend con el formulario', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }))
    await optimizeCv({
      file: new File(['%PDF'], 'cv.pdf', { type: 'application/pdf' }),
      jobOffer: 'oferta',
      language: 'es',
      adjustment: 'subtle',
    })
    const body = fetchMock.mock.calls[0][1]?.body as FormData
    expect(body.get('adjustment_level')).toBe('subtle')
  })
})

const RESULT: OptimizeResponse = {
  request_id: 'req-v16',
  optimized_markdown: '# Ana García\n\n## Experiencia\n- APIs con FastAPI\n\n## Habilidades\n- Python\n- FastAPI',
  application_pitch: 'Desarrolladora backend con Python.\n\n- APIs con FastAPI.\n- Python.\n- Despliegues.',
  match: { score_before: 50, score_after: 50, matched_keywords: ['Python', 'FastAPI'], missing_keywords: ['Kubernetes', 'Inglés C1'], soft_skills: [] },
  gaps: ['Kubernetes', 'Inglés C1 (el CV indica B2)'],
  changes_summary: [],
  warnings: [],
  changes: [],
  ats_suggestions: ['Kubernetes'],
  quality: 'ok',
  meta: {
    mode: 'server',
    provider: 'groq',
    model: 'openai/gpt-oss-120b',
    prompt_version: 'v5',
    latency_ms: 3000,
    tokens: { input: 1000, output: 500 },
    pdf_pages: 1,
  },
}

describe('pitch de candidatura', () => {
  it('tiene su propia pestaña con botón de copiar', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    render(<ResultViewer result={RESULT} onReset={() => {}} />)

    await user.click(screen.getByRole('tab', { name: /pitch para la oferta/i }))
    expect(screen.getByText('Desarrolladora backend con Python.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Copiar pitch' }))
    expect(writeText).toHaveBeenCalledWith(RESULT.application_pitch)
  })

  it('no muestra la pestaña si el modelo no generó pitch', () => {
    render(<ResultViewer result={{ ...RESULT, application_pitch: '' }} onReset={() => {}} />)
    expect(screen.queryByRole('tab', { name: /pitch/i })).toBeNull()
  })
})

describe('experiencia en los requisitos que faltan', () => {
  it('añade la experiencia al CV, recalcula la puntuación y quita el requisito', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    render(<ResultViewer result={RESULT} onReset={() => {}} />)

    const gaps = screen.getByRole('list', { name: 'Requisitos que no están en tu CV' })
    await user.click(screen.getAllByRole('button', { name: 'Sí tengo experiencia en esto' })[0])
    await user.type(screen.getByLabelText('Tu experiencia con Kubernetes'), 'Lo usé para desplegar microservicios')
    await user.click(screen.getByRole('button', { name: 'Añadir al CV' }))

    expect(gaps).not.toHaveTextContent('Kubernetes')
    // La sugerencia ATS equivalente también desaparece: ya está en el CV.
    expect(screen.queryByRole('button', { name: 'Añadir Kubernetes al CV' })).toBeNull()
    expect(document.querySelector('mark[data-kind="added"]')).toHaveTextContent(
      'Kubernetes: Lo usé para desplegar microservicios',
    )
    expect(screen.getByText('75%')).toBeInTheDocument() // 3 de 4 palabras clave

    await user.click(screen.getByRole('button', { name: /copiar al portapapeles/i }))
    expect(writeText.mock.calls[0][0]).toContain('- Kubernetes: Lo usé para desplegar microservicios')

    await user.click(screen.getByRole('button', { name: 'Quitar del CV: Kubernetes' }))
    expect(gaps).toHaveTextContent('Kubernetes')
    expect(screen.queryByText('75%')).toBeNull() // vuelve a 2 de 4
  })

  it('pide al menos una frase antes de añadir', async () => {
    const user = userEvent.setup()
    render(<ResultViewer result={RESULT} onReset={() => {}} />)
    await user.click(screen.getAllByRole('button', { name: 'Sí tengo experiencia en esto' })[1])
    await user.type(screen.getByLabelText('Tu experiencia con Inglés C1 (el CV indica B2)'), 'Sí')
    expect(screen.getByRole('button', { name: 'Añadir al CV' })).toBeDisabled()
  })
})

describe('injectExperience', () => {
  it('usa una viñeta propia aunque las habilidades vayan separadas por comas', () => {
    const md = '## Habilidades\nExcel, Word'
    expect(injectExperience(md, 'SAP (valorable)', 'Lo usé en facturación.')).toBe(
      '## Habilidades\nExcel, Word\n\n- SAP: Lo usé en facturación',
    )
  })
})
