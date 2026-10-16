import type {
  AppStatus,
  GoldenRules,
  Handoff,
  Health,
  JobItem,
  JobsPage,
  JobsView,
  JobVerdict,
  RulesResponse,
  RulesSaved,
  Run,
  RunMode,
  SimulationReport,
  SourceHealth,
  SourceRun,
} from './types'

export const HUNTER_URL = (import.meta.env.VITE_HUNTER_URL ?? 'http://127.0.0.1:8001').replace(/\/$/, '')

export class HunterError extends Error {
  readonly code: string
  readonly status: number
  readonly details?: { path: string; message: string }[]

  constructor(code: string, message: string, status: number, details?: { path: string; message: string }[]) {
    super(message)
    this.name = 'HunterError'
    this.code = code
    this.status = status
    this.details = details
  }
}

const TOKEN_KEY = 'cvopt:hunter-token'

/** El token vive en sessionStorage; con "recordar", también en localStorage (es un equipo propio). */
export const tokenStore = {
  get(): string {
    try {
      return sessionStorage.getItem(TOKEN_KEY) ?? localStorage.getItem(TOKEN_KEY) ?? ''
    } catch {
      return ''
    }
  },
  set(token: string, remember: boolean): void {
    try {
      sessionStorage.setItem(TOKEN_KEY, token)
      if (remember) localStorage.setItem(TOKEN_KEY, token)
      else localStorage.removeItem(TOKEN_KEY)
    } catch {
      // Almacenamiento bloqueado: el token dura lo que dure la pestaña.
    }
  },
  clear(): void {
    try {
      sessionStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(TOKEN_KEY)
    } catch {
      // Nada que limpiar.
    }
  },
}

interface RequestOptions {
  method?: string
  body?: unknown
  token?: string
  signal?: AbortSignal
  timeoutMs?: number
}

async function request<T>(
  path: string,
  { method = 'GET', body, token, signal, timeoutMs = 15_000 }: RequestOptions = {},
): Promise<T> {
  const timeout = AbortSignal.timeout(timeoutMs)
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout
  const headers: Record<string, string> = {}
  if (token) headers['X-Hunter-Token'] = token
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(`${HUNTER_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: combined,
    })
  } catch {
    if (signal?.aborted) throw new HunterError('ABORTED', 'Operación cancelada.', 0)
    if (timeout.aborted) throw new HunterError('CLIENT_TIMEOUT', 'La API local tardó demasiado en responder.', 0)
    throw new HunterError('OFFLINE', 'La API local no responde. Arráncala con `python -m hunter serve`.', 0)
  }
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const error = (
      data as { error?: { code?: string; message?: string; details?: { path: string; message: string }[] } } | null
    )?.error
    throw new HunterError(
      error?.code ?? 'HTTP_ERROR',
      error?.message ?? `Error ${response.status}`,
      response.status,
      error?.details,
    )
  }
  return data as T
}

// --- Normalización defensiva: la UI nunca recibe null donde espera una lista ------------------

const list = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : [])

function normalizeVerdict(v: JobVerdict | null | undefined): JobVerdict | null {
  if (!v || typeof v.match_score !== 'number') return null
  return {
    ...v,
    summary: v.summary ?? '',
    green_flags: list(v.green_flags),
    red_flags: list(v.red_flags),
    stack_core: list(v.stack_core),
    stack_inflated: list(v.stack_inflated),
    missing_must_haves: list(v.missing_must_haves),
  }
}

export function normalizeJob(job: JobItem): JobItem {
  return { ...job, sources: list(job.sources), verdict: normalizeVerdict(job.verdict) }
}

// --- Endpoints -----------------------------------------------------------------------------------

export const hunterApi = {
  health: (signal?: AbortSignal) => request<Health>('/health', { signal, timeoutMs: 4000 }),

  jobs: async (
    token: string,
    params: { view: JobsView; q?: string; cursor?: string | null; minScore?: number },
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({ view: params.view, limit: '30' })
    if (params.q) query.set('q', params.q)
    if (params.cursor) query.set('cursor', params.cursor)
    if (params.minScore !== undefined) query.set('min_score', String(params.minScore))
    const page = await request<JobsPage>(`/api/v1/jobs?${query}`, { token, signal })
    return { ...page, items: list<JobItem>(page.items).map(normalizeJob) }
  },

  setStatus: async (token: string, id: string, appStatus: AppStatus) =>
    normalizeJob(
      await request<JobItem>(`/api/v1/jobs/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        token,
        body: { app_status: appStatus },
      }),
    ),

  rejudge: async (token: string, id: string) =>
    normalizeJob(
      await request<JobItem>(`/api/v1/jobs/${encodeURIComponent(id)}/rejudge`, {
        method: 'POST',
        token,
        timeoutMs: 120_000,
      }),
    ),

  handoff: (token: string, id: string) =>
    request<Handoff>(`/api/v1/jobs/${encodeURIComponent(id)}/handoff`, { method: 'POST', token, timeoutMs: 20_000 }),

  startRun: (token: string, mode: RunMode = 'full') =>
    request<{ run_id: string; status: 'running' }>('/api/v1/runs', { method: 'POST', token, body: { mode } }),

  run: async (token: string, id: string, signal?: AbortSignal) => {
    const run = await request<Run>(`/api/v1/runs/${encodeURIComponent(id)}`, { token, signal })
    return { ...run, sources: list<SourceRun>(run.sources) }
  },

  runs: async (token: string) => list<Run>((await request<{ items: Run[] }>('/api/v1/runs?limit=1', { token })).items),

  sources: async (token: string) => list<SourceHealth>(await request<SourceHealth[]>('/api/v1/sources', { token })),

  rules: (token: string) => request<RulesResponse>('/api/v1/rules', { token }),

  simulate: (token: string, rules: GoldenRules) =>
    request<SimulationReport>('/api/v1/rules/simulate', { method: 'POST', token, body: { rules, window_days: 7 } }),

  saveRules: (token: string, rules: GoldenRules) =>
    request<RulesSaved>('/api/v1/rules', { method: 'PUT', token, body: { rules } }),
}
