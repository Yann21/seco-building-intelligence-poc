"""Stage 2 — pairwise conflict analysis over the document corpus.

Each document pair is analysed independently and cached by content fingerprint
+ prompt version:

    cache key = sha256(text_A)[:12] + "_" + sha256(text_B)[:12] + "_" + PROMPT_VERSION

Adding one document to a cluster of size C costs C-1 new LLM calls, not a full
rebuild — every other pair is a cache hit. Cross-cluster pairs are never run.

The robustness layers (Pydantic schema, quote grounding, retry/backoff, prompt
versioning) live in sibling modules; this file orchestrates them.
"""

import hashlib
import json
import os
import time
from collections import defaultdict
from datetime import UTC, datetime

import anthropic
import json_repair

from .config import ANALYSIS_CACHE, CACHE_DIR, MODEL, PROMPT_VERSION
from .extract import get_extracted
from .grounding import verify_quotes
from .schema import Conflict, PairResult
from .usage import log_usage

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


# ── Per-pair analysis ─────────────────────────────────────────────────────────


def _doc_hash(doc: dict) -> str:
    return hashlib.sha256(doc["full_text"].encode()).hexdigest()[:12]


def _pair_cache_path(doc_a: dict, doc_b: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
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
    """Analyse one document pair, using cache unless force=True or content changed."""
    cache_path = _pair_cache_path(doc_a, doc_b)
    pair_id = f"{doc_a['id']} × {doc_b['id']}"

    if cache_path.exists() and not force:
        print(f"  cache hit:  {pair_id}")
        return json.loads(cache_path.read_text())

    print(f"  analyzing:  {pair_id}")
    doc_sections = ""
    for doc in [doc_a, doc_b]:
        doc_sections += (
            f"\n\n{'=' * 60}\n"
            f"DOCUMENT: {doc['title']}\n"
            f"Autorité: {doc['authority']} | Date: {doc['date']}\n"
            f"{'=' * 60}\n\n"
            f"{doc['full_text']}"
        )

    prompt = PAIR_PROMPT.format(doc_sections=doc_sections)

    # Retry with exponential backoff on transient API errors (layer 3).
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
            wait = 2**attempt
            print(f"  retry {attempt + 1}/3 in {wait}s ({e})")
            time.sleep(wait)

    if message is None:
        raise last_err  # type: ignore[misc]

    cost = log_usage(pair_id, message.usage)

    raw = _extract_json_block(message.content[0].text)
    data = json_repair.repair_json(raw, return_objects=True)

    # Pydantic validation (layer 1) — degrade gracefully on schema errors.
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
        "_cached_at": datetime.now(UTC).isoformat(),
    }
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# ── Cluster pairing & merge ───────────────────────────────────────────────────


def cluster_pairs(docs: dict) -> list[tuple[dict, dict]]:
    """All (doc_a, doc_b) pairs where both share a cluster.

    Cross-cluster pairs are never analysed — documents in different topic areas
    (e.g. lighting vs. fire-safety) have no meaningful regulatory overlap.
    """
    clusters: dict[str, list[dict]] = defaultdict(list)
    for doc in docs.values():
        clusters[doc.get("cluster", "default")].append(doc)
    pairs = []
    for cluster_docs in clusters.values():
        for i in range(len(cluster_docs)):
            for j in range(i + 1, len(cluster_docs)):
                pairs.append((cluster_docs[i], cluster_docs[j]))
    return pairs


def all_pair_caches_exist(docs: dict) -> bool:
    return all(_pair_cache_path(a, b).exists() for a, b in cluster_pairs(docs))


def get_analysis(force: bool = False) -> dict:
    """Run pairwise analysis within each cluster and merge into one result.

    With force=False: warm pair caches are reused if document content is
    unchanged, and the merged result is served straight from analysis.json when
    every cluster pair is cached (no API key required on this path).
    With force=True: every pair cache is busted and Claude is called fresh.
    """
    docs = get_extracted()

    # Fast path: serve the merged result when everything is up to date.
    if not force and ANALYSIS_CACHE.exists():
        try:
            cached = json.loads(ANALYSIS_CACHE.read_text())
            if cached.get("_meta", {}).get(
                "prompt_version"
            ) == PROMPT_VERSION and all_pair_caches_exist(docs):
                return cached
        except Exception:
            pass

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    pairs = cluster_pairs(docs)
    by_cluster: dict[str, list] = defaultdict(list)
    for a, b in pairs:
        by_cluster[a["cluster"]].append((a, b))

    all_conflicts: list[dict] = []
    total_cost = 0.0
    for cluster_name, cluster_pair_list in by_cluster.items():
        print(f"\nCluster '{cluster_name}' — {len(cluster_pair_list)} pair(s)")
        for doc_a, doc_b in cluster_pair_list:
            pair = run_pair(doc_a, doc_b, client, force=force)
            prefix = f"{doc_a['id']}__{doc_b['id']}"
            for idx, c in enumerate(pair["conflicts"]):
                c["id"] = f"{prefix}-{c.get('id', str(idx))}"
            all_conflicts.extend(pair["conflicts"])
            total_cost += pair.get("_cost_usd", 0.0)

    # Validation pass (layer 1) — drop malformed conflicts.
    validated: list[Conflict] = []
    for c in all_conflicts:
        try:
            validated.append(Conflict(**c))
        except Exception as e:
            print(f"  skipping malformed conflict: {e}")

    verified = verify_quotes(validated, docs)  # layer 2

    by_severity = {
        sev: sum(1 for c in verified if c.severity == sev)
        for sev in ("critique", "majeur", "mineur")
    }
    unverified_count = sum(1 for c in verified if not c.quote_verified)
    n_clusters = len(by_cluster)

    summary = (
        f"Analyse de {len(docs)} documents en {n_clusters} cluster(s) "
        f"({len(pairs)} paires intra-cluster): {len(verified)} conflits — "
        f"{by_severity['critique']} critiques, {by_severity['majeur']} majeurs, "
        f"{by_severity['mineur']} mineurs."
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
            "analyzed_at": datetime.now(UTC).isoformat(),
            "quote_verified": len(verified) - unverified_count,
            "quote_unverified": unverified_count,
            "pair_count": len(pairs),
            "cluster_count": n_clusters,
        },
    }
    ANALYSIS_CACHE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result
