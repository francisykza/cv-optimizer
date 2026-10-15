from datetime import date

import pytest

from hunter.rules.engine import JobFacts, evaluate, guillotine
from hunter.rules.schema import GoldenRules
from tests.conftest import LONG_DESCRIPTION

TODAY = date(2026, 10, 15)


def facts(**overrides: object) -> JobFacts:
    data: dict[str, object] = {
        "title": "Junior AI Engineer",
        "company_norm": "acme labs",
        "location_bucket": "malaga",
        "modality": "hybrid",
        "language": "es",
        "description": LONG_DESCRIPTION,
        "date_posted": date(2026, 10, 14),
        "location": "Málaga",
    }
    data.update(overrides)
    return JobFacts(**data)  # type: ignore[arg-type]


def first_rule(rules: GoldenRules, **overrides: object) -> str | None:
    hits = evaluate(facts(**overrides), rules, TODAY)
    return hits[0].rule_id if hits else None


def test_good_offer_passes(rules: GoldenRules) -> None:
    result = guillotine(facts(), rules, TODAY)
    assert result.passed and result.rule_id is None
    assert result.rules_version == rules.version


@pytest.mark.parametrize(
    ("overrides", "rule_id"),
    [
        ({"date_posted": date(2026, 9, 1)}, "STALE"),
        ({"title": "Senior AI Engineer"}, "SEN_TITLE"),
        ({"title": "Sr. Python Developer"}, "SEN_TITLE"),
        ({"title": "Tech Lead IA"}, "SEN_TITLE"),
        ({"title": "Comercial de software IA"}, "BL_TITLE_TERM"),
        ({"location_bucket": "madrid", "modality": "onsite"}, "LOC_ONSITE_OUT_OF_AREA"),
        ({"location_bucket": "madrid", "modality": "hybrid"}, "LOC_ONSITE_OUT_OF_AREA"),
        ({"modality": "remote", "location": "Remote (USA Only)"}, "LOC_REMOTE_SCOPE"),
        (
            {"modality": "remote", "description": LONG_DESCRIPTION + " Candidates must be based in the US."},
            "LOC_REMOTE_SCOPE",
        ),
        (  # redacción real que se escapaba (oferta de MeeBoss, 16/10/2026)
            {
                "modality": "remote",
                "location": "USA",
                "description": LONG_DESCRIPTION
                + " Authorization to work in the US or Canada without sponsorship.",
            },
            "LOC_REMOTE_SCOPE",
        ),
        (
            {
                "modality": "remote",
                "description": LONG_DESCRIPTION + " Valid work permit for the UK required.",
            },
            "LOC_REMOTE_SCOPE",
        ),
        ({"language": "other"}, "LANG_NOT_ALLOWED"),
        (
            {"description": LONG_DESCRIPTION + " Requisitos: 4 años de experiencia con Python."},
            "EXP_TOO_MANY_YEARS",
        ),
        (
            {"description": LONG_DESCRIPTION + " Selección para un importante cliente del sector."},
            "BL_INTERMEDIARY",
        ),
        ({"description": LONG_DESCRIPTION + " Requisito: autónomo obligatorio."}, "BL_DESC_TERM"),
        (
            {"title": "Contable junior", "description": "Gestión de facturas y conciliaciones bancarias."},
            "REQ_ANY_MISSING",
        ),
    ],
)
def test_each_rule_discards(rules: GoldenRules, overrides: dict, rule_id: str) -> None:
    assert first_rule(rules, **overrides) == rule_id


@pytest.mark.parametrize(
    "overrides",
    [
        {"date_posted": None},  # sin fecha: no se sabe si es vieja
        {"location_bucket": "unknown", "modality": "onsite"},  # sin ciudad: no se sabe si está fuera
        {"location_bucket": "madrid", "modality": "unknown"},  # sin modalidad: podría ser remoto
        {"location_bucket": "remote", "modality": "remote"},
        {"modality": "remote", "location": "Remote (Europe)"},
        {"modality": "remote", "description": LONG_DESCRIPTION + " Remote from Spain."},
        {"language": "unknown"},
        {"title": "Salesforce Developer IA"},  # "sales" es un término completo, no una subcadena
        {"location_bucket": "torremolinos", "modality": "onsite"},
    ],
)
def test_when_in_doubt_it_passes(rules: GoldenRules, overrides: dict) -> None:
    assert first_rule(rules, **overrides) is None


def test_blacklisted_company_matches_normalized_name(rules: GoldenRules) -> None:
    custom = rules.model_copy(
        update={"blacklists": rules.blacklists.model_copy(update={"companies": ["Acme Labs SL"]})}
    )
    assert first_rule(custom) == "BL_COMPANY"


def test_salary_rule_only_with_known_eur_salary(rules: GoldenRules) -> None:
    custom = rules.model_copy(update={"salary": rules.salary.model_copy(update={"min_annual_eur": 24000})})
    assert first_rule(custom, salary_annual_max=20000.0) == "SAL_BELOW_MIN"
    assert first_rule(custom, salary_annual_max=30000.0) is None
    assert first_rule(custom, salary_annual_max=None) is None
    assert first_rule(custom, salary_annual_max=20000.0, salary_currency="USD") is None


def test_explain_mode_returns_every_rule(rules: GoldenRules) -> None:
    bad = facts(
        title="Senior Engineer", location_bucket="madrid", modality="onsite", date_posted=date(2026, 1, 1)
    )
    assert [h.rule_id for h in evaluate(bad, rules, TODAY)] == ["STALE"]
    assert [h.rule_id for h in evaluate(bad, rules, TODAY, explain=True)] == [
        "STALE",
        "SEN_TITLE",
        "LOC_ONSITE_OUT_OF_AREA",
    ]


def test_discard_explains_why(rules: GoldenRules) -> None:
    result = guillotine(facts(description=LONG_DESCRIPTION + " Mínimo 5 años de experiencia."), rules, TODAY)
    assert not result.passed
    assert result.rule_label == "Pide 5 años (máximo 2)"
    assert result.matched_text and "5 anos" in result.matched_text


def test_rules_version_is_stable_and_content_based(rules: GoldenRules) -> None:
    same = GoldenRules.model_validate(rules.model_dump())
    assert same.version == rules.version
    changed = rules.model_copy(
        update={"experience": rules.experience.model_copy(update={"max_years_required": 3})}
    )
    assert changed.version != rules.version


def test_rules_reject_unknown_fields() -> None:
    with pytest.raises(ValueError):
        GoldenRules.model_validate({"experience": {"max_years": 2}})


@pytest.mark.parametrize(
    ("location", "modality", "rule_id"),
    [
        ("Knoxville, TN, USA", "unknown", "LOC_FOREIGN_COUNTRY"),
        ("Bronx, NY", "unknown", "LOC_FOREIGN_COUNTRY"),  # estado de EE. UU. sin país
        ("Lausanne, Switzerland", "unknown", "LOC_FOREIGN_COUNTRY"),
        ("Berlin, Germany", "hybrid", "LOC_ONSITE_OUT_OF_AREA"),  # la regla de zona va antes
        ("Málaga, Andalusia, Spain", "unknown", None),
        ("Madrid, Spain", "unknown", None),  # en España y sin modalidad: ante la duda, pasa
        ("Berlin", "unknown", None),  # sin país reconocible
        ("Europe", "unknown", None),  # un ámbito no es un país
        (
            "New York, USA",
            "remote",
            None,
        ),  # lo remoto lo decide LOC_REMOTE_SCOPE (sin restricción en el texto)
    ],
)
def test_foreign_country_without_remote(rules: GoldenRules, location: str, modality: str, rule_id) -> None:
    bucket = location.split(",")[0].lower()
    assert first_rule(rules, location=location, location_bucket=bucket, modality=modality) == rule_id


def test_home_countries_are_configurable(rules: GoldenRules) -> None:
    custom = rules.model_copy(
        update={"location": rules.location.model_copy(update={"home_countries": ["spain", "portugal"]})}
    )
    assert (
        first_rule(custom, location="Lisboa, Portugal", location_bucket="lisboa", modality="unknown") is None
    )
