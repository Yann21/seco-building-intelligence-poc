"""Cost ledger — aggregation and append."""
import json
from types import SimpleNamespace

from pipeline import usage


def test_read_usage_log_aggregates(tmp_path, monkeypatch):
    log = tmp_path / "usage.jsonl"
    rows = [
        {"cost_usd": 0.10, "input_tokens": 10, "output_tokens": 2},
        {"cost_usd": 0.20, "input_tokens": 5, "output_tokens": 3},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(usage, "USAGE_LOG", log)

    agg = usage.read_usage_log()
    assert agg["call_count"] == 2
    assert round(agg["total_cost_usd"], 4) == 0.30
    assert agg["total_input_tokens"] == 15
    assert agg["total_output_tokens"] == 5


def test_read_usage_log_missing_file_is_zeroed(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "USAGE_LOG", tmp_path / "absent.jsonl")
    agg = usage.read_usage_log()
    assert agg["call_count"] == 0 and agg["total_cost_usd"] == 0.0


def test_log_usage_appends_and_returns_cost(tmp_path, monkeypatch):
    log = tmp_path / "usage.jsonl"
    monkeypatch.setattr(usage, "USAGE_LOG", log)
    cost = usage.log_usage("A × B", SimpleNamespace(input_tokens=1000, output_tokens=100))
    assert cost > 0
    entry = json.loads(log.read_text().splitlines()[0])
    assert entry["pair"] == "A × B"
    assert entry["input_tokens"] == 1000
