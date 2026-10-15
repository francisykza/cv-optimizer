from datetime import timedelta

import pytest

from hunter.models import Run
from hunter.pipeline.run import Pipeline, PipelineConfig, RunInProgressError, run_status
from hunter.pipeline.simulate import simulate
from hunter.rules.schema import GoldenRules
from hunter.sources.breaker import BreakerPolicy
from hunter.store.repository import Repository, utcnow
from tests.conftest import LONG_DESCRIPTION
from tests.test_sources import FakeSource


def pipeline(repo: Repository, rules: GoldenRules) -> Pipeline:
    return Pipeline(
        repo, rules, PipelineConfig(source_timeout_s=1, breaker=BreakerPolicy(), profile_terms=["rag"])
    )


@pytest.fixture
def offers(make_raw):
    """Una buena, una senior (descartada) y la buena repetida en otro portal con otra URL."""
    good = make_raw(date_posted=None)
    senior = make_raw(title="Senior AI Engineer", date_posted=None)
    repost = make_raw(
        site="linkedin",
        site_job_id="li-999",
        url="https://www.linkedin.com/jobs/view/4000000999",
        title="Junior AI Engineer (m/f/d)",
        company="ACME LABS SL",
        date_posted=None,
    )
    return good, senior, repost


async def test_run_classifies_and_deduplicates(repo, rules, offers) -> None:
    good, senior, repost = offers
    run = await pipeline(repo, rules).run(
        [FakeSource("indeed", "ok", [good, senior]), FakeSource("linkedin", "ok", [repost])]
    )

    assert run.status == "ok"
    assert run.counts.model_dump(include={"fetched", "new", "duplicates", "discarded", "pending_judge"}) == {
        "fetched": 3,
        "new": 2,
        "duplicates": 1,
        "discarded": 1,
        "pending_judge": 1,
    }
    pending = repo.jobs_seen_since(utcnow() - timedelta(days=1), ("pending_judge",))
    assert len(pending) == 1 and pending[0].times_seen == 2 and pending[0].prescore > 0
    sources = repo.conn.execute(
        "SELECT site FROM job_sources WHERE job_id = ? ORDER BY site", (pending[0].id,)
    )
    assert [r["site"] for r in sources] == ["indeed", "linkedin"]  # alias del reposteo

    discarded = repo.jobs_seen_since(utcnow() - timedelta(days=1), ("discarded",))
    assert repo.latest_guillotine(discarded[0].id).rule_id == "SEN_TITLE"

    stored = repo.get_run(run.id)
    assert stored is not None and stored.status == "ok" and len(stored.sources) == 2


async def test_second_run_is_idempotent(repo, rules, offers) -> None:
    sources = [FakeSource("indeed", "ok", list(offers))]
    await pipeline(repo, rules).run(sources)
    second = await pipeline(repo, rules).run(sources)
    assert second.counts.new == 0 and second.counts.duplicates == 3
    assert repo.count_by_stage() == {"pending_judge": 1, "discarded": 1}


async def test_near_duplicate_content_with_other_title_is_alias(repo, rules, make_raw) -> None:
    first = make_raw(date_posted=None)
    retitled = make_raw(
        title="AI Engineer Junior - Málaga",
        company="Otra Consultora",
        description=LONG_DESCRIPTION.replace("flexible", "flexible."),
        date_posted=None,
    )
    run = await pipeline(repo, rules).run([FakeSource("indeed", "ok", [first, retitled])])
    assert run.counts.new == 1 and run.counts.duplicates == 1


async def test_same_text_with_different_level_is_not_merged(repo, rules, make_raw) -> None:
    # La empresa reutiliza la descripción: si llega antes la senior (descartada), la junior no se pierde.
    senior = make_raw(title="Senior AI Engineer", company="Otra S.L.", date_posted=None)
    junior = make_raw(title="Junior AI Engineer", date_posted=None)
    run = await pipeline(repo, rules).run([FakeSource("indeed", "ok", [senior, junior])])
    assert run.counts.new == 2 and run.counts.pending_judge == 1


async def test_partial_and_failed_status(repo, rules, make_raw) -> None:
    partial = await pipeline(repo, rules).run(
        [FakeSource("a", "blocked"), FakeSource("b", "ok", [make_raw()])]
    )
    assert partial.status == "partial" and partial.counts.new == 1
    failed = await pipeline(repo, rules).run([FakeSource("a", "blocked"), FakeSource("c", "error")])
    assert failed.status == "failed"
    assert run_status([]) == "ok"


async def test_live_run_blocks_and_orphans_are_failed(repo, rules) -> None:
    now = utcnow()
    live = Run(
        id="live", trigger="cli", mode="ingest_only", status="running", started_at=now, rules_version="x"
    )
    repo.create_run(live)
    with pytest.raises(RunInProgressError):
        await pipeline(repo, rules).run([])

    repo.conn.execute(
        "UPDATE runs SET heartbeat_at = ? WHERE id = 'live'", ((now - timedelta(minutes=15)).isoformat(),)
    )
    run = await pipeline(repo, rules).run([])
    assert run.status == "ok"
    assert repo.get_run("live").status == "failed"


async def test_reevaluate_after_rules_change(repo, rules, make_raw) -> None:
    three_years = make_raw(
        description=LONG_DESCRIPTION + " Requisitos: 3 años de experiencia.", date_posted=None
    )
    await pipeline(repo, rules).run([FakeSource("indeed", "ok", [three_years])])
    assert repo.count_by_stage() == {"discarded": 1}

    relaxed = rules.model_copy(
        update={"experience": rules.experience.model_copy(update={"max_years_required": 3})}
    )
    total, to_pending, to_discarded = pipeline(repo, relaxed).reevaluate(window_days=7)
    assert (total, to_pending, to_discarded) == (1, 1, 0)
    assert repo.count_by_stage() == {"pending_judge": 1}

    total, to_pending, to_discarded = pipeline(repo, rules).reevaluate(window_days=7)
    assert (to_pending, to_discarded) == (0, 1)


async def test_simulate_reports_changes_without_saving(repo, rules, make_raw) -> None:
    other_text = (
        "Empresa de logística busca desarrollador Python para automatizar procesos de almacén con "
        "modelos de IA: previsión de devoluciones, clasificación de incidencias y paneles internos. "
        "Trabajarás con FastAPI, PostgreSQL y colas de tareas junto al equipo de operaciones de Málaga. "
        "Mínimo 2 años de experiencia."
    )
    jobs = [
        make_raw(date_posted=None),
        make_raw(title="Python Developer", date_posted=None, description=other_text),
    ]
    await pipeline(repo, rules).run([FakeSource("indeed", "ok", jobs)])
    stricter = rules.model_copy(
        update={"experience": rules.experience.model_copy(update={"max_years_required": 1})}
    )
    report = simulate(repo, rules, stricter, window_days=7)
    assert report.total == 2
    assert (report.current.kept, report.proposed.kept) == (2, 1)
    assert report.newly_discarded_total == 1 and report.newly_discarded[0].rule_id == "EXP_TOO_MANY_YEARS"
    assert report.by_rule == {"EXP_TOO_MANY_YEARS": 1}
    assert repo.count_by_stage() == {"pending_judge": 2}  # nada cambia en la BD


async def test_purge_keeps_fingerprints_for_dedup(repo, rules, make_raw) -> None:
    senior = make_raw(title="Senior AI Engineer", date_posted=None)
    await pipeline(repo, rules).run([FakeSource("indeed", "ok", [senior])])
    future = utcnow() + timedelta(days=1)
    assert repo.purge(older_than=future, fingerprints_older_than=future - timedelta(days=365)) == 1
    assert repo.count_by_stage() == {}

    again = await pipeline(repo, rules).run([FakeSource("indeed", "ok", [senior])])
    assert again.counts.new == 0 and again.counts.duplicates == 1


async def test_purge_never_touches_pending_or_managed(repo, rules, make_raw) -> None:
    await pipeline(repo, rules).run([FakeSource("indeed", "ok", [make_raw(date_posted=None)])])
    future = utcnow() + timedelta(days=1)
    assert repo.purge(older_than=future, fingerprints_older_than=future) == 0


# --- Juez IA en el pipeline (Fase 2) -----------------------------------------------------------


def _judge(repo, rules, provider, budget: int = 100_000):
    from hunter.judge.judge import Judge, JudgeConfig, JudgeContext
    from hunter.judge.limiter import AdaptiveLimiter, BudgetGuard

    return Judge(
        provider,
        repo,
        AdaptiveLimiter(tokens_per_minute=10**6),
        BudgetGuard(repo, budget),
        JudgeContext.from_rules(rules, "Python, LLM, RAG"),
        JudgeConfig(),
    )


def _distinct_offers(make_raw, n: int) -> list:
    topics = ["logística", "banca", "salud", "turismo", "energía", "educación", "seguros", "retail"]
    return [
        make_raw(
            title=f"Junior AI Engineer {topics[i]}",
            date_posted=None,
            description=f"Equipo de {topics[i]} en Málaga busca perfil junior de Python para construir "
            f"servicios con LLM y RAG aplicados al sector {topics[i]}. Proyecto {i}: integración de datos "
            f"del sector {topics[i]}, pruebas automáticas, despliegue en la nube y mentoría semanal "
            f"con el equipo de {topics[i]}, revisiones de código y formación continua en {topics[i]}.",
        )
        for i in range(n)
    ]


async def test_full_run_judges_and_ranks(repo, rules, make_raw) -> None:
    from tests.fakes import FakeProvider, verdict_payload

    provider = FakeProvider(
        verdict_payload(match_score=90), verdict_payload(match_score=60, verdict="maybe"), repeat_last=False
    )
    run = await pipeline(repo, rules).run(
        [FakeSource("indeed", "ok", _distinct_offers(make_raw, 2))],
        mode="full",
        judge=_judge(repo, rules, provider),
    )
    assert run.status == "ok"
    assert (run.counts.judged, run.counts.pending_judge, run.tokens_used) == (2, 0, 2600)
    judged = sorted(
        repo.jobs_by_stage("judged", utcnow() - timedelta(days=1)), key=lambda j: -(j.rank_score or 0)
    )
    assert judged[0].rank_score > judged[1].rank_score and judged[0].verdict_key

    again = await pipeline(repo, rules).run(
        [FakeSource("indeed", "ok", _distinct_offers(make_raw, 2))],
        mode="full",
        judge=_judge(repo, rules, provider),
    )
    assert again.tokens_used == 0 and len(provider.requests) == 2  # todo duplicado: 0 tokens


async def test_rejudging_after_rules_round_trip_uses_cache(repo, rules, make_raw) -> None:
    from tests.fakes import FakeProvider, verdict_payload

    provider = FakeProvider(verdict_payload())
    offer = make_raw(description=LONG_DESCRIPTION + " Requisitos: 2 años de experiencia.", date_posted=None)
    await pipeline(repo, rules).run(
        [FakeSource("indeed", "ok", [offer])], mode="full", judge=_judge(repo, rules, provider)
    )
    # La oferta juzgada vuelve a pendiente (p. ej. se purgó el estado o se restauró): sin tokens.
    repo.conn.execute("UPDATE jobs SET stage = 'pending_judge'")
    run = await pipeline(repo, rules).run([], mode="judge_only", judge=_judge(repo, rules, provider))
    assert run.counts.cache_hits == 1 and run.tokens_used == 0 and len(provider.requests) == 1


async def test_quota_exhausted_stops_and_keeps_queue(repo, rules, make_raw) -> None:
    from app.core.exceptions import UpstreamRateLimitedError

    from tests.fakes import FakeProvider, verdict_payload

    provider = FakeProvider(
        verdict_payload(), UpstreamRateLimitedError(retry_after_s=7200), repeat_last=False
    )
    run = await pipeline(repo, rules).run(
        [FakeSource("indeed", "ok", _distinct_offers(make_raw, 4))],
        mode="full",
        judge=_judge(repo, rules, provider),
    )
    assert run.status == "partial" and run.budget_exhausted
    assert run.counts.judged == 1 and run.counts.pending_judge == 3
    assert "Cuota de Groq agotada" in run.error


async def test_daily_budget_stops_before_spending(repo, rules, make_raw) -> None:
    from tests.fakes import FakeProvider, verdict_payload

    provider = FakeProvider(verdict_payload())
    run = await pipeline(repo, rules).run(
        [FakeSource("indeed", "ok", _distinct_offers(make_raw, 3))],
        mode="full",
        judge=_judge(repo, rules, provider, budget=4000),
    )
    assert run.budget_exhausted and run.counts.judged >= 1 and run.counts.pending_judge >= 1
    assert "Presupuesto diario" in run.error


async def test_consecutive_transient_errors_stop_the_judge(repo, rules, make_raw) -> None:
    from app.core.exceptions import LLMTimeoutError

    from tests.fakes import FakeProvider

    run = await pipeline(repo, rules).run(
        [FakeSource("indeed", "ok", _distinct_offers(make_raw, 5))],
        mode="full",
        judge=_judge(repo, rules, FakeProvider(LLMTimeoutError())),
    )
    assert run.status == "partial" and "3 veces seguidas" in run.error
    assert run.counts.pending_judge == 5 and not run.budget_exhausted


async def test_judge_failed_is_recorded_and_can_be_retried(repo, rules, make_raw) -> None:
    from tests.fakes import FakeProvider, verdict_payload

    await pipeline(repo, rules).run(
        [FakeSource("indeed", "ok", _distinct_offers(make_raw, 1))],
        mode="full",
        judge=_judge(repo, rules, FakeProvider("roto")),
    )
    failed = repo.jobs_by_stage("judge_failed", utcnow() - timedelta(days=1))
    assert len(failed) == 1 and "JSON no válido" in failed[0].judge_error
    assert repo.reset_failed() == 1
    run = await pipeline(repo, rules).run(
        [], mode="judge_only", judge=_judge(repo, rules, FakeProvider(verdict_payload()))
    )
    assert run.counts.judged == 1 and run.counts.cache_hits == 0  # un fallo nunca se sirve desde caché


async def test_full_run_without_key_reports_it(repo, rules, make_raw) -> None:
    run = await pipeline(repo, rules).run([FakeSource("indeed", "ok", [make_raw()])], mode="full", judge=None)
    assert run.status == "partial" and "GROQ_API_KEY" in run.error and run.counts.pending_judge == 1


async def test_judged_offer_breaking_new_rules_is_discarded_and_comes_back_from_cache(
    repo, rules, make_raw
) -> None:
    from tests.fakes import FakeProvider, verdict_payload

    provider = FakeProvider(verdict_payload())
    offer = make_raw(description=LONG_DESCRIPTION + " Requisitos: 2 años de experiencia.", date_posted=None)
    await pipeline(repo, rules).run(
        [FakeSource("indeed", "ok", [offer])], mode="full", judge=_judge(repo, rules, provider)
    )
    stricter = rules.model_copy(
        update={"experience": rules.experience.model_copy(update={"max_years_required": 1})}
    )
    assert pipeline(repo, stricter).reevaluate(window_days=7)[2] == 1
    assert repo.count_by_stage() == {"discarded": 1}

    assert pipeline(repo, rules).reevaluate(window_days=7)[1] == 1  # vuelve a pasar
    run = await pipeline(repo, rules).run([], mode="judge_only", judge=_judge(repo, rules, provider))
    assert run.counts.cache_hits == 1 and run.tokens_used == 0 and len(provider.requests) == 1
