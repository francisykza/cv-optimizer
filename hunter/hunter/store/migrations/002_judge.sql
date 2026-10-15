-- Fase 2: cada oferta apunta a su veredicto en la caché (varias ofertas pueden compartirlo).
ALTER TABLE jobs ADD COLUMN verdict_key TEXT;
ALTER TABLE jobs ADD COLUMN judge_error TEXT;
CREATE INDEX ix_jobs_verdict_key ON jobs(verdict_key);
