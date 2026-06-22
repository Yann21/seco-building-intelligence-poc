"""
Pairwise conflict analysis over regulatory documents.

Architecture: each document pair is analyzed independently and cached by
content fingerprint + prompt version. Adding a new document triggers only
O(n) new LLM calls (new_doc × existing_docs), not a full re-analysis.

Robustness stack:
  - Pydantic schema validation on every LLM response
  - Quote grounding: verifies cited quotes appear in source text
  - Retry with exponential backoff on transient API errors
  - Append-only usage_log.jsonl for cost tracking
"""
import hashlib
import json
import os
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import anthropic
import json_repair
from pydantic import BaseModel, field_validator

from extract import get_extracted

# ── Config ────────────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-6"
PROMPT_VERSION = "v2"  # bump to invalidate all pair caches

COST_INPUT_PER_TOKEN = 3 / 1_000_000   # $3 / MTok
COST_OUTPUT_PER_TOKEN = 15 / 1_000_000  # $15 / MTok

CACHE_DIR = Path(__file__).parent / "cache"
USAGE_LOG = Path(__file__).parent / "usage_log.jsonl"
ANALYSIS_CACHE = Path(__file__).parent / "analysis.json"

# ── Pydantic output schema ─────────────────────────────────────────────────────

class ConflictSource(BaseModel):
    doc_id: str
    article: str
    quote: str = ""
    value: str | None = None


class Conflict(BaseModel):
    id: str
    title: str
    topic: str
    severity: Literal["critique", "majeur", "mineur"]
    type: Literal["contradiction", "lacune", "ambiguïté", "ambiguité"]
    description: str
    sources: list[ConflictSource]
    recommendation: str
    practical_impact: str | None = None
    quote_verified: bool = False

    @field_validator("severity", mode="before")
    @classmethod
    def normalise_severity(cls, v: str) -> str:
        return v.lower().strip()


class PairResult(BaseModel):
    conflicts: list[Conflict]


# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es un expert en réglementation de la construction et de la sécurité au travail au Luxembourg.
Tu analyses des paires de documents réglementaires officiels pour identifier les conflits, lacunes et incohérences
qui peuvent affecter la conception d'un bâtiment ou d'un chantier.

Pour chaque conflit identifié, tu fournis:
1. Le sujet précis du conflit
2. Ce que dit chaque document (avec numéro d'article et citation exacte)
3. La recommandation: quelle valeur appliquer (toujours la plus contraignante)
4. Le niveau de criticité (critique / majeur / mineur)
5. Le type de conflit (contradiction / lacune / ambiguïté)
"""

PAIR_PROMPT = """Voici deux documents réglementaires luxembourgeois:

{doc_sections}

---

Analyse ces deux documents et identifie TOUS les conflits, contradictions, lacunes et ambiguïtés entre eux.
Concentre-toi sur:
- Les valeurs numériques contradictoires (lux, durées, fréquences)
- Les ambiguïtés terminologiques qui peuvent mener à des erreurs de conception
- Les lacunes (un document couvre un cas que l'autre ignore)
- Les exigences contradictoires pour un même contexte

Si tu n'identifies aucun conflit réel entre ces deux documents, retourne une liste vide.

Réponds en JSON strict:
{{
  "conflicts": [
    {{
      "id": "C1",
      "title": "Titre court du conflit",
      "topic": "maintenance | illuminance | terminologie | autonomie | délai",
      "severity": "critique | majeur | mineur",
      "type": "contradiction | lacune | ambiguïté",
      "description": "Description claire du problème pour un architecte ou ingénieur",
      "sources": [
        {{
          "doc_id": "<id exact du document>",
          "article": "Art. X.Y",
          "quote": "Citation exacte du texte source",
          "value": "Valeur ou exigence spécifique"
        }}
      ],
      "recommendation": "Ce qu'il faut appliquer et pourquoi",
      "practical_impact": "Impact concret sur la conception ou la maintenance"
    }}
  ]
}}
"""


# ── Quote grounding ────────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


def verify_quotes(conflicts: list[Conflict], docs: dict) -> list[Conflict]:
    """
    Fuzzy-check that each cited quote's words appear in the source document.
    Threshold: 65% word overlap (tolerates OCR noise and minor text variations).
    Conflicts with unverifiable quotes are flagged, not removed.
    """
    for conflict in conflicts:
        all_ok = True
        for src in conflict.sources:
            doc = docs.get(src.doc_id)
            if not doc or not src.quote:
                continue
            doc_text = _normalise(doc.get("full_text", ""))
            quote_words = set(_normalise(src.quote).split())
            if len(quote_words) < 4:
                continue  # too short to verify meaningfully
            found = sum(1 for w in quote_words if w in doc_text)
            if found / len(quote_words) < 0.65:
                all_ok = False
        conflict.quote_verified = all_ok
    return conflicts


# ── Cost tracking ─────────────────────────────────────────────────────────────

def _log_usage(pair_id: str, usage: anthropic.types.Usage) -> float:
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
    if not USAGE_LOG.exists():
        return {"entries": [], "total_cost_usd": 0.0, "total_input_tokens": 0, "total_output_tokens": 0, "call_count": 0}
    entries = [json.loads(l) for l in USAGE_LOG.read_text().splitlines() if l.strip()]
    return {
        "entries": entries,
        "total_cost_usd": round(sum(e["cost_usd"] for e in entries), 4),
        "total_input_tokens": sum(e["input_tokens"] for e in entries),
        "total_output_tokens": sum(e["output_tokens"] for e in entries),
        "call_count": len(entries),
    }


# ── Per-pair analysis ─────────────────────────────────────────────────────────

def _doc_hash(doc: dict) -> str:
    return hashlib.sha256(doc["full_text"].encode()).hexdigest()[:12]


def _pair_cache_path(doc_a: dict, doc_b: dict) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    key = "_".join(sorted([_doc_hash(doc_a), _doc_hash(doc_b)]))
    return CACHE_DIR / f"{key}_{PROMPT_VERSION}.json"


def _extract_json_block(text: str) -> str:
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}") + 1
    if start != -1 and end > start:
        return text[start:end]
    return text.strip()


def run_pair(doc_a: dict, doc_b: dict, client: anthropic.Anthropic, force: bool = False) -> dict:
    """Analyze one document pair, using cache unless force=True or content changed."""
    cache_path = _pair_cache_path(doc_a, doc_b)
    pair_id = f"{doc_a['id']} × {doc_b['id']}"

    if cache_path.exists() and not force:
        print(f"  cache hit:  {pair_id}")
        return json.loads(cache_path.read_text())

    print(f"  analyzing:  {pair_id}")
    doc_sections = ""
    for doc in [doc_a, doc_b]:
        doc_sections += (
            f"\n\n{'='*60}\n"
            f"DOCUMENT: {doc['title']}\n"
            f"Autorité: {doc['authority']} | Date: {doc['date']}\n"
            f"{'='*60}\n\n"
            f"{doc['full_text']}"
        )

    prompt = PAIR_PROMPT.format(doc_sections=doc_sections)

    # Retry with exponential backoff
    message = None
    last_err = None
    for attempt in range(3):
        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=4000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except (anthropic.RateLimitError, anthropic.InternalServerError) as e:
            last_err = e
            wait = 2 ** attempt
            print(f"  retry {attempt + 1}/3 in {wait}s ({e})")
            time.sleep(wait)

    if message is None:
        raise last_err  # type: ignore[misc]

    cost = _log_usage(pair_id, message.usage)

    raw = _extract_json_block(message.content[0].text)
    data = json_repair.repair_json(raw, return_objects=True)

    # Pydantic validation — degrade gracefully on schema errors
    try:
        parsed = PairResult(**data)
        conflicts = [c.model_dump() for c in parsed.conflicts]
    except Exception as e:
        print(f"  schema warning ({pair_id}): {e}")
        conflicts = data.get("conflicts", []) if isinstance(data, dict) else []

    result = {
        "conflicts": conflicts,
        "_pair_id": pair_id,
        "_cost_usd": cost,
        "_prompt_version": PROMPT_VERSION,
        "_cached_at": datetime.now(timezone.utc).isoformat(),
    }
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# ── Merge & top-level entry point ─────────────────────────────────────────────

def _cluster_pairs(docs: dict) -> list[tuple[dict, dict]]:
    """
    Return all (doc_a, doc_b) pairs where both docs share the same cluster.
    Cross-cluster pairs are never analyzed — documents in different topic areas
    (e.g. lighting vs. fire-safety) have no meaningful regulatory overlap.
    """
    from collections import defaultdict
    clusters: dict[str, list[dict]] = defaultdict(list)
    for doc in docs.values():
        clusters[doc.get("cluster", "default")].append(doc)
    pairs = []
    for cluster_docs in clusters.values():
        for i in range(len(cluster_docs)):
            for j in range(i + 1, len(cluster_docs)):
                pairs.append((cluster_docs[i], cluster_docs[j]))
    return pairs


def _all_pair_caches_exist(docs: dict) -> bool:
    return all(_pair_cache_path(a, b).exists() for a, b in _cluster_pairs(docs))


def get_analysis(force: bool = False) -> dict:
    """
    Run pairwise analysis within each document cluster.

    Only documents in the same subfolder (cluster) are compared — a lighting
    regulation is never paired against a fire-safety document.

    With force=False: pair caches are reused if doc content unchanged.
    Fast path serves from analysis.json when all cluster-pair caches are warm.
    With force=True: all pair caches are busted and Claude is called fresh.
    """
    docs = get_extracted()

    # Fast path: serve from analysis.json when everything is up-to-date
    if not force and ANALYSIS_CACHE.exists():
        try:
            cached = json.loads(ANALYSIS_CACHE.read_text())
            if (cached.get("_meta", {}).get("prompt_version") == PROMPT_VERSION
                    and _all_pair_caches_exist(docs)):
                return cached
        except Exception:
            pass

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    pairs = _cluster_pairs(docs)
    all_conflicts: list[dict] = []
    total_cost = 0.0

    # Group clusters for logging
    from collections import defaultdict
    by_cluster: dict[str, list] = defaultdict(list)
    for a, b in pairs:
        by_cluster[a["cluster"]].append((a, b))

    for cluster_name, cluster_pairs in by_cluster.items():
        print(f"\nCluster '{cluster_name}' — {len(cluster_pairs)} pair(s)")
        for doc_a, doc_b in cluster_pairs:
            pair = run_pair(doc_a, doc_b, client, force=force)
            prefix = f"{doc_a['id'][:8]}-{doc_b['id'][:8]}"
            for idx, c in enumerate(pair["conflicts"]):
                c["id"] = f"{prefix}-{c.get('id', str(idx))}"
            all_conflicts.extend(pair["conflicts"])
            total_cost += pair.get("_cost_usd", 0.0)

    # Pydantic validation pass — filter out malformed conflicts
    validated: list[Conflict] = []
    for c in all_conflicts:
        try:
            validated.append(Conflict(**c))
        except Exception as e:
            print(f"  skipping malformed conflict: {e}")

    # Quote grounding
    verified = verify_quotes(validated, docs)

    by_severity = {
        "critique": sum(1 for c in verified if c.severity == "critique"),
        "majeur": sum(1 for c in verified if c.severity == "majeur"),
        "mineur": sum(1 for c in verified if c.severity == "mineur"),
    }
    unverified_count = sum(1 for c in verified if not c.quote_verified)
    n_clusters = len(by_cluster)

    summary = (
        f"Analyse de {len(docs)} documents en {n_clusters} cluster(s) ({len(pairs)} paires intra-cluster): "
        f"{len(verified)} conflits — "
        f"{by_severity['critique']} critiques, {by_severity['majeur']} majeurs, {by_severity['mineur']} mineurs."
    )
    if unverified_count:
        summary += f" {unverified_count} conflit(s) avec citations non retrouvées dans les sources."

    result = {
        "summary": summary,
        "conflicts": [c.model_dump() for c in verified],
        "documents": {
            d["id"]: {k: v for k, v in d.items() if k not in ("pages", "full_text")}
            for d in docs.values()
        },
        "_meta": {
            "prompt_version": PROMPT_VERSION,
            "model": MODEL,
            "total_cost_usd": round(total_cost, 4),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "quote_verified": len(verified) - unverified_count,
            "quote_unverified": unverified_count,
            "pair_count": len(pairs),
            "cluster_count": n_clusters,
        },
    }

    ANALYSIS_CACHE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    import sys
    result = get_analysis(force="--force" in sys.argv)
    meta = result.get("_meta", {})
    print(f"\nConflicts: {len(result['conflicts'])}")
    print(f"Cost: ${meta.get('total_cost_usd', 0):.4f}")
    print(f"Quote verified: {meta.get('quote_verified')}/{len(result['conflicts'])}")
    for c in result["conflicts"]:
        tag = "✓" if c.get("quote_verified") else "?"
        print(f"  [{c['severity'].upper()}][{tag}] {c['title']}")
