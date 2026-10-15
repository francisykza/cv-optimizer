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
        "UPDATE runs SET heartbeat_at = ? WHERE id = 'live'", ((now - timedelta(minutes=5)).isoformat(),)
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
