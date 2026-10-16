"""Única capa que toca SQL (SPEC D6): cambiar de SQLite a otra BD solo afecta a este módulo."""

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from hunter.models import AppStatus, GuillotineResult, NormalizedJob, Run, RunCounts, SourceRun, Stage
from hunter.pipeline.dedup import Candidate, title_level
from hunter.rules.engine import JobFacts
from hunter.rules.schema import GoldenRules


def utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class SourceHealth:
    source: str
    consecutive_failures: int = 0
    consecutive_empty: int = 0
    times_opened: int = 0
    open_until: datetime | None = None
    last_ok_at: datetime | None = None
    last_error: str | None = None


@dataclass(frozen=True)
class StoredJob:
    id: str
    title: str
    company: str
    location: str
    stage: Stage
    prescore: int
    first_seen: datetime
    last_seen: datetime
    times_seen: int
    facts: JobFacts
    url: str
    desc_sha256: str = ""
    verdict_key: str | None = None
    rank_score: float | None = None
    judge_error: str | None = None
    app_status: AppStatus = "none"


@dataclass(frozen=True)
class StoredVerdict:
    cache_key: str
    status: str  # "ok" | "judge_failed"
    verdict_json: str | None
    model: str
    prompt_version: str
    tokens_in: int
    tokens_out: int
    created_at: datetime


class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")

    # --- Reglas --------------------------------------------------------------------------

    def active_rules(self) -> GoldenRules | None:
        row = self.conn.execute("SELECT json FROM rules WHERE active = 1").fetchone()
        return GoldenRules.model_validate_json(row["json"]) if row else None

    def save_rules(self, rules: GoldenRules) -> str:
        """Guarda y activa. Guardar el mismo contenido otra vez solo lo reactiva."""
        version = rules.version
        with self.transaction():
            self.conn.execute("UPDATE rules SET active = 0 WHERE active = 1")
            self.conn.execute(
                "INSERT INTO rules (version, json, created_at, active) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(version) DO UPDATE SET active = 1",
                (version, rules.canonical_json(), _iso(utcnow())),
            )
        return version

    def rules_history(self, limit: int = 20) -> list[tuple[str, datetime, bool]]:
        rows = self.conn.execute(
            "SELECT version, created_at, active FROM rules ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [(r["version"], _dt(r["created_at"]), bool(r["active"])) for r in rows]

    # --- Deduplicación -------------------------------------------------------------------

    def find_by_source(self, url_canonical: str, site: str, site_job_id: str | None) -> str | None:
        row = self.conn.execute(
            "SELECT job_id FROM job_sources WHERE url_canonical = ? "
            "OR (site = ? AND site_job_id IS NOT NULL AND site_job_id = ?) LIMIT 1",
            (url_canonical, site, site_job_id),
        ).fetchone()
        if row:
            return row["job_id"]
        return None

    def purged_url_seen(self, url_canonical: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_fingerprints WHERE url_canonical = ? LIMIT 1", (url_canonical,)
        ).fetchone()
        return row is not None

    def candidates_by_key(self, job_key: str, since: datetime) -> list[Candidate]:
        rows = self.conn.execute(
            "SELECT id, simhash FROM jobs WHERE job_key = ? AND last_seen >= ? ORDER BY last_seen DESC",
            (job_key, _iso(since)),
        ).fetchall()
        purged = self.conn.execute(
            "SELECT simhash FROM seen_fingerprints WHERE job_key = ? AND last_seen >= ?",
            (job_key, _iso(since)),
        ).fetchall()
        return [Candidate(r["id"], r["simhash"]) for r in rows] + [
            Candidate(None, r["simhash"]) for r in purged
        ]

    def recent_simhashes(self, since: datetime) -> list[Candidate]:
        rows = self.conn.execute(
            "SELECT id, simhash, title_norm FROM jobs WHERE simhash != '' AND last_seen >= ?", (_iso(since),)
        ).fetchall()
        purged = self.conn.execute(
            "SELECT simhash FROM seen_fingerprints WHERE simhash != '' AND last_seen >= ?", (_iso(since),)
        ).fetchall()
        return [Candidate(r["id"], r["simhash"], title_level(r["title_norm"])) for r in rows] + [
            Candidate(None, r["simhash"]) for r in purged
        ]

    def touch_job(self, job_id: str, now: datetime) -> None:
        self.conn.execute(
            "UPDATE jobs SET last_seen = ?, times_seen = times_seen + 1 WHERE id = ?", (_iso(now), job_id)
        )

    def add_alias(self, job_id: str, job: NormalizedJob, now: datetime) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO job_sources (job_id, site, site_job_id, url, url_canonical, seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, job.raw.site, job.raw.site_job_id, job.raw.url, job.url_canonical, _iso(now)),
        )

    # --- Ofertas -------------------------------------------------------------------------

    def insert_job(self, job: NormalizedJob, stage: Stage, prescore: int, now: datetime) -> str:
        job_id = uuid.uuid4().hex
        raw = job.raw
        self.conn.execute(
            """INSERT INTO jobs (id, job_key, desc_sha256, simhash, title, title_norm, company, company_norm,
                 location, location_bucket, modality, language, description, description_chars,
                 salary_min, salary_max, salary_currency, salary_interval, salary_annual_max, date_posted,
                 first_seen, last_seen, times_seen, stage, prescore)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (
                job_id,
                job.job_key,
                job.desc_sha256,
                job.simhash,
                raw.title,
                job.title_norm,
                raw.company,
                job.company_norm,
                raw.location,
                job.location_bucket,
                job.modality,
                job.language,
                job.description,
                len(job.description),
                raw.salary_min,
                raw.salary_max,
                raw.salary_currency,
                raw.salary_interval,
                job.salary_annual_max,
                raw.date_posted.isoformat() if raw.date_posted else None,
                _iso(now),
                _iso(now),
                stage,
                prescore,
            ),
        )
        self.add_alias(job_id, job, now)
        return job_id

    def save_guillotine(self, job_id: str, result: GuillotineResult, now: datetime) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO guillotine_results "
            "(job_id, rules_version, passed, rule_id, rule_label, matched_text, evaluated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                result.rules_version,
                int(result.passed),
                result.rule_id,
                result.rule_label,
                result.matched_text,
                _iso(now),
            ),
        )

    def set_stage(self, job_id: str, stage: Stage, prescore: int | None = None) -> None:
        if prescore is None:
            self.conn.execute("UPDATE jobs SET stage = ? WHERE id = ?", (stage, job_id))
        else:
            self.conn.execute(
                "UPDATE jobs SET stage = ?, prescore = ? WHERE id = ?", (stage, prescore, job_id)
            )

    def jobs_seen_since(self, since: datetime, stages: tuple[Stage, ...] | None = None) -> list[StoredJob]:
        sql = """SELECT j.*, (SELECT url FROM job_sources s WHERE s.job_id = j.id
                         ORDER BY seen_at LIMIT 1) AS url
                 FROM jobs j WHERE j.last_seen >= ?"""
        params: list[object] = [_iso(since)]
        if stages:
            sql += f" AND j.stage IN ({','.join('?' * len(stages))})"
            params.extend(stages)
        rows = self.conn.execute(sql + " ORDER BY j.first_seen DESC", params).fetchall()
        return [self._stored(r) for r in rows]

    def latest_guillotine(self, job_id: str) -> GuillotineResult | None:
        row = self.conn.execute(
            # rowid desempata dentro del mismo segundo (INSERT OR REPLACE siempre crea un rowid nuevo).
            "SELECT * FROM guillotine_results WHERE job_id = ? "
            "ORDER BY evaluated_at DESC, rowid DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return GuillotineResult(
            passed=bool(row["passed"]),
            rule_id=row["rule_id"],
            rule_label=row["rule_label"],
            matched_text=row["matched_text"],
            rules_version=row["rules_version"],
        )

    def count_by_stage(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT stage, COUNT(*) AS n FROM jobs GROUP BY stage").fetchall()
        return {r["stage"]: r["n"] for r in rows}

    @staticmethod
    def _stored(row: sqlite3.Row) -> StoredJob:
        return StoredJob(
            id=row["id"],
            title=row["title"],
            company=row["company"],
            location=row["location"],
            stage=row["stage"],
            prescore=row["prescore"],
            first_seen=_dt(row["first_seen"]),
            last_seen=_dt(row["last_seen"]),
            times_seen=row["times_seen"],
            url=row["url"] or "",
            facts=JobFacts(
                title=row["title"],
                company_norm=row["company_norm"],
                location_bucket=row["location_bucket"],
                modality=row["modality"],
                language=row["language"],
                description=row["description"],
                date_posted=date.fromisoformat(row["date_posted"]) if row["date_posted"] else None,
                salary_annual_max=row["salary_annual_max"],
                salary_currency=row["salary_currency"],
                location=row["location"],
            ),
            desc_sha256=row["desc_sha256"],
            verdict_key=row["verdict_key"],
            rank_score=row["rank_score"],
            judge_error=row["judge_error"],
            app_status=row["app_status"],
        )

    # --- Juez y caché de veredictos ------------------------------------------------------

    def jobs_by_stage(self, stage: Stage, since: datetime) -> list[StoredJob]:
        """Ofertas de una etapa vistas desde `since`, de mayor a menor pre-score (cola del juez)."""
        rows = self.conn.execute(
            """SELECT j.*, (SELECT url FROM job_sources s WHERE s.job_id = j.id
                            ORDER BY seen_at LIMIT 1) AS url
               FROM jobs j WHERE j.stage = ? AND j.last_seen >= ?
               ORDER BY j.prescore DESC, j.first_seen DESC""",
            (stage, _iso(since)),
        ).fetchall()
        return [self._stored(r) for r in rows]

    def get_job(self, job_id: str) -> StoredJob | None:
        row = self.conn.execute(
            """SELECT j.*, (SELECT url FROM job_sources s WHERE s.job_id = j.id
                            ORDER BY seen_at LIMIT 1) AS url
               FROM jobs j WHERE j.id = ? OR j.id LIKE ? ORDER BY j.id = ? DESC LIMIT 1""",
            (job_id, f"{job_id}%", job_id),
        ).fetchone()
        return self._stored(row) if row else None

    def cached_verdict(self, cache_key: str) -> StoredVerdict | None:
        row = self.conn.execute("SELECT * FROM verdicts WHERE cache_key = ?", (cache_key,)).fetchone()
        if row is None:
            return None
        return StoredVerdict(
            cache_key=row["cache_key"],
            status=row["status"],
            verdict_json=row["verdict_json"],
            model=row["model"],
            prompt_version=row["prompt_version"],
            tokens_in=row["tokens_in"],
            tokens_out=row["tokens_out"],
            created_at=_dt(row["created_at"]),
        )

    def save_verdict(self, job_id: str, verdict: StoredVerdict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO verdicts (cache_key, job_id, status, verdict_json, model, "
            "prompt_version, tokens_in, tokens_out, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                verdict.cache_key,
                job_id,
                verdict.status,
                verdict.verdict_json,
                verdict.model,
                verdict.prompt_version,
                verdict.tokens_in,
                verdict.tokens_out,
                _iso(verdict.created_at),
            ),
        )

    def set_judged(
        self, job_id: str, stage: Stage, verdict_key: str | None, rank: float | None, error: str | None = None
    ) -> None:
        self.conn.execute(
            "UPDATE jobs SET stage = ?, verdict_key = ?, rank_score = ?, judge_error = ? WHERE id = ?",
            (stage, verdict_key, rank, error, job_id),
        )

    def set_app_status(self, job_id: str, status: AppStatus) -> None:
        self.conn.execute("UPDATE jobs SET app_status = ? WHERE id = ?", (status, job_id))

    def job_sources(self, job_id: str) -> list[tuple[str, str, datetime]]:
        """(portal, URL, visto) de cada sitio donde apareció la oferta, del primero al último."""
        rows = self.conn.execute(
            "SELECT site, url, seen_at FROM job_sources WHERE job_id = ? ORDER BY seen_at", (job_id,)
        ).fetchall()
        return [(r["site"], r["url"], _dt(r["seen_at"])) for r in rows]

    def verdict_history(self, job_id: str, limit: int = 5) -> list[StoredVerdict]:
        rows = self.conn.execute(
            "SELECT cache_key FROM verdicts WHERE job_id = ? ORDER BY created_at DESC LIMIT ?",
            (job_id, limit),
        ).fetchall()
        return [v for r in rows if (v := self.cached_verdict(r["cache_key"])) is not None]

    def recent_runs(self, limit: int = 10) -> list[Run]:
        rows = self.conn.execute(
            "SELECT id FROM runs ORDER BY started_at DESC, rowid DESC LIMIT ?", (limit,)
        ).fetchall()
        return [run for r in rows if (run := self.get_run(r["id"])) is not None]

    def reset_failed(self) -> int:
        cur = self.conn.execute(
            "UPDATE jobs SET stage = 'pending_judge', judge_error = NULL WHERE stage = 'judge_failed'"
        )
        return cur.rowcount

    def tokens_used(self, day: date) -> int:
        row = self.conn.execute(
            "SELECT tokens_used FROM token_ledger WHERE day = ?", (day.isoformat(),)
        ).fetchone()
        return row["tokens_used"] if row else 0

    def add_tokens(self, day: date, tokens: int) -> None:
        self.conn.execute(
            "INSERT INTO token_ledger (day, tokens_used, requests) VALUES (?, ?, 1) "
            "ON CONFLICT(day) DO UPDATE SET tokens_used = tokens_used + excluded.tokens_used, "
            "requests = requests + 1",
            (day.isoformat(), tokens),
        )

    # --- Ejecuciones ---------------------------------------------------------------------

    def create_run(self, run: Run) -> None:
        self.conn.execute(
            "INSERT INTO runs (id, trigger, mode, status, started_at, heartbeat_at, "
            "rules_version, counts_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run.id,
                run.trigger,
                run.mode,
                run.status,
                _iso(run.started_at),
                _iso(run.started_at),
                run.rules_version,
                run.counts.model_dump_json(),
            ),
        )

    def heartbeat(self, run_id: str, counts: RunCounts) -> None:
        self.conn.execute(
            "UPDATE runs SET heartbeat_at = ?, counts_json = ? WHERE id = ?",
            (_iso(utcnow()), counts.model_dump_json(), run_id),
        )

    def finish_run(self, run: Run) -> None:
        self.conn.execute(
            "UPDATE runs SET status = ?, finished_at = ?, heartbeat_at = ?, counts_json = ?, "
            "tokens_used = ?, "
            "budget_exhausted = ?, error = ? WHERE id = ?",
            (
                run.status,
                _iso(run.finished_at),
                _iso(utcnow()),
                run.counts.model_dump_json(),
                run.tokens_used,
                int(run.budget_exhausted),
                run.error,
                run.id,
            ),
        )

    def save_source_run(self, run_id: str, sr: SourceRun) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO source_runs (run_id, source, status, fetched, valid, invalid, "
            "duration_ms, "
            "error_code, error_message, retry_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                sr.source,
                sr.status,
                sr.fetched,
                sr.valid,
                sr.invalid,
                sr.duration_ms,
                sr.error_code,
                sr.error_message,
                _iso(sr.retry_at),
            ),
        )

    def live_run(self, stale_after: timedelta) -> str | None:
        """Id de un run en marcha con latido reciente, o None."""
        row = self.conn.execute(
            "SELECT id FROM runs WHERE status = 'running' AND heartbeat_at >= ? LIMIT 1",
            (_iso(utcnow() - stale_after),),
        ).fetchone()
        return row["id"] if row else None

    def fail_orphan_runs(self, stale_after: timedelta) -> int:
        """Runs 'running' sin latido (el PC se apagó a mitad): se marcan como fallidos."""
        cur = self.conn.execute(
            "UPDATE runs SET status = 'failed', finished_at = heartbeat_at, "
            "error = 'interrumpido (sin latido)' "
            "WHERE status = 'running' AND heartbeat_at < ?",
            (_iso(utcnow() - stale_after),),
        )
        return cur.rowcount

    def get_run(self, run_id: str) -> Run | None:
        row = self.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        sources = self.conn.execute(
            "SELECT * FROM source_runs WHERE run_id = ? ORDER BY source", (run_id,)
        ).fetchall()
        return Run(
            id=row["id"],
            trigger=row["trigger"],
            mode=row["mode"],
            status=row["status"],
            started_at=_dt(row["started_at"]),
            finished_at=_dt(row["finished_at"]),
            rules_version=row["rules_version"],
            counts=RunCounts.model_validate_json(row["counts_json"]),
            tokens_used=row["tokens_used"],
            budget_exhausted=bool(row["budget_exhausted"]),
            error=row["error"],
            sources=[
                SourceRun(
                    source=s["source"],
                    status=s["status"],
                    fetched=s["fetched"],
                    valid=s["valid"],
                    invalid=s["invalid"],
                    duration_ms=s["duration_ms"],
                    error_code=s["error_code"],
                    error_message=s["error_message"],
                    retry_at=_dt(s["retry_at"]),
                )
                for s in sources
            ],
        )

    # --- Salud de las fuentes (circuit breaker) ------------------------------------------

    def source_health(self, source: str) -> SourceHealth:
        row = self.conn.execute("SELECT * FROM source_health WHERE source = ?", (source,)).fetchone()
        if row is None:
            return SourceHealth(source=source)
        return SourceHealth(
            source=source,
            consecutive_failures=row["consecutive_failures"],
            consecutive_empty=row["consecutive_empty"],
            times_opened=row["times_opened"],
            open_until=_dt(row["open_until"]),
            last_ok_at=_dt(row["last_ok_at"]),
            last_error=row["last_error"],
        )

    def all_source_health(self) -> list[SourceHealth]:
        rows = self.conn.execute("SELECT source FROM source_health ORDER BY source").fetchall()
        return [self.source_health(r["source"]) for r in rows]

    def save_source_health(self, h: SourceHealth) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO source_health (source, consecutive_failures, consecutive_empty, "
            "times_opened, "
            "open_until, last_ok_at, last_error) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                h.source,
                h.consecutive_failures,
                h.consecutive_empty,
                h.times_opened,
                _iso(h.open_until),
                _iso(h.last_ok_at),
                h.last_error,
            ),
        )

    # --- Purga ---------------------------------------------------------------------------

    def purge(self, older_than: datetime, fingerprints_older_than: datetime) -> int:
        """Borra ofertas sin gestionar cuyo `last_seen` es anterior a `older_than`, conservando sus
        huellas (hasta `fingerprints_older_than`) para seguir deduplicando."""
        cutoff = _iso(older_than)
        with self.transaction():
            self.conn.execute(
                """INSERT INTO seen_fingerprints (job_key, simhash, desc_sha256, url_canonical, last_seen)
                   SELECT j.job_key, j.simhash, j.desc_sha256, s.url_canonical, j.last_seen
                   FROM jobs j JOIN job_sources s ON s.job_id = j.id
                   WHERE j.last_seen < ? AND j.app_status = 'none'
                     AND j.stage IN ('discarded', 'judged', 'judge_failed')""",
                (cutoff,),
            )
            cur = self.conn.execute(
                """DELETE FROM jobs WHERE last_seen < ? AND app_status = 'none'
                     AND stage IN ('discarded', 'judged', 'judge_failed')""",
                (cutoff,),
            )
            self.conn.execute(
                "DELETE FROM seen_fingerprints WHERE last_seen < ?", (_iso(fingerprints_older_than),)
            )
        return cur.rowcount
