# SECO PoC — Checkpoint (2026-06-22)

## What this PoC was supposed to demonstrate

A "Building Intelligence" system for SECO (Luxembourg construction inspection firm).
The core thesis: ITM regulatory texts contradict each other, nobody detects that systematically,
and an AI layer can surface those contradictions with citations and resolution workflows.

Three apps planned:
- **App 1** — PAG Zone Map: parcel → applicable zoning rules + documents (done, archived)
- **App 2** — Regulatory Conflict Resolver: intra-cluster pairwise conflict detection (done, live)
- **App 3** — ITM Explorer: full ITM corpus map (BUILT — 454 docs scraped, 326 embedded + UMAP)

---

## Where we are (v0.2 — "cluster-aware")

### App 2 is the main deliverable

Live at [yannhoffmann.com/seco2](https://yannhoffmann.com/seco2).

**What works:**
- Cluster-aware pairwise conflict detection across 3 clusters:
  - 💡 lighting (ITM-CL-55.2, ITM-ET-32.10, ITM-CL-144.1) — 9 conflicts
  - 🌬 ventilation (ITM-CL-53.1, ITM-CL-62.1, ITM-CL-86.1) — ~15 conflicts
  - 🛗 ascenseurs (ITM-CL-82.1, ITM-CL-83.1, ITM-CL-230.2) — ~22 conflicts
- Cluster sidebar with doc list, conflict counts, filter by cluster
- Conflict cards: severity badge, sources with quotes, recommendation, expert resolution workflow
- Quote grounding (65% fuzzy match — flags hallucinated citations)
- Pydantic validation on all LLM output
- Prompt versioning in cache keys (content-hash-based, O(C) re-run on doc update)
- Dark/light mode (browser-aware)
- Usage + cost logging (`usage_log.jsonl`, `GET /api/usage`)

**Architecture decision that matters:** pairwise cache — adding one doc to a cluster triggers C−1 API calls, not a full rebuild. This is the right model for a growing corpus.

### Documentation

Served at `http://localhost:8889` via `make doc`:
- `/` — README (regulatory scope, architecture, LLM tier comparison, costing)
- `/costing` — per-document token counts, pair costs, GPU vs API extrapolation
- `/benchmark` — LLM quality audit (Claude vs phi3.5 on real ITM docs)

**Key costing numbers:** ~$0.35/pair on Claude API, ~$0.01/pair on private GPU (g4dn.xlarge).
Full 100-doc index: ~$35 API vs ~$10 GPU one-time build, ~$0 warm cache hits.

---

## What comes next

### 1. Document freshness tracking (direction 1 — not started)

The conflict resolver is only as good as its corpus. No mechanism exists today to detect
when ITM publishes an updated version of a regulation.

What needs to be built:
- Periodic crawler: compare remote PDF hash against `content_hash` in `DOCS_META` (extract.py)
- On change: re-extract text, invalidate pair caches for that doc's cluster (C−1 re-runs)
- UI: show document date on each doc card, flag docs >2 years without known update

### 2. ITM Explorer — App 3 (BUILT — corpus map done)

Pipeline in `app3-itm-explorer/explore.py` (run via `make explore`, all stages cached):
scrape → download → pdfplumber extract → LLM titles → OpenAI embed → UMAP → `report.html`.

**Corpus, quantified (full ITM, not the earlier 113 estimate):**
- **454 documents** scraped from itm.public.lu (French only, ITM-CL/ET/SST series)
- **326 text-extractable** → embedded + mapped, with meaningful titles
- **128 scanned (28%)** → no text layer, EXCLUDED from the map, listed as an OCR backlog
- ~1.69M words mapped; largest doc ~29.8k words

**Key findings (worth digging into next):**
- **Three series, two eras.** ITM-CL (Conditions-types, per-equipment, ~1990–2016) and
  ITM-ET (Établissements-types, per-building-type, ~1991–2005) are the LEGACY series.
  ITM-SST (Sécurité-Santé au Travail, ~2007–2025) is the MODERN unified series absorbing
  both. → This transition is the strongest argument yet for app2's version-tracking:
  a 1990s CL prescription may be silently superseded by a recent SST text.
- **28% OCR gap** is now a concrete, quantified backlog (the 128 scanned docs), not a guess.

**Implementation notes / known limitations:**
- Titles extracted via gpt-4o-mini (326 calls, pennies, threaded ×8) — clean, 0 fallbacks.
- Embeddings: OpenAI text-embedding-3-small, **first ~8000 chars only** (≈2k tokens).
  Long docs are embedded on their opening section → position reflects the intro, not the
  whole text. Production fix: chunk long docs + average vectors. (Documented in the report.)
- Caches in `app3-itm-explorer/data/cache/`: links, extracted, titles, embeddings, umap2d.

**Still TBD for app3 (next directions):**
- OCR the 128 scanned docs (Claude vision) and fold them into the map.
- Chunking for long docs so positions reflect full content.
- Cross-cluster conflict detection (lighting × fire safety, etc.) using the corpus map to
  pick the next clusters to feed into app2.
- Regulatory graph: which docs cite/supersede which.
- Optionally wire report.html into the `make doc` navbar (currently standalone).

### 3. Code testing — web and AI (direction 3 — not started)

Two test layers planned:
- **Web tests**: UI interaction tests for App 2 (cluster selection, conflict card expand/collapse, resolution workflow, theme toggle)
- **AI tests**: quality regression tests on the LLM pipeline — given a known pair with known conflicts, assert the output contains expected conflict IDs, severities, and quote coverage. Prevents prompt regressions from silently degrading detection quality. Coverage to be improved.

### 4. Scope expansion beyond ITM (longer horizon)

The PoC deliberately scopes to ITM only. The full regulatory stack for Luxembourg commercial
buildings also includes CGDIS (fire safety), Eurocodes National Annexes, and communal PAP supplements.
A cross-body conflict resolver (ITM × CGDIS × Eurocodes) is the full product worth building.
