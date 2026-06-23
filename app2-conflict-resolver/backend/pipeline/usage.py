"""Token usage and cost tracking — an append-only ledger of every LLM call.

Each pair analysis appends one line to ``data/usage_log.jsonl``; the API exposes
the aggregate at ``GET /api/usage``. Append-only keeps it crash-safe and makes
the running cost auditable across restarts.
"""
import json
from datetime import datetime, timezone

import anthropic

from .config import COST_INPUT_PER_TOKEN, COST_OUTPUT_PER_TOKEN, MODEL, USAGE_LOG


def log_usage(pair_id: str, usage: anthropic.types.Usage) -> float:
    """Append one call's usage to the ledger and return its dollar cost."""
    cost = (
        usage.input_tokens * COST_INPUT_PER_TOKEN
        + usage.output_tokens * COST_OUTPUT_PER_TOKEN
    )
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pair": pair_id,
        "model": MODEL,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": round(cost, 6),
    }
    with USAGE_LOG.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return cost


def read_usage_log() -> dict:
    """Aggregate the ledger into totals for the /api/usage endpoint."""
    if not USAGE_LOG.exists():
        return {"entries": [], "total_cost_usd": 0.0, "total_input_tokens": 0,
                "total_output_tokens": 0, "call_count": 0}
    entries = [json.loads(l) for l in USAGE_LOG.read_text().splitlines() if l.strip()]
    return {
        "entries": entries,
        "total_cost_usd": round(sum(e["cost_usd"] for e in entries), 4),
        "total_input_tokens": sum(e["input_tokens"] for e in entries),
        "total_output_tokens": sum(e["output_tokens"] for e in entries),
        "call_count": len(entries),
    }
