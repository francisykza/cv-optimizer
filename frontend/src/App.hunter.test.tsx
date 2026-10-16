// Puente Buscador → Optimizador visto desde la app completa (SPEC del hunter §10.3).
import 'fake-indexeddb/auto'

import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { writeHandoff } from './lib/handoff'

const OFFER =
  'Junior AI Engineer — Acme Labs (Málaga, híbrido)\n\n' + 'Python, LLM y RAG con mentoría semanal. '.repeat(8)

beforeEach(() => {
  // Los tests no dependen de frontend/.env.local: el Buscador empieza desactivado.
  vi.stubEnv('VITE_HUNTER_ENABLED', 'false')
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok', version: '1', server_llm_available: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
  window.scrollTo = vi.fn()
  Element.prototype.scrollIntoView = vi.fn()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  window.location.hash = ''
})

describe('App y el Buscador', () => {
  it('rellena la oferta con la enviada desde el Buscador', async () => {
    writeHandoff({ text: OFFER, title: 'Junior AI Engineer', company: 'Acme Labs', language: 'es' })
    render(<App />)
    const textarea = await screen.findByLabelText('Texto de la oferta de empleo')
    await waitFor(() => expect(textarea).toHaveValue(OFFER.trim())) // pasa por el filtro de cookies, que recorta
    expect(await screen.findByText('Oferta de Acme Labs importada desde el Buscador')).toBeInTheDocument()
    expect(screen.getByLabelText('Idioma del CV')).toHaveValue('es')
  })

  it('sin el Buscador activado no hay pestañas y #/buscar muestra el Optimizador', async () => {
    window.location.hash = '#/buscar'
    render(<App />)
    expect(await screen.findByLabelText('Texto de la oferta de empleo')).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Secciones' })).not.toBeInTheDocument()
  })

  it('con el Buscador activado aparecen las pestañas', async () => {
    localStorage.setItem('cvopt:hunter', '1')
    render(<App />)
    const nav = await screen.findByRole('navigation', { name: 'Secciones' })
    expect(nav).toHaveTextContent('Optimizar CV')
    expect(nav).toHaveTextContent('Buscador')
    expect(screen.getByRole('link', { name: 'Optimizar CV' })).toHaveAttribute('aria-current', 'page')
  })

  it('la portada monta el campo de trazos sin canvas real (jsdom) y queda oculto a lectores de pantalla', async () => {
    render(<App />)
    await screen.findByLabelText('Texto de la oferta de empleo')
    const canvas = document.querySelector('canvas')
    expect(canvas).toHaveAttribute('aria-hidden', 'true')
    expect(canvas).toHaveClass('pointer-events-none')
  })
})
