import { API_BASE_URL } from '../lib/constants'
import type {
  ApiErrorBody,
  HealthResponse,
  KeyValidationResponse,
  OptimizeResponse,
  OutputLanguage,
} from '../types/api'

const OPTIMIZE_TIMEOUT_MS = 120_000

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly requestId?: string | null

  constructor(code: string, message: string, status: number, requestId?: string | null) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.requestId = requestId
  }
}

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const { timeoutMs = 15_000, signal, ...rest } = init
  const timeout = AbortSignal.timeout(timeoutMs)
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...rest, signal: combined })
  } catch (err) {
    if (signal?.aborted) throw new ApiError('ABORTED', 'Operación cancelada.', 0)
    if (timeout.aborted) {
      throw new ApiError('CLIENT_TIMEOUT', 'El servidor tardó demasiado en responder. Inténtalo de nuevo.', 0)
    }
    throw new ApiError(
      'NETWORK_ERROR',
      'No se pudo conectar con el servidor. Comprueba tu conexión o inténtalo en unos segundos.',
      0,
    )
  }

  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const error = (body as ApiErrorBody | null)?.error
    throw new ApiError(
      error?.code ?? 'HTTP_ERROR',
      error?.message ?? `Error inesperado del servidor (${response.status}).`,
      response.status,
      error?.request_id,
    )
  }
  return body as T
}

/** La clave BYOK viaja solo en una cabecera (nunca en la URL ni en el body). */
function byokHeaders(apiKey?: string): HeadersInit {
  return apiKey ? { 'X-User-API-Key': apiKey, 'X-LLM-Provider': 'groq' } : {}
}

export function checkHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/health', { signal, timeoutMs: 90_000 })
}

export function validateApiKey(apiKey: string): Promise<KeyValidationResponse> {
  return request<KeyValidationResponse>('/api/v1/keys/validate', {
    method: 'POST',
    headers: byokHeaders(apiKey),
  })
}

export interface OptimizeParams {
  file: File
  jobOffer: string
  language: OutputLanguage
  apiKey?: string
  signal?: AbortSignal
}

export function optimizeCv({ file, jobOffer, language, apiKey, signal }: OptimizeParams): Promise<OptimizeResponse> {
  const form = new FormData()
  form.append('cv_file', file, file.name)
  form.append('job_offer', jobOffer)
  form.append('output_language', language)

  return request<OptimizeResponse>('/api/v1/optimize', {
    method: 'POST',
    body: form,
    headers: byokHeaders(apiKey),
    signal,
    timeoutMs: OPTIMIZE_TIMEOUT_MS,
  })
}
