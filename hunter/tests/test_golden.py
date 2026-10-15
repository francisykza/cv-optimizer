"""Golden set (SPEC §15): ofertas etiquetadas a mano que recorren el camino real
normalización → guillotina con las reglas de ejemplo.

- Recall de 'keep' = 100 %: la guillotina nunca descarta una oferta buena.
- Al menos el 80 % de las 'discard' se descartan, y por la regla esperada.
- Test live (fuera de CI): `HUNTER_LIVE=1 pytest -m live` llama a Groq de verdad con unas pocas
  ofertas y comprueba que el juez separa las claramente buenas de las claramente malas.
"""

import json
import os
from datetime import date
from pathlib import Path

import pytest

from hunter.models import RawJob
from hunter.pipeline.normalize import normalize
from hunter.rules.engine import JobFacts, evaluate
from hunter.rules.schema import GoldenRules

GOLDEN = json.loads((Path(__file__).parent / "golden" / "offers.json").read_text(encoding="utf-8"))["offers"]
TODAY = date(2026, 10, 15)


def _raw(offer: dict) -> RawJob:
    return RawJob(
        site="indeed",
        site_job_id=offer["id"],
        url=f"https://example.com/jobs/{offer['id']}",
        title=offer["title"],
        company=offer["company"],
        location=offer["location"],
        description=offer["description"],
        date_posted=date.fromisoformat(offer.get("date_posted", "2026-10-14")),
    )


def _first_rule(offer: dict, rules: GoldenRules) -> str | None:
    hits = evaluate(JobFacts.from_normalized(normalize(_raw(offer))), rules, TODAY)
    return hits[0].rule_id if hits else None


def test_golden_set_is_balanced() -> None:
    expects = [o["expect"] for o in GOLDEN]
    assert expects.count("keep") >= 20 and expects.count("discard") >= 20
    assert len({o["id"] for o in GOLDEN}) == len(GOLDEN)


def test_guillotine_never_discards_a_good_offer(rules: GoldenRules) -> None:
    lost = {o["id"]: _first_rule(o, rules) for o in GOLDEN if o["expect"] == "keep"}
    lost = {k: v for k, v in lost.items() if v is not None}
    assert lost == {}, f"Ofertas buenas descartadas (falsos negativos): {lost}"


def test_guillotine_discards_bad_offers_for_the_right_reason(rules: GoldenRules) -> None:
    bad = [o for o in GOLDEN if o["expect"] == "discard"]
    results = {o["id"]: (_first_rule(o, rules), o["rule"]) for o in bad}
    right = [k for k, (got, want) in results.items() if got == want]
    wrong = {k: v for k, v in results.items() if v[0] != v[1]}
    assert len(right) / len(bad) >= 0.8, f"Descartes incorrectos (obtenida, esperada): {wrong}"
    # Ninguna mala debe pasar entera: como mucho, descartada por otra regla.
    assert all(got is not None for got, _ in results.values()), f"Malas que pasan: {wrong}"


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("HUNTER_LIVE"), reason="test live: HUNTER_LIVE=1 y GROQ_API_KEY")
async def test_live_judge_separates_good_from_bad(rules: GoldenRules, repo) -> None:  # pragma: no cover
    import httpx
    from app.services.llm.groq import GroqProvider

    from hunter.config import get_settings
    from hunter.judge.judge import Judge, JudgeConfig, JudgeContext
    from hunter.judge.limiter import AdaptiveLimiter, BudgetGuard
    from hunter.store.repository import StoredJob, utcnow

    settings = get_settings()
    assert settings.server_api_key is not None, "Falta GROQ_API_KEY"
    profile = (Path(__file__).parent.parent / "profile.example.md").read_text(encoding="utf-8")
    model = os.environ.get("HUNTER_LIVE_MODEL", settings.groq_model_primary)
    async with httpx.AsyncClient() as client:
        provider = GroqProvider(
            client=client,
            api_key=settings.server_api_key,
            models=[model],
            mode="byok",
            base_url=settings.groq_base_url,
            timeout_s=90,
            reasoning_effort="low",
        )
        judge = Judge(
            provider,
            repo,
            AdaptiveLimiter(),
            BudgetGuard(repo, 0),
            JudgeContext.from_rules(rules, profile),
            JudgeConfig(model=model),
        )
        scores = {}
        for offer in (o for o in GOLDEN if o.get("judge")):
            job_norm = normalize(_raw(offer))
            now = utcnow()
            job = StoredJob(
                id=offer["id"],
                title=offer["title"],
                company=offer["company"],
                location=offer["location"],
                stage="pending_judge",
                prescore=50,
                first_seen=now,
                last_seen=now,
                times_seen=1,
                facts=JobFacts.from_normalized(job_norm),
                url="",
                desc_sha256=job_norm.desc_sha256,
            )
            outcome = await judge.judge(job, force=True)
            assert outcome.status == "ok", outcome.error
            scores[offer["id"]] = (offer["judge"], outcome.verdict.match_score)
    print(scores)
    for offer_id, (expected, score) in scores.items():
        assert (score >= 60) if expected == "high" else (score <= 50), f"{offer_id}: {score} ({expected})"
