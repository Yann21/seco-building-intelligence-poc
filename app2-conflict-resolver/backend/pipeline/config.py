"""Central configuration: model, prompt version, costs, and data paths.

All generated artifacts live under ``backend/data/`` (git-ignored, fully
reproducible via ``python -m pipeline.run``). Keeping every path in one module
means the API, the pipeline, and the eval harness resolve the same locations —
no path drift between who-writes and who-reads.
"""
from pathlib import Path

# ── LLM ───────────────────────────────────────────────────────────────────────
MODEL = "claude-sonnet-4-6"
PROMPT_VERSION = "v2"  # bump to invalidate every pair cache at once

COST_INPUT_PER_TOKEN = 3 / 1_000_000    # $3  / MTok (Sonnet)
COST_OUTPUT_PER_TOKEN = 15 / 1_000_000  # $15 / MTok (Sonnet)

# ── Paths ─────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent   # pipeline/ -> backend/
DOCS_DIR = BACKEND_DIR.parent / "documents"            # source PDFs (per cluster)
DATA_DIR = BACKEND_DIR / "data"                        # generated artifacts

EXTRACTED_CACHE = DATA_DIR / "extracted.json"          # PDF text, per document
ANALYSIS_CACHE = DATA_DIR / "analysis.json"            # merged conflict set
CACHE_DIR = DATA_DIR / "cache"                         # one file per document pair
USAGE_LOG = DATA_DIR / "usage_log.jsonl"               # append-only cost ledger

DATA_DIR.mkdir(parents=True, exist_ok=True)
