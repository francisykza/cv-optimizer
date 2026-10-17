import type {
  ApplicationDetail,
  ApplicationEvent,
  ApplicationInput,
  ApplicationItem,
  ApplicationsPage,
  ApplicationStatus,
  ApplicationUpdate,
  AppStatus,
  GoldenRules,
  Handoff,
  Health,
  JobItem,
  JobsPage,
  JobsView,
  JobVerdict,
  OutdatedVerdicts,
  Profile,
  ProfileDraft,
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
  /** Cuerpo tal cual (un PDF), con su tipo. */
  file?: Blob
  token?: string
  signal?: AbortSignal
  timeoutMs?: number
}

async function request<T>(
  path: string,
  { method = 'GET', body, file, token, signal, timeoutMs = 15_000 }: RequestOptions = {},
): Promise<T> {
  const timeout = AbortSignal.timeout(timeoutMs)
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout
  const headers: Record<string, string> = {}
  if (token) headers['X-Hunter-Token'] = token
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (file) headers['Content-Type'] = file.type || 'application/pdf'

  let response: Response
  try {
    response = await fetch(`${HUNTER_URL}${path}`, {
      method,
      headers,
      body: file ?? (body === undefined ? undefined : JSON.stringify(body)),
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

export function normalizeApplication<T extends ApplicationItem>(item: T): T {
  return { ...item, notes: item.notes ?? '', events: list<ApplicationEvent>(item.events) }
}

const NO_OUTDATED: OutdatedVerdicts = {
  count: 0,
  from_cache: 0,
  days: 7,
  est_tokens: 0,
  est_minutes: 0,
  tokens_left_today: null,
}

export function normalizeProfile(profile: Profile): Profile {
  return {
    ...profile,
    text: profile.text ?? '',
    terms: list<string>(profile.terms),
    previous_text: profile.previous_text ?? null,
    outdated: { ...NO_OUTDATED, ...(profile.outdated ?? {}) },
  }
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

  profile: async (token: string) => normalizeProfile(await request<Profile>('/api/v1/profile', { token })),

  /** `baseSha256`: la huella del perfil que se editó. Si el archivo cambió fuera de la web: 409 PROFILE_CHANGED. */
  saveProfile: async (token: string, text: string, baseSha256: string) =>
    normalizeProfile(
      await request<Profile>('/api/v1/profile', { method: 'PUT', token, body: { text, base_sha256: baseSha256 } }),
    ),

  /** Borrador del perfil a partir del CV en PDF: lo lee la API local, sin IA y sin guardar nada. */
  profileDraft: async (token: string, pdf: Blob) => {
    const draft = await request<ProfileDraft>('/api/v1/profile/draft', {
      method: 'POST',
      token,
      file: pdf,
      timeoutMs: 30_000,
    })
    return { ...draft, sections: list<string>(draft.sections), warnings: list<string>(draft.warnings) }
  },

  /** Canjea el código de un solo uso del lanzador por el token (SPEC §18.2). */
  pair: (code: string) => request<{ token: string }>('/api/v1/pair', { method: 'POST', body: { code } }),

  shutdown: (token: string) => request<{ status: 'stopping' }>('/api/v1/shutdown', { method: 'POST', token }),

  applications: async (token: string, params: { status?: ApplicationStatus; q?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.status) query.set('status', params.status)
    if (params.q) query.set('q', params.q)
    const page = await request<ApplicationsPage>(`/api/v1/applications?${query}`, { token })
    return { ...page, items: list<ApplicationItem>(page.items).map(normalizeApplication) }
  },

  application: async (token: string, id: string) =>
    normalizeApplication(await request<ApplicationDetail>(`/api/v1/applications/${encodeURIComponent(id)}`, { token })),

  createApplication: async (token: string, input: ApplicationInput) =>
    normalizeApplication(
      await request<ApplicationDetail>('/api/v1/applications', { method: 'POST', token, body: input }),
    ),

  updateApplication: async (token: string, id: string, changes: ApplicationUpdate) =>
    normalizeApplication(
      await request<ApplicationItem>(`/api/v1/applications/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        token,
        body: changes,
      }),
    ),

  deleteApplication: (token: string, id: string) =>
    request<null>(`/api/v1/applications/${encodeURIComponent(id)}`, { method: 'DELETE', token }),

  /** CSV para Excel (separador `;`, BOM). Sin JSON: se descarga tal cual. */
  exportApplications: async (token: string): Promise<Blob> => {
    let response: Response
    try {
      response = await fetch(`${HUNTER_URL}/api/v1/applications.csv`, {
        headers: { 'X-Hunter-Token': token },
        signal: AbortSignal.timeout(15_000),
      })
    } catch {
      throw new HunterError('OFFLINE', 'La API local no responde.', 0)
    }
    if (!response.ok) throw new HunterError('HTTP_ERROR', 'No se pudo exportar.', response.status)
    return response.blob()
  },
}
