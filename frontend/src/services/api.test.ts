import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, optimizeCv, validateApiKey } from './api'

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const pdf = new File(['%PDF-1.4'], 'cv.pdf', { type: 'application/pdf' })

afterEach(() => vi.unstubAllGlobals())

describe('optimizeCv', () => {
  it('envía el PDF y la oferta como multipart, sin clave en modo gratuito', async () => {
    const fetchMock = mockFetch(200, { optimized_markdown: '# CV' })

    await optimizeCv({ file: pdf, jobOffer: 'oferta', language: 'es' })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/v1\/optimize$/)
    const form = init.body as FormData
    expect((form.get('cv_file') as File).name).toBe('cv.pdf')
    expect(form.get('job_offer')).toBe('oferta')
    expect(form.get('output_language')).toBe('es')
    expect(init.headers).toEqual({})
  })

  it('envía la clave BYOK solo en la cabecera', async () => {
    const fetchMock = mockFetch(200, {})

    await optimizeCv({ file: pdf, jobOffer: 'oferta', language: 'auto', apiKey: 'gsk_test' })

    const [url, init] = fetchMock.mock.calls[0]
    expect(init.headers).toEqual({ 'X-User-API-Key': 'gsk_test', 'X-LLM-Provider': 'groq' })
    expect(url).not.toContain('gsk_test')
    expect([...(init.body as FormData).values()]).not.toContain('gsk_test')
  })

  it('convierte los errores del backend en ApiError', async () => {
    mockFetch(422, { error: { code: 'PDF_NO_TEXT', message: 'PDF escaneado', request_id: 'abc' } })

    const error = await optimizeCv({ file: pdf, jobOffer: 'x', language: 'auto' }).catch((e) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ code: 'PDF_NO_TEXT', message: 'PDF escaneado', status: 422, requestId: 'abc' })
  })

  it('informa de errores de red', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const error = await optimizeCv({ file: pdf, jobOffer: 'x', language: 'auto' }).catch((e) => e)

    expect(error).toMatchObject({ code: 'NETWORK_ERROR' })
  })
})

describe('validateApiKey', () => {
  it('llama al endpoint de validación con la clave en la cabecera', async () => {
    const fetchMock = mockFetch(200, { valid: true, provider: 'groq' })

    await expect(validateApiKey('gsk_test')).resolves.toEqual({ valid: true, provider: 'groq' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/v1\/keys\/validate$/)
    expect(init.method).toBe('POST')
    expect(init.headers['X-User-API-Key']).toBe('gsk_test')
  })
})
