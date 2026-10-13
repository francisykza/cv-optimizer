// Espejo de los esquemas Pydantic del backend (backend/app/schemas/optimize.py).

export type OutputLanguage = 'auto' | 'es' | 'en'

export interface MatchReport {
  score_before: number
  score_after: number
  matched_keywords: string[]
  missing_keywords: string[]
}

export interface OptimizeMeta {
  mode: 'server' | 'byok'
  provider: string
  model: string
  prompt_version: string
  latency_ms: number
  tokens: { input: number; output: number }
  pdf_pages: number
}

export type WarningCode =
  | 'UNGROUNDED_DATE'
  | 'UNGROUNDED_METRIC'
  | 'UNGROUNDED_ENTITY'
  | 'UNGROUNDED_SKILL'
  | 'GAP_LEAKED'
  | 'FORMAT'
  | 'LIMITED_CHECK'

export interface ValidationWarning {
  code: WarningCode
  message: string
  term: string | null
  snippet: string | null
}

export interface OptimizeResponse {
  request_id: string | null
  optimized_markdown: string
  match: MatchReport
  gaps: string[]
  changes_summary: string[]
  warnings: ValidationWarning[]
  /** Expresiones reformuladas respecto al CV original (se resaltan en verde en la vista previa). */
  changes: string[]
  quality: 'ok' | 'needs_review'
  meta: OptimizeMeta
}

/** Avisos que señalan datos no respaldados por el CV original (se resaltan en la vista previa). */
export const UNGROUNDED_CODES: ReadonlySet<WarningCode> = new Set([
  'UNGROUNDED_DATE',
  'UNGROUNDED_METRIC',
  'UNGROUNDED_ENTITY',
  'UNGROUNDED_SKILL',
  'GAP_LEAKED',
])

export interface KeyValidationResponse {
  valid: boolean
  provider: string
}

export interface HealthResponse {
  status: 'ok'
  version: string
  server_llm_available: boolean
}

export interface ApiErrorBody {
  error: { code: string; message: string; request_id?: string | null }
}
