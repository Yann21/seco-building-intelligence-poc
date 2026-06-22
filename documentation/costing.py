#!/usr/bin/env python3
"""
SECO — API Costing Report Generator

Uses the Anthropic count_tokens API (no inference, no charge) to get exact
input token counts for each document pair, then estimates output cost and
extrapolates to larger document corpora.

Usage:
    python documentation/costing.py
    python documentation/costing.py --output documentation/costing.html
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "app2-conflict-resolver" / "backend"))

from analyze import SYSTEM_PROMPT, PAIR_PROMPT, MODEL, COST_INPUT_PER_TOKEN, COST_OUTPUT_PER_TOKEN
from extract import get_extracted

# Observed output range: 2k–4k tokens per pair. Using upper bound to be conservative.
OUTPUT_TOKENS_PER_PAIR_EST = 4000


# ── Measurement ───────────────────────────────────────────────────────────────

def build_pair_prompt(doc_a: dict, doc_b: dict) -> str:
    doc_sections = ""
    for doc in [doc_a, doc_b]:
        doc_sections += (
            f"\n\n{'='*60}\n"
            f"DOCUMENT: {doc['title']}\n"
            f"Autorité: {doc['authority']} | Date: {doc['date']}\n"
            f"{'='*60}\n\n"
            f"{doc['full_text']}"
        )
    return PAIR_PROMPT.format(doc_sections=doc_sections)


def count_pair_input_tokens(client: anthropic.Anthropic, doc_a: dict, doc_b: dict) -> int:
    """Exact input token count via count_tokens API — no inference, no charge."""
    resp = client.messages.count_tokens(
        model=MODEL,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_pair_prompt(doc_a, doc_b)}],
    )
    return resp.input_tokens


def count_prompt_overhead(client: anthropic.Anthropic) -> int:
    """Tokens used by system prompt + pair prompt template (no doc content)."""
    resp = client.messages.count_tokens(
        model=MODEL,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": PAIR_PROMPT.format(doc_sections="")}],
    )
    return resp.input_tokens


# ── Extrapolation ─────────────────────────────────────────────────────────────

def extrapolation_rows(avg_input_per_pair: float, ns: list[int]) -> list[dict]:
    """
    Model: N documents, undirected pairwise matrix.
    Total pairs for N docs: N*(N-1)/2
    New pairs when adding the N-th doc to N-1 existing: N-1
    Cost per call: avg_input * INPUT_RATE + OUTPUT_EST * OUTPUT_RATE
    """
    cost_per_pair = (
        avg_input_per_pair * COST_INPUT_PER_TOKEN
        + OUTPUT_TOKENS_PER_PAIR_EST * COST_OUTPUT_PER_TOKEN
    )
    rows = []
    for n in ns:
        total_pairs = n * (n - 1) // 2
        new_pairs = n - 1  # adding the n-th doc
        rows.append({
            "n": n,
            "total_pairs": total_pairs,
            "new_pairs_on_add": new_pairs,
            "cost_one_addition": new_pairs * cost_per_pair,
            "cost_full_build": total_pairs * cost_per_pair,
        })
    return rows


# ── HTML generation ───────────────────────────────────────────────────────────

def _cost_color(usd: float) -> str:
    if usd < 1:
        return "#d1fae5"  # green
    if usd < 5:
        return "#fef3c7"  # yellow
    if usd < 20:
        return "#fed7aa"  # orange
    return "#fecaca"      # red


def generate_html(
    doc_list: list[dict],
    prompt_overhead: int,
    pair_stats: list[dict],
    extrap_rows: list[dict],
    avg_input_per_pair: float,
    generated_at: str,
) -> str:
    total_input = sum(p["input_tokens"] for p in pair_stats)
    total_output_est = OUTPUT_TOKENS_PER_PAIR_EST * len(pair_stats)
    total_cost = sum(p["cost_usd"] for p in pair_stats)

    # ── Document rows ──
    doc_rows_html = ""
    for doc in doc_list:
        words = len(doc["full_text"].split())
        tok_est = int(words * 1.3)
        doc_rows_html += f"""
        <tr>
          <td><code>{doc['id']}</code></td>
          <td>{doc['title']}</td>
          <td class="num">{doc['authority'].split('(')[1].rstrip(')') if '(' in doc['authority'] else doc['authority']}</td>
          <td class="num">{len(doc['pages'])}</td>
          <td class="num">{words:,}</td>
          <td class="num">~{tok_est:,}</td>
        </tr>"""

    # ── Pair rows ──
    pair_rows_html = ""
    for p in pair_stats:
        content_tokens = p["input_tokens"] - prompt_overhead
        pair_rows_html += f"""
        <tr>
          <td><code>{p['doc_a']}</code> × <code>{p['doc_b']}</code></td>
          <td class="num">{prompt_overhead:,}</td>
          <td class="num">{content_tokens:,}</td>
          <td class="num"><strong>{p['input_tokens']:,}</strong></td>
          <td class="num">{OUTPUT_TOKENS_PER_PAIR_EST:,} <span class="est">est.</span></td>
          <td class="num cost">${p['cost_usd']:.4f}</td>
        </tr>"""

    # ── Extrapolation rows ──
    extrap_rows_html = ""
    is_baseline = True
    for row in extrap_rows:
        baseline_marker = " <span class='baseline'>← baseline</span>" if is_baseline else ""
        is_baseline = False
        bg_add = _cost_color(row["cost_one_addition"])
        bg_build = _cost_color(row["cost_full_build"])
        extrap_rows_html += f"""
        <tr>
          <td class="num"><strong>{row['n']}</strong></td>
          <td class="num">{row['total_pairs']:,}</td>
          <td class="num">{row['new_pairs_on_add']}{baseline_marker}</td>
          <td class="num" style="background:{bg_add}">${row['cost_one_addition']:.2f}</td>
          <td class="num" style="background:{bg_build}">${row['cost_full_build']:.2f}</td>
        </tr>"""

    # ── Robustness stack rows ──
    robustness_items = [
        (
            "Pydantic schema validation",
            "Every LLM response is validated against a typed schema "
            "(<code>Conflict</code>, <code>ConflictSource</code>). "
            "Malformed conflicts are logged and dropped, not silently served. "
            "Prevents schema drift between prompt iterations from corrupting cached results.",
        ),
        (
            "Quote grounding",
            "Each cited quote is fuzzy-matched against the source document text "
            "(65% word-overlap, accent-normalised). Conflicts where the quote cannot "
            "be located are flagged <code>quote_verified: false</code> in the API "
            "response and shown with a warning badge in the UI. "
            "Catches hallucinated citations without discarding potentially valid conflicts.",
        ),
        (
            "Retry with exponential backoff",
            "API calls are wrapped in a 3-attempt loop "
            "(1 s → 2 s → 4 s) on <code>RateLimitError</code> and "
            "<code>InternalServerError</code>. Permanent failures propagate as a 500.",
        ),
        (
            "Prompt versioning",
            "<code>PROMPT_VERSION</code> is embedded in the pair cache key. "
            "Bumping the version automatically invalidates all cached pairs on the "
            "next analysis run — no manual cache flush needed.",
        ),
        (
            "Content-addressed pair cache",
            "Cache key = <code>sha256(doc_a_text)[:12] + sha256(doc_b_text)[:12] + PROMPT_VERSION</code>. "
            "Changing a document's bytes invalidates only the pairs involving that document; "
            "all other pairs remain cached.",
        ),
        (
            "Append-only usage log",
            "Every API call appends a record to <code>usage_log.jsonl</code> "
            "(timestamp, pair ID, model, input tokens, output tokens, cost USD). "
            "Exposed at <code>GET /api/usage</code>.",
        ),
    ]
    robustness_rows_html = ""
    for name, desc in robustness_items:
        robustness_rows_html += f"""
        <tr>
          <td class="guard-name">{name}</td>
          <td>{desc}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SECO — API Costing & Robustness Report</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
      font-size: 14px;
      line-height: 1.6;
      color: #1a1a2e;
      background: #f5f5f7;
      margin: 0;
      padding: 0 0 48px;
    }}
    header {{
      background: #1a1a2e;
      color: #e2e8f0;
      padding: 28px 40px 24px;
      border-bottom: 3px solid #3b82f6;
    }}
    header h1 {{
      margin: 0 0 6px;
      font-size: 20px;
      font-weight: 600;
      color: #fff;
    }}
    header p {{
      margin: 0;
      font-size: 12px;
      color: #94a3b8;
    }}
    header code {{
      background: #334155;
      padding: 1px 5px;
      border-radius: 3px;
      font-size: 11px;
      color: #93c5fd;
    }}
    main {{
      max-width: 960px;
      margin: 32px auto;
      padding: 0 24px;
    }}
    .metric-row {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 32px;
    }}
    .metric-card {{
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 16px 18px;
    }}
    .metric-card .label {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: #64748b;
      margin-bottom: 6px;
    }}
    .metric-card .value {{
      font-size: 22px;
      font-weight: 700;
      color: #1e293b;
    }}
    .metric-card .sub {{
      font-size: 11px;
      color: #94a3b8;
      margin-top: 2px;
    }}
    section {{
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 24px 28px;
      margin-bottom: 20px;
    }}
    h2 {{
      font-size: 15px;
      font-weight: 600;
      color: #1e293b;
      margin: 0 0 16px;
      padding-bottom: 10px;
      border-bottom: 1px solid #f1f5f9;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    thead th {{
      text-align: left;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #64748b;
      padding: 6px 10px;
      border-bottom: 2px solid #e2e8f0;
    }}
    tbody tr:nth-child(odd) {{ background: #f8fafc; }}
    tbody tr:hover {{ background: #f0f9ff; }}
    td {{
      padding: 8px 10px;
      border-bottom: 1px solid #f1f5f9;
      vertical-align: top;
    }}
    td.num {{ text-align: right; white-space: nowrap; }}
    td.cost {{
      font-weight: 600;
      color: #0f766e;
    }}
    td.guard-name {{
      font-weight: 600;
      white-space: nowrap;
      color: #1e293b;
      width: 200px;
    }}
    .est {{
      font-size: 10px;
      color: #94a3b8;
      font-style: italic;
    }}
    .baseline {{
      font-size: 10px;
      color: #3b82f6;
      font-weight: 400;
    }}
    code {{
      background: #f1f5f9;
      padding: 1px 5px;
      border-radius: 3px;
      font-size: 12px;
      color: #0f172a;
    }}
    .note {{
      margin-top: 14px;
      padding: 12px 14px;
      background: #f8fafc;
      border-left: 3px solid #94a3b8;
      border-radius: 0 4px 4px 0;
      font-size: 12px;
      color: #475569;
      line-height: 1.7;
    }}
    .note strong {{ color: #334155; }}
    tfoot td {{
      font-weight: 600;
      border-top: 2px solid #e2e8f0;
      background: #f8fafc;
    }}
  </style>
</head>
<body>
<header>
  <h1>SECO — API Costing &amp; Robustness Report</h1>
  <p>
    Generated: {generated_at} &nbsp;·&nbsp;
    Model: <code>{MODEL}</code> &nbsp;·&nbsp;
    Pricing: <code>${COST_INPUT_PER_TOKEN * 1_000_000:.0f} / MTok input</code>
    &nbsp;·&nbsp; <code>${COST_OUTPUT_PER_TOKEN * 1_000_000:.0f} / MTok output</code>
  </p>
</header>

<main>

  <div class="metric-row">
    <div class="metric-card">
      <div class="label">Documents analysed</div>
      <div class="value">{len(doc_list)}</div>
      <div class="sub">{len(pair_stats)} pairs</div>
    </div>
    <div class="metric-card">
      <div class="label">Total input tokens</div>
      <div class="value">{total_input:,}</div>
      <div class="sub">exact · count_tokens API</div>
    </div>
    <div class="metric-card">
      <div class="label">Output tokens (est.)</div>
      <div class="value">{total_output_est:,}</div>
      <div class="sub">{OUTPUT_TOKENS_PER_PAIR_EST:,} / pair · conservative</div>
    </div>
    <div class="metric-card">
      <div class="label">Total cost (3-doc baseline)</div>
      <div class="value">${total_cost:.4f}</div>
      <div class="sub">$0.00 on warm restart</div>
    </div>
  </div>

  <!-- 1. Document corpus -->
  <section>
    <h2>1 · Document Corpus</h2>
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Title</th>
          <th>Authority</th>
          <th>Pages</th>
          <th>Words</th>
          <th>Tokens (est.)</th>
        </tr>
      </thead>
      <tbody>{doc_rows_html}</tbody>
    </table>
    <div class="note">
      Per-document token count is estimated as <strong>words × 1.3</strong> (standard approximation for French regulatory text).
      Pair-level counts below are exact, measured via the Anthropic <code>count_tokens</code> API (non-billable endpoint).
    </div>
  </section>

  <!-- 2. Pair analysis -->
  <section>
    <h2>2 · Pair-by-Pair Token Analysis</h2>
    <table>
      <thead>
        <tr>
          <th>Pair</th>
          <th>Prompt overhead</th>
          <th>Document content</th>
          <th>Total input</th>
          <th>Output (est.)</th>
          <th>Cost</th>
        </tr>
      </thead>
      <tbody>{pair_rows_html}</tbody>
      <tfoot>
        <tr>
          <td>Total ({len(pair_stats)} pairs)</td>
          <td class="num">{prompt_overhead * len(pair_stats):,}</td>
          <td class="num">{total_input - prompt_overhead * len(pair_stats):,}</td>
          <td class="num">{total_input:,}</td>
          <td class="num">{total_output_est:,}</td>
          <td class="num cost">${total_cost:.4f}</td>
        </tr>
      </tfoot>
    </table>
    <div class="note">
      <strong>Prompt overhead</strong> = system prompt + pair prompt template, before any document content is added ({prompt_overhead:,} tokens, constant per call).<br>
      <strong>Output estimate</strong> uses {OUTPUT_TOKENS_PER_PAIR_EST:,} tokens/pair (upper bound from <code>max_tokens</code> setting; observed output is typically 2,000–3,500 tokens).
    </div>
  </section>

  <!-- 3. Robustness stack -->
  <section>
    <h2>3 · Robustness Stack</h2>
    <table>
      <thead>
        <tr>
          <th style="width:200px">Guard</th>
          <th>What it does</th>
        </tr>
      </thead>
      <tbody>{robustness_rows_html}</tbody>
    </table>
  </section>

  <!-- 4. Extrapolation -->
  <section>
    <h2>4 · Cost Extrapolation</h2>
    <table>
      <thead>
        <tr>
          <th>Index size (N docs)</th>
          <th>Total pairs N(N−1)/2</th>
          <th>New pairs when adding 1 doc</th>
          <th>Cost: 1 doc addition</th>
          <th>Cost: full build from scratch</th>
        </tr>
      </thead>
      <tbody>{extrap_rows_html}</tbody>
    </table>
    <div class="note">
      <strong>Model assumptions:</strong>
      average input tokens per pair = <strong>{int(avg_input_per_pair):,}</strong>
      (mean of the {len(pair_stats)} measured pairs above) ·
      output = {OUTPUT_TOKENS_PER_PAIR_EST:,} tokens/pair (conservative) ·
      warm restarts cost $0.00 (all pairs served from cache).<br><br>

      <strong>Adding the N-th document</strong> to an index of N−1 existing documents
      requires N−1 new LLM calls — one per new pair. All existing pair results are cache hits.
      Growth is O(n) per ingestion, O(n²) total to build from scratch.<br><br>

      <strong>Main lever for cost reduction:</strong> document chunking — send only topically
      relevant sections per pair instead of full text. Lighting regulations are ~30% lighting-specific content;
      chunking could reduce per-pair token counts by 3–5×, bringing the 50-doc full-build cost
      from ~${extrap_rows[-2]['cost_full_build']:.0f} to under $20.
    </div>
  </section>

</main>
</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate API costing report")
    parser.add_argument(
        "--output",
        default=str(ROOT / "documentation" / "costing.html"),
        help="Output HTML path",
    )
    args = parser.parse_args()

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    docs = get_extracted()
    doc_list = list(docs.values())

    print(f"Counting prompt overhead...")
    prompt_overhead = count_prompt_overhead(client)
    print(f"  {prompt_overhead:,} tokens")

    print("Counting tokens per pair (count_tokens API — no charge)...")
    pair_stats = []
    for i in range(len(doc_list)):
        for j in range(i + 1, len(doc_list)):
            da, db = doc_list[i], doc_list[j]
            print(f"  {da['id']} × {db['id']}...")
            input_tokens = count_pair_input_tokens(client, da, db)
            cost = (
                input_tokens * COST_INPUT_PER_TOKEN
                + OUTPUT_TOKENS_PER_PAIR_EST * COST_OUTPUT_PER_TOKEN
            )
            pair_stats.append({
                "doc_a": da["id"],
                "doc_b": db["id"],
                "input_tokens": input_tokens,
                "cost_usd": cost,
            })
            print(f"    → {input_tokens:,} tokens · ${cost:.4f}")

    avg_input = sum(p["input_tokens"] for p in pair_stats) / len(pair_stats)
    extrap = extrapolation_rows(avg_input, [3, 5, 10, 20, 50, 100])

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = generate_html(doc_list, prompt_overhead, pair_stats, extrap, avg_input, generated_at)

    out = Path(args.output)
    out.parent.mkdir(exist_ok=True)
    out.write_text(html)
    print(f"\nReport written → {out}")


if __name__ == "__main__":
    main()
