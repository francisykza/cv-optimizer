import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PASTE_MAX_CHARS } from '../lib/pasteText'
import { JobDescription } from './JobDescription'

const recognize = vi.fn()
vi.mock('tesseract.js', () => ({
  createWorker: vi.fn(async (_langs: unknown, _oem: unknown, options: { logger: (m: unknown) => void }) => {
    options.logger({ status: 'recognizing text', progress: 0.5 })
    return { recognize, terminate: vi.fn() }
  }),
}))

const OFFER = 'Buscamos auxiliar administrativo. Requisitos: Excel, contabilidad y facturación.'

function Harness({ initial = '', onBusyChange }: { initial?: string; onBusyChange?: (b: boolean) => void }) {
  const [value, setValue] = useState(initial)
  return (
    <JobDescription
      value={value}
      onChange={setValue}
      language="auto"
      onLanguageChange={() => {}}
      onBusyChange={onBusyChange}
    />
  )
}

const textarea = () => screen.getByLabelText('Texto de la oferta de empleo') as HTMLTextAreaElement

function paste(data: { text?: string; files?: File[] }) {
  const items = (data.files ?? []).map((file) => ({ kind: 'file', type: file.type, getAsFile: () => file }))
  return fireEvent.paste(textarea(), {
    clipboardData: { getData: (type: string) => (type === 'text/plain' ? (data.text ?? '') : ''), items },
  })
}

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  )
}

afterEach(() => {
  vi.restoreAllMocks()
  recognize.mockReset()
})

describe('JobDescription: textarea inteligente', () => {
  it('lee la oferta al pegar un enlace', async () => {
    let respond: (r: Response) => void = () => {}
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise((resolve) => (respond = resolve)))
    const onBusyChange = vi.fn()
    render(<Harness onBusyChange={onBusyChange} />)

    paste({ text: 'https://empleo.example.com/oferta/1' })

    expect(await screen.findByText('Leyendo la oferta desde el enlace…')).toBeInTheDocument()
    expect(textarea()).toHaveAttribute('readonly')
    respond(new Response(JSON.stringify({ text: OFFER }), { status: 200 }))
    await waitFor(() => expect(textarea().value).toBe(OFFER))
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/v1\/extract-job-url$/)
    expect(JSON.parse(String(init?.body))).toEqual({ url: 'https://empleo.example.com/oferta/1' })
    expect(onBusyChange).toHaveBeenCalledWith(true)
    expect(onBusyChange).toHaveBeenLastCalledWith(false)
  })

  it('explica qué hacer si el portal bloquea el enlace', async () => {
    const message =
      'Este portal bloquea enlaces directos. Entra en la oferta, pulsa Ctrl+A para copiar todo o pega aquí una captura de pantalla con Ctrl+V.'
    mockFetch(422, { error: { code: 'JOB_URL_UNREADABLE', message } })
    render(<Harness />)

    paste({ text: 'https://www.linkedin.com/jobs/view/1' })

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(textarea().value).toBe('')
  })

  it('reconoce el texto de una captura y lo añade al final', async () => {
    recognize.mockResolvedValue({ data: { text: 'Requisitos:\n\n\n\n- Excel   avanzado' } })
    render(<Harness initial="Primera captura" />)

    paste({ files: [new File(['png'], 'captura.png', { type: 'image/png' })] })

    await waitFor(() => expect(textarea().value).toBe('Primera captura\n\nRequisitos:\n\n- Excel avanzado'))
    expect(recognize).toHaveBeenCalledTimes(1)
  })

  it('si el portapapeles trae texto e imagen (Word, Excel), usa el texto', () => {
    render(<Harness />)

    paste({ text: OFFER, files: [new File(['png'], 'tabla.png', { type: 'image/png' })] })

    expect(recognize).not.toHaveBeenCalled()
  })

  it('limpia el texto copiado con Ctrl+A y lo limita para proteger los tokens', () => {
    render(<Harness />)

    paste({ text: `Menú\t\tInicio\n\n\n\n${'x'.repeat(PASTE_MAX_CHARS)}` })

    expect(textarea().value.startsWith('Menú Inicio\n\nxxx')).toBe(true)
    expect(textarea().value).toHaveLength(PASTE_MAX_CHARS)
    expect(screen.getByRole('status')).toHaveTextContent(/recortado la oferta/)
  })
})
