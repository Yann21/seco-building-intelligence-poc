"""Golden-set regression eval — does the pipeline still find the known conflicts?

Prompt tweaks, model swaps and refactors can silently degrade detection quality.
This harness pins the high-value, human-verified conflicts (``golden_set.json``)
and fails loudly if any stops being detected, drops below its severity floor, or
loses its characteristic evidence.

    python -m eval.run_eval        # run from backend/, exits non-zero on failure

It runs against the *current* merged analysis. With warm pair caches that is
offline and free (no API key); cold caches would require a build first, so the
eval refuses rather than silently spending money.
"""
import json
import sys
from pathlib import Path

from pipeline.analyze import all_pair_caches_exist, get_analysis
from pipeline.extract import get_extracted
from pipeline.grounding import normalise

GOLDEN_PATH = Path(__file__).parent / "golden_set.json"
SEVERITY_RANK = {"mineur": 1, "majeur": 2, "critique": 3}


def _searchable(conflict: dict) -> str:
    """All human-readable text of a conflict, accent-normalised, for matching."""
    parts = [
        conflict.get("title", ""),
        conflict.get("description", ""),
        conflict.get("recommendation", ""),
        conflict.get("practical_impact", "") or "",
        conflict.get("topic", ""),
    ]
    for src in conflict.get("sources", []):
        parts += [src.get("article", ""), src.get("quote", ""), src.get("value", "") or ""]
    return normalise(" ".join(parts))


def _pair_conflicts(conflicts: list[dict], pair: list[str]) -> list[dict]:
    """Conflicts whose id prefix matches this document pair (either order)."""
    a, b = pair
    prefixes = (f"{a}__{b}-", f"{b}__{a}-")
    return [c for c in conflicts if c.get("id", "").startswith(prefixes)]


def _evaluate_case(case: dict, conflicts: list[dict]) -> dict:
    """Return a verdict dict for one golden case."""
    candidates = _pair_conflicts(conflicts, case["pair"])
    keywords = [normalise(k) for k in case["keywords"]]
    floor = SEVERITY_RANK[case["min_severity"]]

    best = None
    for c in candidates:
        text = _searchable(c)
        hits = [k for k in keywords if k in text]
        if len(hits) >= case["min_keyword_hits"]:
            # Prefer the highest-severity matching conflict.
            rank = SEVERITY_RANK.get(c.get("severity", ""), 0)
            if best is None or rank > best["rank"]:
                best = {"conflict": c, "hits": hits, "rank": rank}

    if best is None:
        reason = (
            "no conflict on this pair" if not candidates
            else f"{len(candidates)} conflict(s) on pair, none with >={case['min_keyword_hits']} keywords"
        )
        return {"name": case["name"], "passed": False, "reason": reason}

    sev = best["conflict"].get("severity", "?")
    if best["rank"] < floor:
        return {"name": case["name"], "passed": False,
                "reason": f"severity {sev} below floor {case['min_severity']}"}

    return {
        "name": case["name"],
        "passed": True,
        "severity": sev,
        "verified": best["conflict"].get("quote_verified", False),
        "hits": best["hits"],
    }


def main() -> int:
    docs = get_extracted()
    if not all_pair_caches_exist(docs):
        print("✗ pair caches are cold — build first: `python -m pipeline.run`")
        return 2

    analysis = get_analysis()  # fast path, offline
    conflicts = analysis["conflicts"]
    golden = json.loads(GOLDEN_PATH.read_text())
    cases = golden["cases"]

    print(f"Golden-set eval — {len(cases)} cases against {len(conflicts)} detected conflicts\n")
    results = [_evaluate_case(c, conflicts) for c in cases]

    passed = 0
    for r in results:
        if r["passed"]:
            passed += 1
            tag = "✓ verified" if r["verified"] else "⚠ quote-unverified"
            print(f"  PASS  {r['name']:<42} [{r['severity']}] {tag}")
            print(f"        matched on: {', '.join(r['hits'])}")
        else:
            print(f"  FAIL  {r['name']:<42} {r['reason']}")

    print(f"\n{passed}/{len(cases)} golden conflicts detected.")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
