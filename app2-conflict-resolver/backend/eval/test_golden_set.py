"""Pytest wrapper around the golden set, so `pytest` discovers it directly.

    cd backend && pytest

Equivalent to `python -m eval.run_eval` but as parametrised test cases. Skips
(rather than spends money) when the pair caches are cold.
"""
import json
from pathlib import Path

import pytest

from eval.run_eval import _evaluate_case
from pipeline.analyze import all_pair_caches_exist, get_analysis
from pipeline.extract import get_extracted

GOLDEN = json.loads((Path(__file__).parent / "golden_set.json").read_text())


@pytest.fixture(scope="module")
def conflicts():
    if not all_pair_caches_exist(get_extracted()):
        pytest.skip("pair caches cold — run `python -m pipeline.run` first")
    return get_analysis()["conflicts"]


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: c["name"])
def test_golden_conflict_detected(case, conflicts):
    verdict = _evaluate_case(case, conflicts)
    assert verdict["passed"], verdict.get("reason")
