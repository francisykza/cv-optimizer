import pytest

from hunter.pipeline.normalize import (
    canonical_url,
    clean_description,
    detect_modality,
    detect_offer_language,
    location_bucket,
    normalize,
    normalize_company,
    normalize_title,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Acme Labs S.L.", "acme labs"),
        ("ACME LABS SL", "acme labs"),
        ("Acme Group S.A.U.", "acme"),
        ("Grupo Acme, S.L.U.", "grupo acme"),
        ("Acme Inc.", "acme"),
        ("Datos & Más GmbH", "datos & mas"),
    ],
)
def test_normalize_company(raw: str, expected: str) -> None:
    assert normalize_company(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Junior AI Engineer (m/f/d)", "junior ai engineer"),
        ("Desarrollador/a Python (H/M) [Málaga]", "desarrollador a python"),
        ("Oferta: Data Scientist Jr.", "data scientist jr"),
        ("Senior Backend Engineer - Remote", "senior backend engineer"),
        ("Python Developer | Hybrid", "python developer"),
    ],
)
def test_normalize_title_keeps_level(raw: str, expected: str) -> None:
    assert normalize_title(raw) == expected


@pytest.mark.parametrize(
    ("location", "bucket"),
    [
        ("Málaga, Andalucía, España", "malaga"),
        ("Torremolinos, Andalusia, Spain", "torremolinos"),
        ("Remote", "remote"),
        ("Remoto (España)", "remote"),
        ("España", "unknown"),
        ("", "unknown"),
        ("Madrid, Comunidad de Madrid, España", "madrid"),
        ("Andalucía, España", "unknown"),
        ("29001 Málaga", "malaga"),
        ("Seville, Spain", "sevilla"),
    ],
)
def test_location_bucket(location: str, bucket: str) -> None:
    assert location_bucket(location) == bucket


@pytest.mark.parametrize(
    ("title", "location", "description", "is_remote", "expected"),
    [
        ("Python Dev (Remoto)", "España", "", None, "remote"),
        ("Python Dev", "Málaga", "Modelo híbrido: 2 días en oficina.", None, "hybrid"),
        ("Python Dev", "Málaga", "Trabajo 100% presencial en nuestras oficinas.", None, "onsite"),
        ("Python Dev", "Málaga", "Posición 100% remoto desde cualquier punto de España.", None, "remote"),
        ("Python Dev", "Madrid", "Hybrid role: 3 days per week in office.", None, "hybrid"),
        ("Python Dev", "Madrid", "Nada sobre la modalidad.", None, "unknown"),
        ("Python Dev", "Madrid", "Nada sobre la modalidad.", True, "remote"),
    ],
)
def test_detect_modality(
    title: str, location: str, description: str, is_remote: bool | None, expected: str
) -> None:
    assert detect_modality(title, location, description, is_remote) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://es.linkedin.com/jobs/view/junior-ai-engineer-at-acme-4012345678?trk=public&refId=x",
            "https://www.linkedin.com/jobs/view/4012345678",
        ),
        ("https://www.linkedin.com/jobs/view/4012345678/", "https://www.linkedin.com/jobs/view/4012345678"),
        (
            "https://es.indeed.com/viewjob?jk=ABCDEF0123456789&from=serp",
            "https://www.indeed.com/viewjob?jk=abcdef0123456789",
        ),
        ("https://Example.com/jobs/1/?utm_source=x&b=2&a=1#apply", "https://example.com/jobs/1?a=1&b=2"),
        ("http://www.example.com/", "https://example.com/"),
    ],
)
def test_canonical_url(url: str, expected: str) -> None:
    assert canonical_url(url) == expected


def test_clean_description_strips_html_markdown_and_cookies() -> None:
    raw = (
        "<p>**Buscamos** un perfil <b>junior</b>.</p><ul><li>Python</li><li>SQL</li></ul>"
        "<p>Utilizamos cookies para mejorar tu experiencia.</p>Junior \\- IA &amp; datos"
    )
    text = clean_description(raw)
    assert "<" not in text and "**" not in text
    assert "cookies" not in text
    assert "Buscamos un perfil junior" in text
    assert "Junior - IA & datos" in text


def test_detect_language_marks_german_as_other() -> None:
    german = (
        "Wir suchen eine Person für unser Team. Die Stelle ist in München und wir bieten eine "
        "gute Bezahlung. Sie arbeiten mit Python und der Cloud, das ist nicht schwer, und unsere "
        "Kunden sind auf der ganzen Welt. Ihre Aufgaben werden spannend sein."
    )
    assert detect_offer_language("Python Entwickler", german) == "other"


def test_normalize_builds_keys(make_raw) -> None:
    job = normalize(make_raw(title="Junior AI Engineer (m/f/d)", company="Acme Labs S.L."))
    same = normalize(make_raw(title="Junior AI Engineer", company="ACME LABS SL", url="https://x.com/1"))
    assert job.job_key == same.job_key
    assert len(job.simhash) == 16
    assert job.modality == "unknown"
    assert job.language == "es"


def test_explicit_remote_flag_means_onsite(make_raw) -> None:
    job = normalize(
        make_raw(site="arbeitnow", is_remote=False, location="Berlin", description="Python team.")
    )
    assert job.modality == "onsite"
    jobspy_job = normalize(
        make_raw(site="linkedin", is_remote=False, location="Berlin", description="Python team.")
    )
    assert jobspy_job.modality == "unknown"  # jobspy pone False por defecto: no es un dato
