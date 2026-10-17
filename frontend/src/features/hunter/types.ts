// Espejo de los contratos de la API local del Job Hunter (hunter/hunter/api/schemas.py, SPEC §8).

export type Modality = 'remote' | 'hybrid' | 'onsite' | 'unknown'
export type Stage = 'discarded' | 'pending_judge' | 'judged' | 'judge_failed'
export type AppStatus = 'none' | 'saved' | 'sent_to_optimizer' | 'applied' | 'dismissed'
export type JobsView = 'ranked' | 'pending' | 'discarded' | 'failed' | 'all'
export type Verdict = 'apply' | 'maybe' | 'skip'
export type RunStatus = 'running' | 'ok' | 'partial' | 'failed'
/** rejudge: vuelve a juzgar las ofertas cuya nota es de un perfil anterior (SPEC §19.3). */
export type RunMode = 'full' | 'ingest_only' | 'judge_only' | 'rejudge'

export interface Flag {
  text: string
  evidence: string
  evidence_verified: boolean
}

export interface JobVerdict {
  match_score: number
  verdict: Verdict
  summary: string
  green_flags: Flag[]
  red_flags: Flag[]
  stack_core: string[]
  stack_inflated: string[]
  missing_must_haves: string[]
  seniority_detected: 'intern' | 'junior' | 'mid' | 'senior' | 'lead' | 'unknown'
  seniority_fit: 'under' | 'fit' | 'over' | 'unknown'
}

export interface JobItem {
  id: string
  title: string
  company: string
  location: string
  modality: Modality
  stage: Stage
  app_status: AppStatus
  rank_score: number | null
  prescore: number
  first_seen: string
  times_seen: number
  days_published: number
  sources: { site: string; url: string }[]
  verdict: JobVerdict | null
  judge_status: 'ok' | 'judge_failed' | 'pending' | 'discarded'
  judge_error: string | null
  guillotine: { rule_id: string | null; rule_label: string | null; matched_text: string | null } | null
}

export interface JobsPage {
  items: JobItem[]
  total: number
  next_cursor: string | null
}

export interface Health {
  status: 'ok'
  version: string
  db_ok: boolean
  groq_key_configured: boolean
  token_configured: boolean
  last_run: { id: string; status: RunStatus; finished_at: string | null } | null
  /** Minutos sin uso tras los que se apaga sola (null: arrancada a mano). */
  auto_shutdown_minutes?: number | null
}

export interface SourceRun {
  source: string
  status: 'ok' | 'empty' | 'blocked' | 'timeout' | 'error' | 'skipped_breaker_open'
  fetched: number
  valid: number
  invalid: number
  duration_ms: number
  error_code: string | null
  error_message: string | null
  retry_at: string | null
}

export interface Run {
  id: string
  trigger: 'scheduler' | 'api' | 'cli'
  mode: RunMode
  status: RunStatus
  started_at: string
  finished_at: string | null
  rules_version: string
  counts: {
    fetched: number
    new: number
    duplicates: number
    discarded: number
    pending_judge: number
    judged: number
    judge_failed: number
    cache_hits: number
    /** Ofertas en la cola del juez al empezar a juzgar: con judged + judge_failed da el progreso. */
    judge_queue?: number
  }
  tokens_used: number
  budget_exhausted: boolean
  sources: SourceRun[]
  error: string | null
}

export interface SourceHealth {
  source: string
  state: 'closed' | 'open' | 'half_open'
  consecutive_failures: number
  open_until: string | null
  last_ok_at: string | null
  last_error: string | null
}

export interface Handoff {
  version: 1
  text: string
  chars: number
  title: string
  company: string
  source_url: string | null
  language: 'es' | 'en' | null
  complete: boolean
}

/** Reglas de Oro: se editan unos campos concretos y el resto viaja intacto. */
export interface GoldenRules {
  experience: { max_years_required: number | null; unknown_years: 'pass' }
  location: {
    home_area: string
    onsite_allowed_areas: string[]
    accept_remote: boolean
    remote_scopes: string[]
    accept_hybrid_outside_area: boolean
    home_countries: string[]
  }
  seniority: { exclude_title_terms: string[] }
  blacklists: {
    companies: string[]
    intermediary_signals: string[]
    title_terms: string[]
    description_terms: string[]
  }
  required_any: { terms: string[]; min_hits: number }
  judge: { min_score_to_show: number; priorities: string[]; soft_dislikes: string[]; profile_file: string }
  [section: string]: unknown
}

export interface RulesResponse {
  version: string
  rules: GoldenRules
  history: { version: string; created_at: string; active: boolean }[]
}

export interface SimulationReport {
  window_days: number
  total: number
  current: { kept: number; discarded: number }
  proposed: { kept: number; discarded: number }
  newly_discarded: {
    job_id: string
    title: string
    company: string
    rule_id: string | null
    rule_label: string | null
  }[]
  newly_kept: { job_id: string; title: string; company: string; rule_id: string | null; rule_label: string | null }[]
  newly_discarded_total: number
  newly_kept_total: number
  by_rule: Record<string, number>
}

export interface RulesSaved {
  version: string
  reevaluated: number
  now_pending_judge: number
  now_discarded: number
}

// --- Candidaturas (SPEC §18.4) -------------------------------------------------------------------

export type ApplicationStatus =
  'applied' | 'in_process' | 'interview' | 'offer' | 'rejected' | 'no_response' | 'withdrawn'
export type ApplicationSource = 'optimizer' | 'hunter' | 'manual'

export interface ApplicationEvent {
  status: ApplicationStatus
  at: string
}

/** Alta de una candidatura. El id lo genera el navegador: reenviarla desde la cola no la duplica. */
export interface ApplicationInput {
  id: string
  company: string
  title: string
  source: ApplicationSource
  job_id?: string | null
  url?: string | null
  location?: string
  applied_at?: string
  ats_score_before?: number | null
  ats_score_after?: number | null
  judge_score?: number | null
  notes?: string
  offer_text?: string | null
  cv_markdown?: string | null
}

export interface ApplicationItem {
  id: string
  job_id: string | null
  company: string
  title: string
  url: string | null
  location: string
  source: ApplicationSource
  status: ApplicationStatus
  applied_at: string
  status_changed_at: string
  ats_score_before: number | null
  ats_score_after: number | null
  judge_score: number | null
  notes: string
  has_offer_text: boolean
  has_cv: boolean
  events: ApplicationEvent[]
  /** Enviada hace más de 3 semanas sin noticias. */
  stale: boolean
}

export interface ApplicationDetail extends ApplicationItem {
  offer_text: string | null
  cv_markdown: string | null
}

export interface ApplicationUpdate {
  status?: ApplicationStatus
  notes?: string
  company?: string
  title?: string
  url?: string | null
}

export interface ApplicationStats {
  total: number
  last_7_days: number
  awaiting: number
  responded: number
  interviews: number
  offers: number
  stale: number
  avg_ats_after: number | null
  by_band: { label: string; total: number; responded: number }[]
}

export interface ApplicationsPage {
  items: ApplicationItem[]
  total: number
  stats: ApplicationStats
}

// --- Tu perfil (SPEC §19) -------------------------------------------------------------------------

/** Notas de los últimos `days` días que son de un perfil anterior y lo que costaría ponerlas al día. */
export interface OutdatedVerdicts {
  count: number
  /** Ya se juzgaron con este perfil: vuelven de la caché sin gastar tokens. */
  from_cache: number
  days: number
  est_tokens: number
  est_minutes: number
  /** null: sin tope diario de tokens. */
  tokens_left_today: number | null
}

export interface Profile {
  text: string
  /** Huella del archivo leído: al guardar se comprueba que nadie lo ha cambiado fuera de la web. */
  sha256: string
  chars: number
  max_chars: number
  /** Lo que buscará el pre-score en las ofertas. */
  terms: string[]
  is_example: boolean
  exists: boolean
  updated_at: string | null
  previous_text: string | null
  outdated: OutdatedVerdicts
}

/** Borrador sacado del CV en PDF: no se guarda hasta que el usuario lo revisa. */
export interface ProfileDraft {
  text: string
  chars: number
  sections: string[]
  warnings: string[]
}
