"""Quote grounding — the second robustness layer."""
from pipeline.grounding import normalise, verify_quotes
from pipeline.schema import Conflict

DOCS = {"D": {"full_text": "Les essais de l'éclairage de secours sont effectués tous les trois mois."}}


def _conflict(quote):
    return Conflict(
        id="C1", title="t", topic="x", severity="majeur", type="contradiction",
        description="d", recommendation="r",
        sources=[{"doc_id": "D", "article": "a", "quote": quote, "value": None}],
    )


def test_normalise_strips_accents_and_case_and_whitespace():
    assert normalise("Éclairage   DE  Secours") == "eclairage de secours"


def test_quote_found_marks_verified():
    out = verify_quotes([_conflict("essais éclairage secours tous les trois mois")], DOCS)
    assert out[0].quote_verified is True


def test_quote_absent_marks_unverified():
    out = verify_quotes([_conflict("la ventilation assure trente metres cubes par heure minimum")], DOCS)
    assert out[0].quote_verified is False


def test_quote_too_short_is_skipped_not_failed():
    # < 4 words is too generic to verify → skipped, conflict stays verified
    assert verify_quotes([_conflict("trois mois")], DOCS)[0].quote_verified is True


def test_unknown_doc_id_does_not_fail():
    c = Conflict(
        id="C1", title="t", topic="x", severity="mineur", type="lacune",
        description="d", recommendation="r",
        sources=[{"doc_id": "MISSING", "article": "a", "quote": "some long quote here", "value": None}],
    )
    assert verify_quotes([c], DOCS)[0].quote_verified is True
