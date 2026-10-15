from hunter.pipeline.dedup import (
    Candidate,
    decide_by_content,
    decide_by_key,
    desc_fingerprint_text,
    hamming,
    simhash_hex,
)
from tests.conftest import LONG_DESCRIPTION


def _hash(text: str) -> str:
    return simhash_hex(desc_fingerprint_text(text))


def test_simhash_is_stable_and_sized() -> None:
    assert _hash(LONG_DESCRIPTION) == _hash(LONG_DESCRIPTION)
    assert len(_hash(LONG_DESCRIPTION)) == 16


def test_short_text_has_no_simhash() -> None:
    assert _hash("Python developer") == ""
    assert hamming("", "ff") is None


def test_small_edit_is_near_duplicate() -> None:
    edited = LONG_DESCRIPTION.replace("horario flexible", "horario muy flexible")
    distance = hamming(_hash(LONG_DESCRIPTION), _hash(edited))
    assert distance is not None and distance <= 12


def test_boilerplate_does_not_change_fingerprint() -> None:
    with_footer = LONG_DESCRIPTION + "\nSomos una empresa comprometida con la igualdad de oportunidades."
    assert _hash(LONG_DESCRIPTION) == _hash(with_footer)


def test_different_offer_is_far() -> None:
    other = (
        "Se necesita mozo de almacén para turno de noche en Antequera. Manejo de carretilla elevadora, "
        "preparación de pedidos, control de inventario y descarga de camiones. Contrato temporal de tres "
        "meses con posibilidad de renovación, incorporación inmediata y salario según convenio del sector."
    )
    distance = hamming(_hash(LONG_DESCRIPTION), _hash(other))
    assert distance is not None and distance > 12


def test_decide_by_key_aliases_similar_or_uncomparable_content() -> None:
    h = _hash(LONG_DESCRIPTION)
    assert decide_by_key(h, [Candidate("a", h)]).job_id == "a"
    assert decide_by_key("", [Candidate("b", h)]).job_id == "b"  # sin texto que comparar: misma oferta
    assert decide_by_key(h, []).duplicate is False


def test_decide_by_key_keeps_distinct_position_with_same_title() -> None:
    far = f"{int(_hash(LONG_DESCRIPTION), 16) ^ 0xFFFF_FFFF:016x}"  # 32 bits distintos
    assert decide_by_key(_hash(LONG_DESCRIPTION), [Candidate("a", far)]).duplicate is False


def test_decide_by_content_picks_closest_and_purged() -> None:
    h = _hash(LONG_DESCRIPTION)
    one_bit = f"{int(h, 16) ^ 1:016x}"
    decision = decide_by_content(
        h, [Candidate("far", f"{int(h, 16) ^ 0xFF:016x}"), Candidate("near", one_bit)]
    )
    assert decision.duplicate and decision.job_id == "near" and decision.layer == "simhash"
    purged = decide_by_content(h, [Candidate(None, h)])
    assert purged.duplicate and purged.job_id is None and purged.layer == "fingerprint"
    assert decide_by_content("", [Candidate("x", h)]).duplicate is False
