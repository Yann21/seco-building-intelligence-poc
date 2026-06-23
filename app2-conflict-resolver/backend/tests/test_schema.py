"""Schema validation — the first robustness layer."""
import pytest

from pipeline.schema import Conflict, ConflictSource, PairResult


def _conflict(**over):
    base = dict(
        id="C1", title="t", topic="illuminance", severity="majeur",
        type="contradiction", description="d",
        sources=[{"doc_id": "X", "article": "Art. 1", "quote": "q", "value": "10"}],
        recommendation="r",
    )
    base.update(over)
    return base


def test_valid_conflict_parses():
    c = Conflict(**_conflict())
    assert c.severity == "majeur"
    assert c.sources[0].doc_id == "X"
    assert c.quote_verified is False  # default


def test_severity_is_normalised():
    assert Conflict(**_conflict(severity="  CRITIQUE ")).severity == "critique"


def test_bad_severity_rejected():
    with pytest.raises(Exception):
        Conflict(**_conflict(severity="urgent"))


def test_missing_required_field_rejected():
    d = _conflict()
    del d["title"]
    with pytest.raises(Exception):
        Conflict(**d)


def test_source_optional_fields_default():
    s = ConflictSource(doc_id="X", article="Art. 1")
    assert s.quote == "" and s.value is None


def test_pairresult_wraps_conflict_list():
    pr = PairResult(conflicts=[_conflict(), _conflict(id="C2")])
    assert len(pr.conflicts) == 2
