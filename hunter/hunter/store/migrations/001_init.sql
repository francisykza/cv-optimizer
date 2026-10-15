-- Esquema inicial (SPEC §4.2). Fechas en ISO 8601 con zona (UTC).

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  job_key TEXT NOT NULL,
  desc_sha256 TEXT NOT NULL,
  simhash TEXT NOT NULL,                 -- hex: un uint64 no cabe en INTEGER con signo
  title TEXT NOT NULL, title_norm TEXT NOT NULL,
  company TEXT NOT NULL, company_norm TEXT NOT NULL,
  location TEXT NOT NULL, location_bucket TEXT NOT NULL,
  modality TEXT NOT NULL, language TEXT NOT NULL,
  description TEXT NOT NULL, description_chars INTEGER NOT NULL,
  salary_min REAL, salary_max REAL, salary_currency TEXT, salary_interval TEXT, salary_annual_max REAL,
  date_posted TEXT,
  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, times_seen INTEGER NOT NULL DEFAULT 1,
  stage TEXT NOT NULL, app_status TEXT NOT NULL DEFAULT 'none',
  prescore INTEGER NOT NULL DEFAULT 0, rank_score REAL
);
CREATE INDEX ix_jobs_job_key ON jobs(job_key);
CREATE INDEX ix_jobs_stage_rank ON jobs(stage, rank_score DESC);
CREATE INDEX ix_jobs_last_seen ON jobs(last_seen);
CREATE INDEX ix_jobs_first_seen ON jobs(first_seen);

CREATE TABLE job_sources (                -- alias: la misma oferta vista en varias URLs/portales
  job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  site TEXT NOT NULL, site_job_id TEXT,
  url TEXT NOT NULL, url_canonical TEXT NOT NULL UNIQUE,
  seen_at TEXT NOT NULL
);
CREATE INDEX ix_job_sources_job ON job_sources(job_id);
CREATE UNIQUE INDEX ux_job_sources_site_id ON job_sources(site, site_job_id) WHERE site_job_id IS NOT NULL;

CREATE TABLE guillotine_results (
  job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  rules_version TEXT NOT NULL,
  passed INTEGER NOT NULL, rule_id TEXT, rule_label TEXT, matched_text TEXT,
  evaluated_at TEXT NOT NULL,
  PRIMARY KEY (job_id, rules_version)
);

CREATE TABLE verdicts (                   -- caché de veredictos (Fase 2)
  cache_key TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  status TEXT NOT NULL, verdict_json TEXT,
  model TEXT NOT NULL, prompt_version TEXT NOT NULL,
  tokens_in INTEGER NOT NULL, tokens_out INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_verdicts_job ON verdicts(job_id, created_at DESC);

CREATE TABLE rules (
  version TEXT PRIMARY KEY,               -- sha256[:12] del JSON canónico
  json TEXT NOT NULL, created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE runs (
  id TEXT PRIMARY KEY, trigger TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL,
  started_at TEXT NOT NULL, finished_at TEXT, heartbeat_at TEXT NOT NULL,
  rules_version TEXT NOT NULL, counts_json TEXT NOT NULL,
  tokens_used INTEGER NOT NULL DEFAULT 0, budget_exhausted INTEGER NOT NULL DEFAULT 0, error TEXT
);
CREATE INDEX ix_runs_started ON runs(started_at DESC);

CREATE TABLE source_runs (
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  source TEXT NOT NULL, status TEXT NOT NULL,
  fetched INTEGER NOT NULL DEFAULT 0, valid INTEGER NOT NULL DEFAULT 0, invalid INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  error_code TEXT, error_message TEXT, retry_at TEXT,
  PRIMARY KEY (run_id, source)
);

CREATE TABLE source_health (              -- circuit breaker por fuente
  source TEXT PRIMARY KEY,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  consecutive_empty INTEGER NOT NULL DEFAULT 0,
  times_opened INTEGER NOT NULL DEFAULT 0,
  open_until TEXT, last_ok_at TEXT, last_error TEXT
);

CREATE TABLE token_ledger (               -- presupuesto diario del juez (Fase 2)
  day TEXT PRIMARY KEY, tokens_used INTEGER NOT NULL DEFAULT 0, requests INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE seen_fingerprints (          -- huellas que sobreviven a la purga
  job_key TEXT NOT NULL, simhash TEXT NOT NULL, desc_sha256 TEXT NOT NULL,
  url_canonical TEXT, last_seen TEXT NOT NULL
);
CREATE INDEX ix_seen_fp_job_key ON seen_fingerprints(job_key);
CREATE INDEX ix_seen_fp_url ON seen_fingerprints(url_canonical);
