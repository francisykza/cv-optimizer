"""De ofertas guardadas a JSON de la API: veredicto, estado del juez, motivo de descarte y handoff."""

from datetime import datetime

from app.services.text_utils import fold
from pydantic import ValidationError

from hunter.api.schemas import (
    GuillotineOut,
    Handoff,
    JobDetail,
    JobItem,
    JobsView,
    JudgeStatus,
    SourceLink,
    VerdictHistoryItem,
)
from hunter.judge.schema import JobVerdict
from hunter.models import AppStatus, Stage
from hunter.store.repository import Repository, StoredJob

VIEW_STAGES: dict[JobsView, tuple[Stage, ...]] = {
    "ranked": ("judged",),
    "pending": ("pending_judge",),
    "discarded": ("discarded",),
    "failed": ("judge_failed",),
    "all": ("judged", "pending_judge", "judge_failed", "discarded"),
}
_JUDGE_STATUS: dict[str, JudgeStatus] = {
    "judged": "ok",
    "judge_failed": "judge_failed",
    "pending_judge": "pending",
    "discarded": "discarded",
}
_MODALITY_ES = {
    "remote": "remoto",
    "hybrid": "híbrido",
    "onsite": "presencial",
    "unknown": "modalidad no indicada",
}
OPTIMIZER_MIN_CHARS = 200  # mínimos y máximos de la oferta en el Optimizador (frontend/src/lib/constants.ts)
OPTIMIZER_MAX_CHARS = 15_000


def verdict_of(repo: Repository, job: StoredJob) -> JobVerdict | None:
    if job.stage != "judged" or not job.verdict_key:
        return None
    stored = repo.cached_verdict(job.verdict_key)
    if stored is None or stored.status != "ok" or not stored.verdict_json:
        return None
    try:
        return JobVerdict.model_validate_json(stored.verdict_json)
    except ValidationError:
        return None


def to_item(repo: Repository, job: StoredJob, now: datetime, verdict: JobVerdict | None = None) -> JobItem:
    published = job.facts.date_posted or job.first_seen.date()
    guillotine = None
    if job.stage == "discarded":
        g = repo.latest_guillotine(job.id)
        if g is not None and not g.passed:
            guillotine = GuillotineOut(
                rule_id=g.rule_id, rule_label=g.rule_label, matched_text=g.matched_text
            )
    return JobItem(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        modality=job.facts.modality,
        stage=job.stage,
        app_status=job.app_status,
        rank_score=job.rank_score,
        prescore=job.prescore,
        first_seen=job.first_seen,
        times_seen=job.times_seen,
        days_published=max(0, (now.date() - published).days),
        sources=[SourceLink(site=site, url=url) for site, url, _ in repo.job_sources(job.id)],
        verdict=verdict if verdict is not None else verdict_of(repo, job),
        judge_status=_JUDGE_STATUS[job.stage],
        judge_error=job.judge_error if job.stage == "judge_failed" else None,
        guillotine=guillotine,
    )


def to_detail(repo: Repository, job: StoredJob, now: datetime) -> JobDetail:
    history = []
    for stored in repo.verdict_history(job.id):
        score = None
        if stored.verdict_json:
            try:
                score = JobVerdict.model_validate_json(stored.verdict_json).match_score
            except ValidationError:
                score = None
        history.append(
            VerdictHistoryItem(
                model=stored.model,
                prompt_version=stored.prompt_version,
                created_at=stored.created_at,
                match_score=score,
            )
        )
    return JobDetail(
        **to_item(repo, job, now).model_dump(), description=job.facts.description, verdict_history=history
    )


def select_jobs(
    repo: Repository,
    jobs: list[StoredJob],
    view: JobsView,
    *,
    app_status: AppStatus | None,
    min_score: int | None,
    q: str | None,
) -> list[tuple[StoredJob, JobVerdict | None]]:
    """Filtra y ordena. En 'ranked' se ocultan las descartadas a mano salvo que se pidan."""
    needle = fold(q).strip() if q else ""
    out: list[tuple[StoredJob, JobVerdict | None]] = []
    for job in jobs:
        if app_status is not None and job.app_status != app_status:
            continue
        if app_status is None and view == "ranked" and job.app_status == "dismissed":
            continue
        if needle and needle not in fold(f"{job.title} {job.company} {job.location}"):
            continue
        verdict = verdict_of(repo, job) if view in ("ranked", "all") else None
        if (
            view == "ranked"
            and min_score is not None
            and (verdict is None or verdict.match_score < min_score)
        ):
            continue
        out.append((job, verdict))
    if view == "ranked":
        out.sort(key=lambda pair: pair[0].rank_score or 0, reverse=True)
    elif view == "pending":
        out.sort(key=lambda pair: pair[0].prescore, reverse=True)
    else:
        out.sort(key=lambda pair: pair[0].first_seen, reverse=True)
    return out


def build_handoff(job: StoredJob, description: str) -> Handoff:
    """Texto listo para el textarea del Optimizador: cabecera con contexto + descripción."""
    location = job.location or "ubicación no indicada"
    header = f"{job.title} — {job.company} ({location}, {_MODALITY_ES[job.facts.modality]})"
    body = description.strip()
    text = f"{header}\n\n{body}"[:OPTIMIZER_MAX_CHARS]
    language = job.facts.language if job.facts.language in ("es", "en") else None
    return Handoff(
        text=text,
        chars=len(text),
        title=job.title,
        company=job.company,
        source_url=job.url or None,
        language=language,
        complete=len(body) >= OPTIMIZER_MIN_CHARS,
    )
