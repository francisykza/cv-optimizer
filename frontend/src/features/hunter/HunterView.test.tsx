import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { consumeHandoff } from '../../lib/handoff'
import { HunterError, hunterApi, normalizeJob, tokenStore } from './hunterClient'
import HunterView from './HunterView'
import type { JobItem } from './types'

const LONG = 'Junior AI Engineer — Acme (Málaga, híbrido)\n\n' + 'Python, LLM y RAG con mentoría semanal. '.repeat(8)

function job(overrides: Partial<JobItem> = {}): JobItem {
  return {
    id: 'job-1',
    title: 'Junior AI Engineer',
    company: 'Acme Labs',
    location: 'Málaga',
    modality: 'hybrid',
    stage: 'judged',
    app_status: 'none',
    rank_score: 82,
    prescore: 60,
    first_seen: '2026-10-15T08:00:00+00:00',
    times_seen: 1,
    days_published: 1,
    sources: [{ site: 'linkedin', url: 'https://www.linkedin.com/jobs/view/1' }],
    verdict: {
      match_score: 86,
      verdict: 'apply',
      summary: 'Encaja por Python y RAG, con mentoría.',
      green_flags: [{ text: 'Mentoría semanal', evidence: 'mentoría semanal con un senior', evidence_verified: true }],
      red_flags: [{ text: 'Salario sin publicar', evidence: '', evidence_verified: false }],
      stack_core: ['Python', 'RAG'],
      stack_inflated: ['Kubernetes'],
      missing_must_haves: [],
      seniority_detected: 'junior',
      seniority_fit: 'fit',
    },
    judge_status: 'ok',
    judge_error: null,
    guillotine: null,
    ...overrides,
  }
}

const health = {
  status: 'ok',
  version: '0.3.0',
  db_ok: true,
  groq_key_configured: true,
  token_configured: true,
  last_run: null,
} as const

beforeEach(() => {
  vi.spyOn(hunterApi, 'health').mockResolvedValue(health)
  vi.spyOn(hunterApi, 'runs').mockResolvedValue([])
  vi.spyOn(hunterApi, 'jobs').mockResolvedValue({ items: [job()], total: 1, next_cursor: null })
})

afterEach(() => {
  vi.restoreAllMocks()
  window.location.hash = ''
})

describe('HunterView', () => {
  it('explica cómo arrancar la API si no responde', async () => {
    vi.mocked(hunterApi.health).mockRejectedValue(new HunterError('OFFLINE', 'no', 0))
    render(<HunterView />)
    expect(await screen.findByRole('heading', { name: 'La API local no está arrancada' })).toBeInTheDocument()
    expect(screen.getByText(/python -m hunter serve/)).toBeInTheDocument()
  })

  it('pide el token y, con él, muestra el ranking', async () => {
    const user = userEvent.setup()
    render(<HunterView />)
    await user.type(await screen.findByLabelText('Token local'), 'mi-token')
    await user.click(screen.getByRole('button', { name: 'Conectar' }))

    const card = await screen.findByRole('article', { name: 'Junior AI Engineer' })
    expect(within(card).getByText('86')).toBeInTheDocument()
    expect(within(card).getByText('Encaja por Python y RAG, con mentoría.')).toBeInTheDocument()
    expect(within(card).getByText('Salario sin publicar')).toHaveClass('marker-amber')
    expect(within(card).getByText('Mentoría semanal')).toHaveClass('marker-green')
    expect(hunterApi.jobs).toHaveBeenCalledWith('mi-token', expect.objectContaining({ view: 'ranked' }))
    expect(tokenStore.get()).toBe('mi-token')
  })

  it('un token rechazado vuelve a pedirlo con el motivo', async () => {
    tokenStore.set('viejo', false)
    vi.mocked(hunterApi.jobs).mockRejectedValue(new HunterError('HUNTER_TOKEN_INVALID', 'no', 401))
    render(<HunterView />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Ese token no coincide')
    expect(tokenStore.get()).toBe('')
  })

  it('el detalle muestra las citas y marca las no verificables', async () => {
    tokenStore.set('t', false)
    const user = userEvent.setup()
    render(<HunterView />)
    const card = await screen.findByRole('article', { name: 'Junior AI Engineer' })
    await user.click(within(card).getByRole('button', { name: 'Más detalle' }))
    expect(within(card).getByText('«mentoría semanal con un senior»')).toBeInTheDocument()
    expect(within(card).getByText('Kubernetes')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: /Ver en LinkedIn/ })).toHaveAttribute(
      'href',
      'https://www.linkedin.com/jobs/view/1',
    )
  })

  it('"Enviar al Optimizador" deja la oferta preparada y cambia de vista', async () => {
    tokenStore.set('t', false)
    vi.spyOn(hunterApi, 'handoff').mockResolvedValue({
      version: 1,
      text: LONG,
      chars: LONG.length,
      title: 'Junior AI Engineer',
      company: 'Acme Labs',
      source_url: 'https://www.linkedin.com/jobs/view/1',
      language: 'es',
      complete: true,
    })
    const user = userEvent.setup()
    render(<HunterView />)
    await user.click(await screen.findByRole('button', { name: 'Enviar al Optimizador' }))
    await waitFor(() => expect(window.location.hash).toBe('#/optimizar'))
    expect(consumeHandoff()).toMatchObject({ company: 'Acme Labs', text: LONG, language: 'es' })
  })

  it('no envía un extracto: avisa y se queda', async () => {
    tokenStore.set('t', false)
    vi.spyOn(hunterApi, 'handoff').mockResolvedValue({
      version: 1,
      text: 'corto',
      chars: 5,
      title: 'x',
      company: 'Acme',
      source_url: null,
      language: null,
      complete: false,
    })
    const user = userEvent.setup()
    render(<HunterView />)
    await user.click(await screen.findByRole('button', { name: 'Enviar al Optimizador' }))
    await waitFor(() => expect(hunterApi.handoff).toHaveBeenCalled())
    expect(window.location.hash).not.toBe('#/optimizar')
    expect(consumeHandoff()).toBeNull()
  })

  it('"No me interesa" actualiza la ficha', async () => {
    tokenStore.set('t', false)
    vi.spyOn(hunterApi, 'setStatus').mockResolvedValue(job({ app_status: 'dismissed' }))
    const user = userEvent.setup()
    render(<HunterView />)
    await user.click(await screen.findByRole('button', { name: 'No me interesa' }))
    expect(await screen.findByText('Descartada por ti')).toBeInTheDocument()
    expect(hunterApi.setStatus).toHaveBeenCalledWith('t', 'job-1', 'dismissed')
  })

  it('las descartadas explican la regla', async () => {
    tokenStore.set('t', false)
    vi.mocked(hunterApi.jobs).mockImplementation(async (_t, params) =>
      params.view === 'discarded'
        ? {
            items: [
              job({
                stage: 'discarded',
                verdict: null,
                judge_status: 'discarded',
                guillotine: {
                  rule_id: 'SEN_TITLE',
                  rule_label: 'Nivel excluido en el título: «senior»',
                  matched_text: 'Senior AI Engineer',
                },
              }),
            ],
            total: 1,
            next_cursor: null,
          }
        : { items: [], total: 0, next_cursor: null },
    )
    const user = userEvent.setup()
    render(<HunterView />)
    await user.click(await screen.findByRole('tab', { name: /Descartadas/ }))
    expect(await screen.findByText('Nivel excluido en el título: «senior»')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Enviar al Optimizador' })).not.toBeInTheDocument()
  })
})

describe('normalizeJob', () => {
  it('convierte listas ausentes en listas vacías', () => {
    const raw = {
      ...job(),
      sources: null,
      verdict: { ...job().verdict!, red_flags: null, stack_core: undefined },
    } as unknown as JobItem
    const fixed = normalizeJob(raw)
    expect(fixed.sources).toEqual([])
    expect(fixed.verdict?.red_flags).toEqual([])
    expect(fixed.verdict?.stack_core).toEqual([])
  })
})
