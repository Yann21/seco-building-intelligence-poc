#!/usr/bin/env python3
"""
SECO — API Costing Report Generator

Uses the Anthropic count_tokens API (no inference, no charge) to get exact
input token counts for each document pair, then estimates output cost and
extrapolates to larger document corpora using a cluster-based model.

Extrapolation model:
  Documents are organized into topic clusters (subfolders under documents/).
  Only intra-cluster pairs are analyzed. For a corpus of N docs with average
  cluster size C:
    Total pairs = N * (C-1) / 2
    New pairs when adding 1 doc = C-1  (constant regardless of total N)
  This bounds ingestion cost at O(C), not O(N).

The HTML output includes interactive inputs for avg. document size and
cluster size that dynamically update all extrapolation rows.

Usage:
    python documentation/costing.py
    python documentation/costing.py --output documentation/costing.html
"""

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "conflict-resolver" / "backend"))

from pipeline.analyze import PAIR_PROMPT, SYSTEM_PROMPT
from pipeline.config import COST_INPUT_PER_TOKEN, COST_OUTPUT_PER_TOKEN, MODEL
from pipeline.extract import get_extracted

OUTPUT_TOKENS_PER_PAIR_EST = 4000  # conservative upper bound (observed: 2k–4k)


# ── Token counting ─────────────────────────────────────────────────────────────


def build_pair_prompt(doc_a: dict, doc_b: dict) -> str:
    doc_sections = ""
    for doc in [doc_a, doc_b]:
        doc_sections += (
            f"\n\n{'=' * 60}\n"
            f"DOCUMENT: {doc['title']}\n"
            f"Autorité: {doc['authority']} | Date: {doc['date']}\n"
            f"{'=' * 60}\n\n"
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
    """Tokens used by system prompt + pair prompt template with no doc content."""
    resp = client.messages.count_tokens(
        model=MODEL,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": PAIR_PROMPT.format(doc_sections="")}],
    )
    return resp.input_tokens


def avg_doc_tokens_from_pairs(pair_stats: list[dict], prompt_overhead: int) -> int:
    """
    Derive average per-document token count from pair measurements.
    Uses the system of equations: for each pair (A,B), tokens(A) + tokens(B) = pair_input - overhead.
    With N=3 docs and 3 pairs this is solvable exactly; for larger sets we use the mean.
    """
    # For 3 docs: solve exactly
    doc_ids = list({p["doc_a"] for p in pair_stats} | {p["doc_b"] for p in pair_stats})
    if len(doc_ids) == 3 and len(pair_stats) == 3:
        content = {
            p["doc_a"] + "+" + p["doc_b"]: p["input_tokens"] - prompt_overhead for p in pair_stats
        }
        vals = list(content.values())
        total = sum(vals) / 2  # each doc counted twice across 3 pairs
        return round(total / 3)
    # General case: average pair content / 2
    avg_pair_content = sum(p["input_tokens"] - prompt_overhead for p in pair_stats) / len(
        pair_stats
    )
    return round(avg_pair_content / 2)


# ── HTML generation ────────────────────────────────────────────────────────────


def gpu_section(pair_stats: list[dict], total_api_cost: float) -> str:
    """
    GPU cost projections for g4dn.xlarge (NVIDIA T4 16 GB VRAM, Frankfurt eu-central-1).
    Source: interpolate/aws/spin-up.sh — same instance used for Stable Diffusion work.
    """
    on_demand = 0.526  # $/hr, eu-central-1 on-demand
    spot = 0.158  # $/hr, ~70% discount
    gen_tps = 180  # tok/sec, Mistral 7B Q4_K_M generation on T4
    prefill_tps = 4000  # tok/sec, prefill is memory-bandwidth bound

    n_pairs = len(pair_stats)
    avg_input = sum(p["input_tokens"] for p in pair_stats) / n_pairs if n_pairs else 32000
    output_est = OUTPUT_TOKENS_PER_PAIR_EST

    prefill_s = avg_input / prefill_tps
    gen_s = output_est / gen_tps
    per_pair_s = prefill_s + gen_s
    total_s = per_pair_s * n_pairs

    cost_od = total_s / 3600 * on_demand
    cost_spot = total_s / 3600 * spot

    lora_h = 0.75  # LoRA fine-tune on T4, ~100 examples
    lora_cost = lora_h * on_demand

    speedup = total_api_cost / cost_od if cost_od > 0 else 0

    rows = [
        (
            "Instance",
            "g4dn.xlarge",
            "AWS Frankfurt (eu-central-1) — same config as interpolate/aws/spin-up.sh",
        ),
        ("GPU", "NVIDIA T4 · 16 GB VRAM", "8.1 TFLOPS FP32 · 320 GB/s memory bandwidth"),
        ("Model", "Mistral 7B Q4_K_M", "4.1 GB VRAM · leaves 12 GB headroom · near-FP16 quality"),
        ("Generation throughput", "~180 tok/sec", "T4 memory-bandwidth bound at Q4 quant"),
        (
            "Prefill (input)",
            f"~{avg_input / prefill_tps:.1f}s / pair",
            f"{avg_input:,.0f} tok avg input ÷ {prefill_tps:,} tok/s",
        ),
        (
            "Generation (output)",
            f"~{gen_s:.1f}s / pair",
            f"{output_est:,} tok output ÷ {gen_tps} tok/s",
        ),
        (
            "Total inference time",
            f"~{total_s:.0f}s ({n_pairs} pairs)",
            f"{per_pair_s:.1f}s/pair · sequential; trivially parallelisable",
        ),
        ("Cost · on-demand", f"${cost_od:.4f}", f"${on_demand}/hr × {total_s:.0f}s"),
        (
            "Cost · spot instance",
            f"${cost_spot:.4f}",
            f"${spot}/hr · ~70% discount · interruptible",
        ),
        (
            "vs. Claude API",
            f"{speedup:.0f}× cheaper / run",
            f"API ${total_api_cost:.4f} → GPU ${cost_od:.4f} once instance is running",
        ),
        (
            "LoRA fine-tune (optional)",
            f"~{lora_h}h · ${lora_cost:.2f}",
            "100-example domain adaptation on T4 · one-time cost",
        ),
    ]

    rows_html = "\n".join(
        f'<tr><td>{r}</td><td class="num">{v}</td><td style="color:#64748b;font-size:12px">{n}</td></tr>'
        for r, v, n in rows
    )

    return f"""
  <section class="gpu-section">
    <h2>3 · GPU Inference — g4dn.xlarge / NVIDIA T4</h2>
    <p style="font-size:12px;color:#4b5563;margin:0 0 14px">
      <span class="tier-api">Tier 1</span> Claude API — pay per token, data leaves network &nbsp;·&nbsp;
      <span class="tier-gpu">Tier 3</span> GPU private — near-API quality, data stays in VPC
    </p>
    <table class="gpu-table">
      <thead><tr><th>Metric</th><th>Value</th><th>Notes</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    <div class="gpu-note">
      <strong>When GPU pays off:</strong>
      the instance startup overhead (~2 min) dominates for occasional use.
      At ~10 full analyses/day a persistent spot instance costs ~$3.80/day vs ~$4.70/day on the API —
      break-even is low, but the primary driver for GPU is <strong>confidentiality</strong>
      (no document text transits external servers), not cost.<br><br>
      <strong>Spin-up command:</strong> <code>bash interpolate/aws/spin-up.sh</code>
      (auto-terminates after 4 h, costs max ${on_demand * 4:.2f} on-demand).
    </div>
  </section>"""


def generate_html(
    doc_list: list[dict],
    prompt_overhead: int,
    pair_stats: list[dict],
    avg_doc_tok: int,
    current_cluster_size: int,
    generated_at: str,
) -> str:
    total_input = sum(p["input_tokens"] for p in pair_stats)
    total_output_est = OUTPUT_TOKENS_PER_PAIR_EST * len(pair_stats)
    total_cost = sum(p["cost_usd"] for p in pair_stats)
    gpu_html = gpu_section(pair_stats, total_cost)

    # ── Document rows ──
    doc_rows_html = ""
    for doc in doc_list:
        words = len(doc["full_text"].split())
        cluster = doc.get("cluster", "default")
        doc_rows_html += f"""
        <tr>
          <td><code>{doc["id"]}</code></td>
          <td>{doc["title"]}</td>
          <td class="num">{doc["authority"].split("(")[1].rstrip(")") if "(" in doc["authority"] else doc["authority"]}</td>
          <td class="num"><span class="cluster-tag">{cluster}</span></td>
          <td class="num">{len(doc["pages"])}</td>
          <td class="num">{words:,}</td>
        </tr>"""

    # ── Pair rows ──
    pair_rows_html = ""
    for p in pair_stats:
        content_tokens = p["input_tokens"] - prompt_overhead
        pair_rows_html += f"""
        <tr>
          <td><code>{p["doc_a"]}</code> × <code>{p["doc_b"]}</code>
            <span class="cluster-tag" style="margin-left:6px">{p["cluster"]}</span></td>
          <td class="num">{prompt_overhead:,}</td>
          <td class="num">{content_tokens:,}</td>
          <td class="num"><strong>{p["input_tokens"]:,}</strong></td>
          <td class="num">{OUTPUT_TOKENS_PER_PAIR_EST:,} <span class="est">est.</span></td>
          <td class="num cost">${p["cost_usd"]:.4f}</td>
        </tr>"""

    # ── Metric cards ──
    def metric(label, val, sub=""):
        return f'<div class="mc"><div class="ml">{label}</div><div class="mv">{val}</div><div class="ms">{sub}</div></div>'

    cards_html = f"""
    <div class="metrics">
      {metric("Documents", str(len(doc_list)), f"{current_cluster_size}-doc cluster · {len(pair_stats)} pairs")}
      {metric("Total input tokens", f"{total_input:,}", "exact · count_tokens API")}
      {metric("Output tokens (est.)", f"{total_output_est:,}", f"{OUTPUT_TOKENS_PER_PAIR_EST:,} / pair · conservative")}
      {metric("Baseline cost", f"${total_cost:.4f}", "$0.00 on warm restart")}
    </div>"""

    # ── JS for interactive extrapolation ──
    js = f"""
const COST_INPUT  = {COST_INPUT_PER_TOKEN};
const COST_OUTPUT = {COST_OUTPUT_PER_TOKEN};
const OUTPUT_EST  = {OUTPUT_TOKENS_PER_PAIR_EST};
const PROMPT_OVERHEAD = {prompt_overhead};

// GPU — g4dn.xlarge / T4 (eu-central-1)
const GPU_OD_PER_HR   = 0.526;   // on-demand $/hr
const GPU_SPOT_PER_HR = 0.158;   // spot $/hr
const GPU_GEN_TPS     = 180;     // tok/sec generation (Mistral 7B Q4_K_M)
const GPU_PREFILL_TPS = 4000;    // tok/sec prefill

const FIXED_NS = [3, 5, 10, 20, 50, 100];

function costColor(usd) {{
  if (usd < 1)  return '#d1fae5';
  if (usd < 10) return '#fef3c7';
  if (usd < 50) return '#fed7aa';
  return '#fecaca';
}}

function gpuColor(usd) {{
  if (usd < 0.01) return '#ede9fe';
  if (usd < 0.1)  return '#ddd6fe';
  if (usd < 1)    return '#c4b5fd';
  return '#a78bfa';
}}

function fmt(usd) {{
  return usd < 0.01 ? usd.toFixed(4) : usd.toFixed(2);
}}

function calcRow(n, avgDocTok, clusterSize) {{
  const cs = Math.max(2, clusterSize);
  const nClusters = n / cs;
  const pairsPerCluster = cs * (cs - 1) / 2;
  const totalPairs = nClusters * pairsPerCluster;   // = n*(cs-1)/2
  const newPairs   = cs - 1;                         // adding 1 doc to a full cluster
  const pairTok    = 2 * avgDocTok + PROMPT_OVERHEAD;
  const cpp        = pairTok * COST_INPUT + OUTPUT_EST * COST_OUTPUT;

  // GPU: time per pair = prefill time + generation time
  const pairTimeS  = pairTok / GPU_PREFILL_TPS + OUTPUT_EST / GPU_GEN_TPS;
  const gpuCppOD   = pairTimeS / 3600 * GPU_OD_PER_HR;
  const gpuCppSpot = pairTimeS / 3600 * GPU_SPOT_PER_HR;

  const apiAdd   = newPairs  * cpp;
  const apiBuild = totalPairs * cpp;

  return {{
    n:           Math.round(n),
    nClusters:   Math.round(nClusters * 10) / 10,
    totalPairs:  Math.round(totalPairs),
    newPairs:    Math.round(newPairs),
    costAdd:     apiAdd,
    costBuild:   apiBuild,
    gpuAddOD:    newPairs  * gpuCppOD,
    gpuBuildOD:  totalPairs * gpuCppOD,
    gpuAddSpot:  newPairs  * gpuCppSpot,
    gpuBuildSpot: totalPairs * gpuCppSpot,
  }};
}}

function renderTable() {{
  const avgDocTok   = parseInt(document.getElementById('avgDocTok').value)   || {avg_doc_tok};
  const clusterSize = parseInt(document.getElementById('clusterSize').value) || {current_cluster_size};
  const customN     = parseInt(document.getElementById('customN').value)     || 1000;
  const gpuMode     = document.getElementById('gpuMode').value;

  const ns = [...FIXED_NS, customN];
  let rows = '';
  ns.forEach((n, i) => {{
    const r = calcRow(n, avgDocTok, clusterSize);
    const isCustom = i === ns.length - 1;
    const isBaseline = n === {len(doc_list)};
    const baseline = isBaseline ? ' <span class="baseline">← baseline</span>' : '';
    const gpuAdd   = gpuMode === 'spot' ? r.gpuAddSpot   : r.gpuAddOD;
    const gpuBuild = gpuMode === 'spot' ? r.gpuBuildSpot : r.gpuBuildOD;
    const savingsUsd = r.costBuild - gpuBuild;
    const savingsLabel = fmt(savingsUsd);
    rows += `<tr${{isCustom ? ' class="custom-row"' : ''}}>
      <td class="num"><strong>${{r.n}}</strong>${{baseline}}</td>
      <td class="num">${{r.nClusters}}</td>
      <td class="num">${{r.totalPairs.toLocaleString()}}</td>
      <td class="num">${{r.newPairs}}</td>
      <td class="num" style="background:${{costColor(r.costAdd)}}">${{fmt(r.costAdd)}}</td>
      <td class="num" style="background:${{costColor(r.costBuild)}}">${{fmt(r.costBuild)}}</td>
      <td class="num gpu-col" style="background:${{gpuColor(gpuAdd)}}">${{fmt(gpuAdd)}}</td>
      <td class="num gpu-col" style="background:${{gpuColor(gpuBuild)}}">${{fmt(gpuBuild)}}</td>
      <td class="num savings-col">${{savingsLabel}}</td>
    </tr>`;
  }});
  document.getElementById('extrap-body').innerHTML = rows;

  // Update formula note
  const cpp    = (2 * avgDocTok + PROMPT_OVERHEAD) * COST_INPUT + OUTPUT_EST * COST_OUTPUT;
  const pTime  = ((2 * avgDocTok + PROMPT_OVERHEAD) / GPU_PREFILL_TPS + OUTPUT_EST / GPU_GEN_TPS).toFixed(1);
  const gpuCpp = gpuMode === 'spot'
    ? (parseFloat(pTime) / 3600 * GPU_SPOT_PER_HR)
    : (parseFloat(pTime) / 3600 * GPU_OD_PER_HR);
  document.getElementById('cpp-note').innerHTML =
    `<strong>API:</strong> ${{(2*avgDocTok + PROMPT_OVERHEAD).toLocaleString()}} tok × $${{(COST_INPUT*1e6).toFixed(0)}}/MTok + ${{OUTPUT_EST.toLocaleString()}} tok × $${{(COST_OUTPUT*1e6).toFixed(0)}}/MTok = $${{cpp.toFixed(4)}} / pair` +
    `&emsp;|&emsp;<strong>GPU (${{gpuMode}}):</strong> ${{pTime}}s / pair = $${{gpuCpp.toFixed(5)}} / pair`;
}}

document.addEventListener('DOMContentLoaded', () => {{
  ['avgDocTok', 'clusterSize', 'customN', 'gpuMode'].forEach(id =>
    document.getElementById(id).addEventListener('input', renderTable));
  renderTable();
}});
"""

    css = """
*,*::before,*::after{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;font-size:14px;line-height:1.6;color:#1a1a2e;background:#f5f5f7;margin:0;padding:0 0 48px}
header{background:#1a1a2e;color:#e2e8f0;padding:28px 40px 24px;border-bottom:3px solid #3b82f6}
header h1{margin:0 0 6px;font-size:20px;font-weight:600;color:#fff}
header p{margin:0;font-size:12px;color:#94a3b8}
header code{background:#334155;padding:1px 5px;border-radius:3px;font-size:11px;color:#93c5fd}
main{max-width:960px;margin:32px auto;padding:0 24px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:32px}
.mc{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 18px}
.ml{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:#64748b;margin-bottom:6px}
.mv{font-size:22px;font-weight:700;color:#1e293b}
.ms{font-size:11px;color:#94a3b8;margin-top:2px}
section{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:24px 28px;margin-bottom:20px}
h2{font-size:15px;font-weight:600;color:#1e293b;margin:0 0 16px;padding-bottom:10px;border-bottom:1px solid #f1f5f9}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:#64748b;padding:6px 10px;border-bottom:2px solid #e2e8f0}
tbody tr:nth-child(odd){background:#f8fafc}
tbody tr:hover{background:#f0f9ff}
td{padding:8px 10px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
td.num{text-align:right;white-space:nowrap}
td.cost{font-weight:600;color:#0f766e}
tfoot td{font-weight:600;border-top:2px solid #e2e8f0;background:#f8fafc}
code{background:#f1f5f9;padding:1px 5px;border-radius:3px;font-size:12px;color:#0f172a}
.est{font-size:10px;color:#94a3b8;font-style:italic}
.baseline{font-size:10px;color:#3b82f6;font-weight:400}
.cluster-tag{font-size:10px;background:#ede9fe;color:#5b21b6;padding:1px 6px;border-radius:3px;font-weight:500}
.note{margin-top:14px;padding:12px 14px;background:#f8fafc;border-left:3px solid #94a3b8;border-radius:0 4px 4px 0;font-size:12px;color:#475569;line-height:1.7}
.note strong{color:#334155}
.controls{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;padding:16px 18px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px}
.control-group label{display:block;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:#64748b;margin-bottom:6px}
.control-group input{width:100%;border:1px solid #cbd5e1;border-radius:5px;padding:7px 10px;font-size:14px;color:#1e293b;background:#fff}
.control-group input:focus{outline:2px solid #3b82f6;border-color:transparent}
.control-note{display:block;font-size:11px;color:#94a3b8;margin-top:4px}
.custom-row{background:#fffbeb !important}
#cpp-note{font-size:11px;color:#64748b;font-style:italic;margin-top:10px;display:block}
.gpu-section{border-left:4px solid #6366f1}
.gpu-section h2{color:#3730a3}
.gpu-table td:first-child{font-weight:500;color:#1e293b;width:220px}
.gpu-note{margin-top:14px;padding:12px 14px;background:#eef2ff;border-left:3px solid #6366f1;border-radius:0 4px 4px 0;font-size:12px;color:#3730a3;line-height:1.7}
.tier-pill{display:inline-block;font-size:10px;font-weight:700;padding:1px 7px;border-radius:10px;margin-right:4px}
.tier-api{background:#dbeafe;color:#1e40af}
.tier-gpu{background:#ede9fe;color:#5b21b6}
.api-header{background:#eff6ff;color:#1e40af}
.gpu-header{background:#ede9fe;color:#5b21b6}
.gpu-col{border-left:2px solid #ede9fe}
.savings-header{background:#f0fdf4;color:#166534;text-align:center !important;border-left:2px solid #bbf7d0}
.savings-col{border-left:2px solid #bbf7d0;font-weight:600;color:#15803d;white-space:nowrap}
.savings-mult{font-size:10px;font-weight:700;color:#166534;opacity:.8}
thead tr:first-child th{border-bottom:1px solid #e2e8f0}
thead tr:last-child th{font-size:10px;padding:4px 10px;border-bottom:2px solid #e2e8f0}
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SECO — API Costing Report</title>
  <style>{css}</style>
</head>
<body>
<header>
  <h1>SECO — API Costing Report</h1>
  <p>
    Generated: {generated_at} &nbsp;·&nbsp;
    Model: <code>{MODEL}</code> &nbsp;·&nbsp;
    Input: <code>${COST_INPUT_PER_TOKEN * 1_000_000:.0f} / MTok</code> &nbsp;·&nbsp;
    Output: <code>${COST_OUTPUT_PER_TOKEN * 1_000_000:.0f} / MTok</code>
  </p>
</header>
<main>
  {cards_html}

  <section>
    <h2>1 · Document Corpus</h2>
    <table>
      <thead>
        <tr><th>ID</th><th>Title</th><th>Authority</th><th>Cluster</th><th>Pages</th><th>Words</th></tr>
      </thead>
      <tbody>{doc_rows_html}</tbody>
    </table>
    <div class="note">
      Cluster = subfolder under <code>documents/</code>. Only intra-cluster pairs are analyzed.
      Per-document token counts are estimated at words × 1.3; pair-level counts below are exact (count_tokens API).
    </div>
  </section>

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
      <strong>Prompt overhead</strong> = system prompt + pair prompt template ({prompt_overhead:,} tokens, constant per call).<br>
      <strong>Output estimate</strong>: {OUTPUT_TOKENS_PER_PAIR_EST:,} tokens/pair (upper bound; observed 2,000–3,500).
    </div>
  </section>

  {gpu_html}

  <section>
    <h2>4 · Cost Extrapolation</h2>
    <div class="controls" style="grid-template-columns:1fr 1fr 1fr">
      <div class="control-group">
        <label>Avg. document size (tokens)</label>
        <input id="avgDocTok" type="number" value="{avg_doc_tok}" min="500" step="500">
        <span class="control-note">Default: derived from count_tokens measurements ({avg_doc_tok:,} tok/doc)</span>
      </div>
      <div class="control-group">
        <label>Avg. cluster size (docs per topic)</label>
        <input id="clusterSize" type="number" value="{current_cluster_size}" min="2" step="1">
        <span class="control-note">Default: current lighting cluster ({current_cluster_size} docs)</span>
      </div>
      <div class="control-group">
        <label>GPU pricing tier</label>
        <select id="gpuMode" style="width:100%;border:1px solid #cbd5e1;border-radius:5px;padding:7px 10px;font-size:14px;color:#1e293b;background:#fff">
          <option value="on-demand">On-demand ($0.526/hr)</option>
          <option value="spot">Spot (~$0.158/hr)</option>
        </select>
        <span class="control-note">g4dn.xlarge, eu-central-1 · Mistral 7B Q4_K_M</span>
      </div>
    </div>
    <table>
      <thead>
        <tr>
          <th rowspan="2">Total docs (N)</th>
          <th rowspan="2">Clusters</th>
          <th rowspan="2">Total pairs</th>
          <th rowspan="2">New pairs +1 doc</th>
          <th colspan="2" class="api-header" style="text-align:center">Claude API</th>
          <th colspan="2" class="gpu-header" style="text-align:center">GPU (g4dn.xlarge)</th>
          <th rowspan="2" class="savings-header">Savings<br><span style="font-weight:400;font-size:9px">full build · API−GPU</span></th>
        </tr>
        <tr>
          <th class="api-header">+1 doc</th>
          <th class="api-header">Full build</th>
          <th class="gpu-header">+1 doc</th>
          <th class="gpu-header">Full build</th>
        </tr>
      </thead>
      <tbody id="extrap-body"></tbody>
      <tfoot>
        <tr>
          <td colspan="4" style="text-align:right;font-weight:400;font-size:12px">Custom N →</td>
          <td colspan="5" style="padding:4px 10px">
            <input id="customN" type="number" value="1000" min="10" step="10"
              style="width:100%;border:1px solid #cbd5e1;border-radius:4px;padding:4px 8px;font-size:13px">
          </td>
        </tr>
      </tfoot>
    </table>
    <span id="cpp-note"></span>
    <div class="note">
      <strong>Cluster model:</strong> documents in the same topic folder are compared pairwise;
      cross-cluster pairs are never run. Adding 1 document to an existing cluster of size C
      triggers exactly C−1 new LLM calls — independent of the total corpus size N.
      This bounds ingestion cost at O(C), not O(N).<br><br>
      <strong>Full build</strong> = cost to analyze a fresh corpus from scratch.
      <strong>1 addition</strong> = marginal cost of adding one document to an existing cluster (all other pairs cached).
      GPU costs exclude instance startup (~2 min); break-even favors GPU at ~10+ analyses/day.<br><br>
      <strong>Note — production costs only.</strong>
      The figures above reflect steady-state operation on a stable prompt and schema.
      Development and experimentation add an unknown multiple on top: prompt iterations, schema changes that bust the cache,
      exploratory runs on new document sets, and benchmark comparisons all generate calls that never reach production.
      In practice the stack will be a mix across tiers — higher budget means less discipline around token usage and faster iteration;
      lower budget means trading iteration speed for cost, running more locally and being deliberate about when to call the API.
      Either way, the production marginal cost is low enough that budget pressure mostly lands on the development phase, not the deployment.
    </div>
  </section>

</main>
<script>{js}</script>
</body>
</html>"""


# ── Entry point ────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Generate API costing report")
    parser.add_argument("--output", default=str(ROOT / "documentation" / "costing.html"))
    args = parser.parse_args()

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    docs = get_extracted()
    doc_list = list(docs.values())

    print("Counting prompt overhead...")
    prompt_overhead = count_prompt_overhead(client)
    print(f"  {prompt_overhead:,} tokens")

    print("Counting tokens per pair (count_tokens API — no charge)...")
    pair_stats = []
    for i in range(len(doc_list)):
        for j in range(i + 1, len(doc_list)):
            da, db = doc_list[i], doc_list[j]
            # Only measure intra-cluster pairs (mirrors analyze.py behavior)
            if da.get("cluster") != db.get("cluster"):
                continue
            print(f"  {da['id']} × {db['id']}...")
            input_tokens = count_pair_input_tokens(client, da, db)
            cost = (
                input_tokens * COST_INPUT_PER_TOKEN
                + OUTPUT_TOKENS_PER_PAIR_EST * COST_OUTPUT_PER_TOKEN
            )
            pair_stats.append(
                {
                    "doc_a": da["id"],
                    "doc_b": db["id"],
                    "cluster": da.get("cluster", "default"),
                    "input_tokens": input_tokens,
                    "cost_usd": cost,
                }
            )
            print(f"    → {input_tokens:,} tokens · ${cost:.4f}")

    avg_doc_tok = avg_doc_tokens_from_pairs(pair_stats, prompt_overhead)
    cluster_sizes = {}
    for doc in doc_list:
        c = doc.get("cluster", "default")
        cluster_sizes[c] = cluster_sizes.get(c, 0) + 1
    current_cluster_size = (
        round(sum(cluster_sizes.values()) / len(cluster_sizes)) if cluster_sizes else 3
    )

    print(f"\nAvg. doc tokens (derived): {avg_doc_tok:,}")
    print(f"Avg. cluster size: {current_cluster_size}")

    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    html = generate_html(
        doc_list, prompt_overhead, pair_stats, avg_doc_tok, current_cluster_size, generated_at
    )

    out = Path(args.output)
    out.parent.mkdir(exist_ok=True)
    out.write_text(html)
    print(f"\nReport written → {out}")


if __name__ == "__main__":
    main()
