import { API_BASE_URL } from '../lib/constants'
import type {
  AdjustmentLevel,
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

// Cualquier respuesta del backend (aunque sea un error 4xx de validación) demuestra que está vivo.
// El indicador de la cabecera se suscribe para no quedarse en "no disponible" cuando la app ya
// está funcionando (p. ej. tras un arranque en frío de Render más largo de lo previsto).
const reachableListeners = new Set<() => void>()

export function onServerReachable(listener: () => void): () => void {
  reachableListeners.add(listener)
  return () => reachableListeners.delete(listener)
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

  reachableListeners.forEach((listener) => listener())
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

export function checkHealth(signal?: AbortSignal, timeoutMs = 15_000): Promise<HealthResponse> {
  return request<HealthResponse>('/health', { signal, timeoutMs })
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
  adjustment?: AdjustmentLevel
  apiKey?: string
  signal?: AbortSignal
}

export function optimizeCv({
  file,
  jobOffer,
  language,
  adjustment = 'deep',
  apiKey,
  signal,
}: OptimizeParams): Promise<OptimizeResponse> {
  const form = new FormData()
  form.append('cv_file', file, file.name)
  form.append('job_offer', jobOffer)
  form.append('output_language', language)
  form.append('adjustment_level', adjustment)

  return request<OptimizeResponse>('/api/v1/optimize', {
    method: 'POST',
    body: form,
    headers: byokHeaders(apiKey),
    signal,
    timeoutMs: OPTIMIZE_TIMEOUT_MS,
  })
}

/** Margen para el arranque en frío de Render; Jina tiene a su vez 8 s en el backend. */
const JOB_URL_TIMEOUT_MS = 30_000

/** Texto de una oferta a partir de su enlace. Si el portal lo bloquea, el backend responde 422
 *  `JOB_URL_UNREADABLE` con instrucciones para copiar el texto o pegar una captura. */
export async function extractJobUrl(url: string, signal?: AbortSignal): Promise<string> {
  const body = await request<{ text: string }>('/api/v1/extract-job-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
    signal,
    timeoutMs: JOB_URL_TIMEOUT_MS,
  })
  return body.text
}
