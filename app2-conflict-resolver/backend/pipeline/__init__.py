"""Offline data pipeline for the regulatory conflict resolver.

Stages: extract (PDFs → text) → analyze (pairwise LLM conflict detection) with
schema validation, quote grounding, retry/backoff and cost logging layered in.
The FastAPI app imports only the two entry points re-exported here; everything
else is an internal stage.
"""
from .analyze import get_analysis
from .usage import read_usage_log

__all__ = ["get_analysis", "read_usage_log"]
