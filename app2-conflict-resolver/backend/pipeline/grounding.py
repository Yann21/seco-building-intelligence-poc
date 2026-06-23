"""Quote grounding — the second layer of the robustness stack.

Each quote the model cites is fuzzy-matched against its source document. Quotes
that cannot be located are flagged (``quote_verified=False``), not discarded:
a real conflict with a paraphrased citation is still worth surfacing, just with
a warning. This catches hallucinated citations without throwing away signal.
"""
import unicodedata

from .schema import Conflict

# Word-overlap threshold. Tolerant of OCR noise and minor transcription drift;
# a value to tune against a labelled set once real false-pos/neg rates exist.
MATCH_THRESHOLD = 0.65
MIN_QUOTE_WORDS = 4  # shorter quotes are too generic to verify meaningfully


def normalise(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


def verify_quotes(conflicts: list[Conflict], docs: dict) -> list[Conflict]:
    """Set ``quote_verified`` on each conflict by checking its cited quotes.

    A conflict is verified only if every citation long enough to check is found
    in its source document above the overlap threshold.
    """
    for conflict in conflicts:
        all_ok = True
        for src in conflict.sources:
            doc = docs.get(src.doc_id)
            if not doc or not src.quote:
                continue
            doc_text = normalise(doc.get("full_text", ""))
            quote_words = set(normalise(src.quote).split())
            if len(quote_words) < MIN_QUOTE_WORDS:
                continue
            found = sum(1 for w in quote_words if w in doc_text)
            if found / len(quote_words) < MATCH_THRESHOLD:
                all_ok = False
        conflict.quote_verified = all_ok
    return conflicts
