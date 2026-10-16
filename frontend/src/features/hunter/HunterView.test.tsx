import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { consumeHandoff } from '../../lib/handoff'
import { outbox } from './applications'
import { HunterError, hunterApi, normalizeJob, tokenStore } from './hunterClient'
import HunterView from './HunterView'
import type { ApplicationItem, ApplicationsPage, JobItem, Run } from './types'

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
  localStorage.clear()
  sessionStorage.clear()
})

function application(overrides: Partial<ApplicationItem> = {}): ApplicationItem {
  return {
    id: 'app-1',
    job_id: 'job-1',
    company: 'Acme Labs',
    title: 'Junior AI Engineer',
    url: 'https://www.linkedin.com/jobs/view/1',
    location: 'Málaga',
    source: 'optimizer',
    status: 'applied',
    applied_at: '2026-10-12T10:00:00+00:00',
    status_changed_at: '2026-10-12T10:00:00+00:00',
    ats_score_before: 54,
    ats_score_after: 86,
    judge_score: 82,
    notes: '',
    has_offer_text: true,
    has_cv: true,
    events: [{ status: 'applied', at: '2026-10-12T10:00:00+00:00' }],
    stale: false,
    ...overrides,
  }
}

const applicationsPage = (items: ApplicationItem[]): ApplicationsPage => ({
  items,
  total: items.length,
  stats: {
    total: items.length,
    last_7_days: items.length,
    awaiting: items.length,
    responded: 0,
    interviews: 0,
    offers: 0,
    stale: 0,
    avg_ats_after: 86,
    by_band: [],
  },
})

describe('HunterView', () => {
  it('si la API está apagada, manda al acceso directo del escritorio', async () => {
    vi.mocked(hunterApi.health).mockRejectedValue(new HunterError('OFFLINE', 'no', 0))
    render(<HunterView />)
    expect(await screen.findByRole('heading', { name: 'La API local está apagada' })).toBeInTheDocument()
    expect(screen.getByText('Buscador de empleo')).toBeInTheDocument()
    expect(screen.getByText(/python -m hunter open/)).toBeInTheDocument()
  })

  it('se conecta sola con el código del acceso directo y lo quita de la dirección', async () => {
    window.location.hash = '#/buscar?pair=codigo-de-un-solo-uso'
    vi.spyOn(hunterApi, 'pair').mockResolvedValue({ token: 'token-emparejado' })
    render(<HunterView />)
    expect(await screen.findByRole('article', { name: 'Junior AI Engineer' })).toBeInTheDocument()
    expect(hunterApi.pair).toHaveBeenCalledWith('codigo-de-un-solo-uso')
    expect(hunterApi.jobs).toHaveBeenCalledWith('token-emparejado', expect.objectContaining({ view: 'ranked' }))
    expect(tokenStore.get()).toBe('token-emparejado')
    expect(window.location.hash).toBe('#/buscar')
  })

  it('un código caducado explica qué hacer', async () => {
    window.location.hash = '#/buscar?pair=viejo'
    vi.spyOn(hunterApi, 'pair').mockRejectedValue(
      new HunterError('PAIR_CODE_INVALID', 'El enlace de conexión ha caducado o ya se usó.', 401),
    )
    render(<HunterView />)
    expect(await screen.findByRole('alert')).toHaveTextContent('El enlace de conexión ha caducado')
    expect(screen.getByLabelText('Token local')).toBeInTheDocument()
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
    expect(consumeHandoff()).toMatchObject({
      company: 'Acme Labs',
      text: LONG,
      language: 'es',
      sourceUrl: 'https://www.linkedin.com/jobs/view/1',
      jobId: 'job-1',
      matchScore: 86,
      location: 'Málaga',
    })
  })

  it('"Ya me he inscrito" la apunta en Candidaturas con la nota del juez', async () => {
    tokenStore.set('t', false)
    vi.spyOn(hunterApi, 'createApplication').mockResolvedValue({
      ...application({ source: 'hunter' }),
      offer_text: null,
      cv_markdown: null,
    })
    const user = userEvent.setup()
    render(<HunterView />)
    await user.click(await screen.findByRole('button', { name: 'Ya me he inscrito' }))
    expect(await screen.findByText('Inscrito: está en tus candidaturas')).toBeInTheDocument()
    expect(hunterApi.createApplication).toHaveBeenCalledWith(
      't',
      expect.objectContaining({
        job_id: 'job-1',
        source: 'hunter',
        company: 'Acme Labs',
        title: 'Junior AI Engineer',
        url: 'https://www.linkedin.com/jobs/view/1',
        judge_score: 86,
      }),
    )
  })

  it('si la API no responde, la candidatura espera en el navegador', async () => {
    tokenStore.set('t', false)
    vi.spyOn(hunterApi, 'createApplication').mockRejectedValue(new HunterError('OFFLINE', 'no', 0))
    const user = userEvent.setup()
    render(<HunterView />)
    await user.click(await screen.findByRole('button', { name: 'Ya me he inscrito' }))
    await waitFor(() => expect(outbox.list()).toHaveLength(1))
    expect(outbox.list()[0]).toMatchObject({ job_id: 'job-1', company: 'Acme Labs' })
  })

  it('la pestaña Candidaturas enseña la compatibilidad y cambia el estado', async () => {
    tokenStore.set('t', false)
    const interview = application({
      status: 'interview',
      events: [
        { status: 'applied', at: '2026-10-12T10:00:00+00:00' },
        { status: 'interview', at: '2026-10-15T10:00:00+00:00' },
      ],
    })
    vi.spyOn(hunterApi, 'applications')
      .mockResolvedValueOnce(applicationsPage([application()]))
      .mockResolvedValue(applicationsPage([interview])) // tras el cambio se recarga el resumen
    vi.spyOn(hunterApi, 'updateApplication').mockResolvedValue(interview)
    const user = userEvent.setup()
    render(<HunterView />)
    await user.click(await screen.findByRole('tab', { name: 'Candidaturas' }))
    const card = await screen.findByRole('article', { name: 'Junior AI Engineer' })
    expect(within(card).getByText('86 %')).toHaveClass('marker-green')
    expect(within(card).getByText('antes 54 %')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: /Abrir la oferta/ })).toHaveAttribute(
      'href',
      'https://www.linkedin.com/jobs/view/1',
    )
    await user.selectOptions(within(card).getByLabelText('Estado de la candidatura'), 'interview')
    expect(hunterApi.updateApplication).toHaveBeenCalledWith('t', 'app-1', { status: 'interview' })
    expect(await within(card).findByText(/Entrevista 15 oct/)).toBeInTheDocument()
  })

  it('#/buscar/candidaturas abre directamente las candidaturas', async () => {
    tokenStore.set('t', false)
    window.location.hash = '#/buscar/candidaturas'
    vi.spyOn(hunterApi, 'applications').mockResolvedValue(applicationsPage([]))
    render(<HunterView />)
    expect(await screen.findByText(/Aún no has apuntado ninguna candidatura/)).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Candidaturas' })).toHaveAttribute('aria-selected', 'true')
  })

  it('enseña cuántas ofertas lleva puntuadas la IA en una búsqueda', async () => {
    tokenStore.set('t', false)
    const running: Run = {
      id: 'run-1',
      trigger: 'api',
      mode: 'full',
      status: 'running',
      started_at: '2026-10-16T08:00:00+00:00',
      finished_at: null,
      rules_version: 'x',
      counts: {
        fetched: 40,
        new: 6,
        duplicates: 30,
        discarded: 2,
        pending_judge: 4,
        judged: 1,
        judge_failed: 0,
        cache_hits: 0,
        judge_queue: 4,
      },
      tokens_used: 3000,
      budget_exhausted: false,
      sources: [],
      error: null,
    }
    vi.mocked(hunterApi.runs).mockResolvedValue([running])
    vi.spyOn(hunterApi, 'run').mockResolvedValue(running)
    render(<HunterView />)
    expect(await screen.findByText('La IA está puntuando las ofertas nuevas: 1 de 4.')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Ofertas puntuadas' })).toHaveAttribute('aria-valuenow', '1')
  })

  it('"Apagar ahora" apaga la API local', async () => {
    tokenStore.set('t', false)
    vi.mocked(hunterApi.health).mockResolvedValue({ ...health, auto_shutdown_minutes: 30 })
    vi.spyOn(hunterApi, 'shutdown').mockResolvedValue({ status: 'stopping' })
    const user = userEvent.setup()
    render(<HunterView />)
    expect(await screen.findByText(/se apaga sola 30 minutos después/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Apagar ahora' }))
    expect(await screen.findByRole('heading', { name: 'La API local está apagada' })).toBeInTheDocument()
    expect(hunterApi.shutdown).toHaveBeenCalledWith('t')
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
