-- Fase 4 (SPEC §18): candidaturas y emparejado del navegador con el lanzador.

CREATE TABLE applications (
  id TEXT PRIMARY KEY,                    -- lo genera el cliente: reenviar el alta no la duplica
  job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
  company TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  location TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,                   -- optimizer | hunter | manual
  status TEXT NOT NULL,
  applied_at TEXT NOT NULL,
  status_changed_at TEXT NOT NULL,
  ats_score_before INTEGER,               -- % de palabras clave de la oferta en el CV original
  ats_score_after INTEGER,                -- el mismo % en el CV que se envió
  judge_score INTEGER,                    -- nota del juez del Buscador
  notes TEXT NOT NULL DEFAULT '',
  offer_text TEXT,                        -- copia de la oferta: los portales la borran al cerrarla
  cv_markdown TEXT,                       -- el CV exacto que se envió
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX ix_applications_applied ON applications(applied_at DESC);
CREATE INDEX ix_applications_job ON applications(job_id);

CREATE TABLE application_events (         -- historial de estados (tiempos de respuesta)
  application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  at TEXT NOT NULL
);
CREATE INDEX ix_application_events_app ON application_events(application_id, at);

CREATE TABLE pairing_codes (              -- códigos de un solo uso del lanzador (solo su hash)
  code_sha256 TEXT PRIMARY KEY,
  expires_at TEXT NOT NULL
);
