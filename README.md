# Building Intelligence PoC — SECO

**Live demos:** [seco1 – PAG Zone Map](https://yannhoffmann.com/seco1) · [seco2 – Conflict Resolver](https://yannhoffmann.com/seco2)

---

## What problem, for whom?

Construction projects in Luxembourg touch a web of overlapping regulatory texts — ITM workplace safety prescriptions, PAG urban planning rules, European norms, communal supplements. These documents were written by different authorities at different dates and are never cross-referenced. When values contradict (e.g. emergency lighting test frequency: 3 months in one text, 6 months in another), the architect or site engineer has no systematic way to know, and defaults to the wrong one.

**App 2 — Regulatory Conflict Resolver** surfaces those contradictions automatically. The target user is a SECO inspector or an architect preparing a building permit dossier: someone who needs to know *which value to apply* when two binding texts disagree.

**App 1 — PAG Zone Map** addresses a related pain: understanding what's allowed on a given parcel before even starting design. It maps the full PAG zoning of Luxembourg and surfaces the applicable rules, required documents, and SECO control points on a single click.

---

## Why is this relevant to SECO?

SECO's core value is independent technical control. A conflict between two regulations is exactly the kind of ambiguity that generates liability exposure for clients and work for inspectors. Surfacing it early — at design stage rather than at the CTC visit — shortens feedback loops and prevents rework. The resolution workflow (expert documents their decision) also starts building an auditable knowledge base of how conflicts have been resolved in practice, which is the longer-term product.

---

## Data sources

| Source | Used in | Why |
|---|---|---|
| ITM-CL-55.2, ITM-ET-32.10, ITM-CL-144.1 (PDFs, public ITM website) | App 2 | Three lighting regulations from the same authority with known overlaps — good test case for the conflict detection approach |
| PAG Zonage + NQ-PAP (GeoJSON, geoportail.lu open data) | App 1 | Official national zoning dataset, refreshed by communes; the only authoritative source for parcel classification |
| RGD 28 juillet 2011 (zone rules, coded manually) | App 1 | The grand-ducal regulation defining zone types; static enough to encode as a lookup table for the PoC |

---

## Technical decisions and trade-offs

### App 2 architecture: pairwise document index

The naive approach — dump all documents into one prompt — works for a handful of texts but breaks at scale: context grows as O(n), cost grows as O(n), and a single API failure invalidates everything.

The implemented model is a **pairwise analysis matrix**. Each document pair `(A, B)` is analyzed independently and cached by content fingerprint:

```
cache key = sha256(text_A)[:12] + "_" + sha256(text_B)[:12] + "_" + PROMPT_VERSION
```

When a new document `D` is added to an index of `n` existing documents, only `2n − 1` new LLM calls are needed (the new pairs involving `D`). All existing pair results are cache hits. The merged conflict set is rebuilt from the pair cache — no API calls on warm restarts.

**Trade-off accepted:** pairwise analysis misses conflicts that only emerge from three-way interactions (A says X, B says Y, C resolves it). In practice those are rare and can be caught in a second-pass synthesis step if needed. The scalability gain is worth it.

### AI robustness stack

Every LLM call goes through four layers before its output is persisted:

**1. Structured output validation (Pydantic)**
The response is parsed against a strict schema (`Conflict`, `ConflictSource`). Required fields are enforced; `severity` is constrained to `critique | majeur | mineur`. Malformed conflicts are logged and dropped, not silently served. This prevents schema drift between prompt iterations from corrupting stored results.

**2. Quote grounding check**
Each cited quote is fuzzy-matched against the source document text (65% word-overlap threshold, accent-normalised). Conflicts where the quote cannot be located in the source are flagged `quote_verified: false` in the API response and shown with a warning badge in the UI. This catches hallucinated citations without discarding potentially valid conflicts.

**3. Retry with exponential backoff**
Every API call is wrapped in a 3-attempt retry loop (1 s → 2 s → 4 s) on `RateLimitError` and `InternalServerError`. Transient failures are logged; permanent failures surface as a 500 with the original error.

**4. Prompt versioning**
`PROMPT_VERSION` is embedded in the cache key. Bumping it (e.g. `v2 → v3`) automatically invalidates all pair caches on the next run without requiring a manual cache flush.

### Data confidentiality and LLM deployment tiers

The current production path sends document text to the Anthropic API. For a technical inspection firm this creates a confidentiality exposure: client project data, unpublished permit dossiers, or proprietary inspection reports would transit external servers. Three deployment tiers address this at increasing infrastructure cost:

| Tier | Stack | Confidentiality | Cost per analysis | Quality |
|---|---|---|---|---|
| 1 · API | Claude claude-sonnet-4-6 (Anthropic) | Data leaves network | ~$0.35 | Best |
| 2 · CPU local | Ollama + phi3.5 / llama3.2:3b | Fully air-gapped | $0.00 | Reduced |
| 3 · GPU private | Mistral 7B on g4dn.xlarge / T4 | Private VPC | ~$0.01 on-demand | Good |

Tier 2 (CPU) is viable for a confidentiality-first deployment: a quantized 3.8B model runs on any developer machine, data never leaves the process, and the pairwise cache means inference only runs on new document pairs. Quality degrades on complex legal French — the benchmark document (`documentation/llm_benchmark.html`) provides a human-auditable side-by-side comparison for experts to validate.

Tier 3 is the right balance for an internal SECO deployment: a private GPU instance (or on-premises RTX-class workstation) delivers near-API quality at ~40× lower marginal cost, with no external data transfer. See `documentation/costing.html` for the full breakdown including g4dn.xlarge spin-up cost projections.

### API dependency and cost model

Token counts are measured with the Anthropic `count_tokens` API (non-billable) and costs extrapolated across corpus sizes. See [`documentation/costing.html`](documentation/costing.html) for the full breakdown — per-document token counts, pair-by-pair cost table, and extrapolation to 100-document indices.

All live token usage and cost is logged to `usage_log.jsonl` and exposed at `GET /api/usage`.

---

## What goes to production tomorrow vs. what gets thrown away

**Ship tomorrow:**
- The conflict detection and resolution workflow — the core loop works and produces actionable output
- The pairwise cache architecture — it's the right model for an incrementally growing document corpus

**Throw away:**
- The static `zone_rules.py` lookup table in App 1 — it needs to be replaced by parsing the actual PAG texts per commune, not a hand-coded approximation
- `resolutions.json` flat file — replace with a proper database (SQLite at minimum) with versioning and audit trail
- The 65% word-overlap threshold for quote grounding — it should be tuned on a labelled set once real false-positive/negative rates are known

---

## 3-month vision

The resolution workflow already captures the most valuable long-term asset: expert decisions on ambiguous regulatory points. At scale, that becomes a **precedent database** — searchable by topic, by regulation pair, by building type. Combined with a RAG layer over the full ITM/PAG corpus, an inspector could query "what lux level applies to a chantier corridor under CL-144.1 vs CL-55.2" and get back the conflict, the recommendation, and any prior resolution by a SECO expert. That's the product worth building.

Three months of work: structured document ingest pipeline (OCR + chunking), PostgreSQL-backed precedent store, RAG query interface, basic auth to scope resolutions by team.
