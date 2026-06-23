"""CLI entry point — rebuild the conflict analysis from the document corpus.

    python -m pipeline.run            # reuse warm pair caches, call API only for new pairs
    python -m pipeline.run --force    # bust every pair cache and re-call the LLM

Run from the ``backend/`` directory so the ``pipeline`` package is importable.
"""
import sys

from .analyze import get_analysis


def main() -> None:
    result = get_analysis(force="--force" in sys.argv)
    meta = result.get("_meta", {})
    print(f"\nConflicts: {len(result['conflicts'])}")
    print(f"Cost: ${meta.get('total_cost_usd', 0):.4f}")
    print(f"Quote verified: {meta.get('quote_verified')}/{len(result['conflicts'])}")
    for c in result["conflicts"]:
        tag = "✓" if c.get("quote_verified") else "?"
        print(f"  [{c['severity'].upper()}][{tag}] {c['title']}")


if __name__ == "__main__":
    main()
