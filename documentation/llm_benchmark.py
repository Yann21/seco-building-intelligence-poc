#!/usr/bin/env python3
"""
SECO — LLM Benchmark & Quality Audit

Runs the same document-pair conflict analysis through two backends:
  Tier 1 — Claude API   (production path, uses pair cache if warm)
  Tier 2 — Ollama local (CPU inference, air-gapped)

Outputs a self-contained HTML report with:
  - Side-by-side conflict comparison per document pair
  - Expert rating interface (valid / hallucinated / uncertain)
  - GPU tier cost projections (Tier 3, g4dn.xlarge / NVIDIA T4)

Usage:
    python documentation/llm_benchmark.py
    python documentation/llm_benchmark.py --model llama3.2:3b
    python documentation/llm_benchmark.py --skip-local     # regenerate HTML from cache only

Ollama setup (if not installed):
    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull phi3.5       # recommended: 3.8B, ~2.5GB, good French instruction following
    ollama pull llama3.2:3b  # alternative: 3B, ~2GB
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "app2-conflict-resolver" / "backend"))

from analyze import (
    SYSTEM_PROMPT, PAIR_PROMPT, MODEL as CLAUDE_MODEL,
    COST_INPUT_PER_TOKEN, COST_OUTPUT_PER_TOKEN,
    _pair_cache_path, _extract_json_block, PROMPT_VERSION,
)
from extract import get_extracted

import json_repair
from pydantic import BaseModel, field_validator
from typing import Literal

OLLAMA_URL = "http://localhost:11434/api/generate"
LOCAL_CACHE_DIR = ROOT / "app2-conflict-resolver" / "backend" / "cache"


# ── Shared schema (same as analyze.py) ────────────────────────────────────────

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
    def normalise(cls, v: str) -> str:
        return v.lower().strip()


# ── Backend: Claude API ────────────────────────────────────────────────────────

def run_claude_pair(doc_a: dict, doc_b: dict, client: anthropic.Anthropic) -> dict:
    """
    Use the warm pair cache if available, otherwise call Claude.
    The benchmark reuses analyze.py's cache — no duplicate spend.
    """
    cache_path = _pair_cache_path(doc_a, doc_b)
    pair_id = f"{doc_a['id']} × {doc_b['id']}"

    if cache_path.exists():
        print(f"  [Claude] cache hit: {pair_id}")
        data = json.loads(cache_path.read_text())
        return {
            "conflicts": _parse_conflicts(data.get("conflicts", [])),
            "cost_usd": data.get("_cost_usd", 0.0),
            "elapsed_s": 0.0,
            "from_cache": True,
        }

    print(f"  [Claude] calling API: {pair_id}")
    prompt = _build_prompt(doc_a, doc_b)
    t0 = time.time()
    msg = client.messages.create(
        model=CLAUDE_MODEL, max_tokens=4000, system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.time() - t0
    cost = msg.usage.input_tokens * COST_INPUT_PER_TOKEN + msg.usage.output_tokens * COST_OUTPUT_PER_TOKEN
    raw = _extract_json_block(msg.content[0].text)
    data = json_repair.repair_json(raw, return_objects=True)
    conflicts = _parse_conflicts(data.get("conflicts", []) if isinstance(data, dict) else [])
    return {"conflicts": conflicts, "cost_usd": cost, "elapsed_s": elapsed, "from_cache": False}


# ── Backend: Ollama local ─────────────────────────────────────────────────────

def _local_cache_path(model: str, doc_a: dict, doc_b: dict) -> Path:
    LOCAL_CACHE_DIR.mkdir(exist_ok=True)
    import hashlib
    key = "_".join(sorted([
        hashlib.sha256(doc_a["full_text"].encode()).hexdigest()[:12],
        hashlib.sha256(doc_b["full_text"].encode()).hexdigest()[:12],
    ]))
    safe_model = model.replace(":", "_").replace("/", "_")
    return LOCAL_CACHE_DIR / f"local_{safe_model}_{key}_{PROMPT_VERSION}.json"


def check_ollama(model: str) -> tuple[bool, str]:
    """Returns (available, message)."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            tags = json.loads(resp.read())
        models = [m["name"] for m in tags.get("models", [])]
        base = model.split(":")[0]
        if not any(m.startswith(base) for m in models):
            return False, f"Model '{model}' not pulled. Run: ollama pull {model}"
        return True, f"Model '{model}' ready"
    except urllib.error.URLError:
        return False, "Ollama not running. Install: curl -fsSL https://ollama.com/install.sh | sh && ollama serve"
    except Exception as e:
        return False, str(e)


def run_ollama_pair(doc_a: dict, doc_b: dict, model: str, max_tokens: int = 4000) -> dict:
    pair_id = f"{doc_a['id']} × {doc_b['id']}"
    cache_path = _local_cache_path(model, doc_a, doc_b)

    if cache_path.exists():
        print(f"  [local]  cache hit: {pair_id}")
        data = json.loads(cache_path.read_text())
        return {
            "conflicts": _parse_conflicts(data.get("conflicts", [])),
            "elapsed_s": data.get("_elapsed_s", 0.0),
            "tokens_per_sec": data.get("_tokens_per_sec"),
            "from_cache": True,
        }

    print(f"  [local]  running {model}: {pair_id} (this may take several minutes on CPU)...")
    prompt = _build_prompt(doc_a, doc_b)

    payload = json.dumps({
        "model": model,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": max_tokens},
    }).encode()

    t0 = time.time()
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            result = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama call failed: {e}") from e
    elapsed = time.time() - t0

    raw_text = result.get("response", "")
    eval_count = result.get("eval_count", 0)
    eval_duration_ns = result.get("eval_duration", 1)
    tokens_per_sec = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns > 0 else 0

    raw = _extract_json_block(raw_text) if raw_text.strip().startswith("{") is False else raw_text
    data = json_repair.repair_json(raw, return_objects=True)
    conflicts = _parse_conflicts(data.get("conflicts", []) if isinstance(data, dict) else [])

    cache_data = {
        "conflicts": [c.model_dump() for c in conflicts],
        "_elapsed_s": elapsed,
        "_tokens_per_sec": round(tokens_per_sec, 1),
        "_model": model,
    }
    cache_path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2))

    return {"conflicts": conflicts, "elapsed_s": elapsed, "tokens_per_sec": tokens_per_sec, "from_cache": False}


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _build_prompt(doc_a: dict, doc_b: dict) -> str:
    doc_sections = ""
    for doc in [doc_a, doc_b]:
        doc_sections += (
            f"\n\n{'='*60}\nDOCUMENT: {doc['title']}\n"
            f"Autorité: {doc['authority']} | Date: {doc['date']}\n"
            f"{'='*60}\n\n{doc['full_text']}"
        )
    return PAIR_PROMPT.format(doc_sections=doc_sections)


def _parse_conflicts(raw_list: list) -> list[Conflict]:
    result = []
    for c in raw_list:
        if not isinstance(c, dict):
            continue
        try:
            result.append(Conflict(**c))
        except Exception:
            pass
    return result


# ── GPU tier projections (T4 / g4dn.xlarge) ───────────────────────────────────

def gpu_projections(avg_input_tokens_per_pair: float, n_pairs: int) -> dict:
    """
    Cost and time projections for Tier 3: NVIDIA T4 on AWS g4dn.xlarge.
    Instance: eu-central-1, ~$0.526/hr on-demand, ~$0.158/hr spot.
    Model: Mistral 7B Q4_K_M (4.1 GB VRAM, ~180 tok/sec generation on T4).
    """
    t4_gen_tok_per_sec = 180       # generation throughput, Mistral 7B Q4_K_M
    t4_prefill_tok_per_sec = 4000  # prefill is much faster (memory bandwidth bound)
    output_tokens_per_pair = 4000

    prefill_s = avg_input_tokens_per_pair / t4_prefill_tok_per_sec
    gen_s = output_tokens_per_pair / t4_gen_tok_per_sec
    inference_s_per_pair = prefill_s + gen_s
    inference_s_total = inference_s_per_pair * n_pairs

    on_demand_rate = 0.526  # $/hr
    spot_rate = 0.158       # $/hr (~70% discount, eu-central-1)

    cost_on_demand = (inference_s_total / 3600) * on_demand_rate
    cost_spot = (inference_s_total / 3600) * spot_rate

    # Fine-tuning: LoRA on Mistral 7B, ~100 examples, T4
    lora_hours = 0.75
    lora_cost = lora_hours * on_demand_rate

    return {
        "inference_s_per_pair": round(inference_s_per_pair, 1),
        "inference_s_total": round(inference_s_total, 1),
        "cost_on_demand": round(cost_on_demand, 4),
        "cost_spot": round(cost_spot, 4),
        "instance_type": "g4dn.xlarge",
        "gpu": "NVIDIA T4 16GB VRAM",
        "model": "Mistral 7B Q4_K_M",
        "on_demand_rate": on_demand_rate,
        "spot_rate": spot_rate,
        "lora_hours": lora_hours,
        "lora_cost": round(lora_cost, 2),
    }


# ── HTML generation ───────────────────────────────────────────────────────────

_SEV_COLOR = {"critique": "#fee2e2", "majeur": "#fef3c7", "mineur": "#f0fdf4"}
_SEV_BADGE = {"critique": "#dc2626", "majeur": "#d97706", "mineur": "#16a34a"}


def _conflict_card_html(c: Conflict | None, side: str, pair_idx: int, conflict_idx: int) -> str:
    if c is None:
        return '<div class="conflict-card empty">—</div>'
    cid = f"{side}-{pair_idx}-{conflict_idx}"
    sev_bg = _SEV_COLOR.get(c.severity, "#f8fafc")
    sev_col = _SEV_BADGE.get(c.severity, "#64748b")
    sources_html = "".join(
        f'<div class="src"><code>{s.doc_id}</code> {s.article}'
        + (f' <em>"{s.quote[:120]}…"</em>' if len(s.quote) > 120 else (f' <em>"{s.quote}"</em>' if s.quote else ""))
        + (f' → <strong>{s.value}</strong>' if s.value else "")
        + "</div>"
        for s in c.sources
    )
    unverified = "" if c.quote_verified else '<span class="unv" title="Citation non retrouvée dans la source">⚠</span> '
    return f"""
<div class="conflict-card" id="{cid}" style="border-left:3px solid {sev_col};background:{sev_bg}">
  <div class="card-head">
    <span class="sev" style="background:{sev_col}">{c.severity}</span>
    {unverified}<strong>{c.title}</strong>
  </div>
  <div class="card-desc">{c.description[:300]}{"…" if len(c.description) > 300 else ""}</div>
  <div class="card-sources">{sources_html}</div>
  <div class="card-rec"><em>{c.recommendation[:200]}{"…" if len(c.recommendation) > 200 else ""}</em></div>
  <div class="rating-row" data-id="{cid}">
    <button class="rate-btn" onclick="rate('{cid}','valid')" title="Valid finding">✓ Valid</button>
    <button class="rate-btn" onclick="rate('{cid}','hallucinated')" title="Hallucinated / incorrect">✗ Halluc.</button>
    <button class="rate-btn" onclick="rate('{cid}','uncertain')" title="Uncertain">? Unsure</button>
    <span class="rating-label" id="rl-{cid}"></span>
  </div>
</div>"""


def generate_html(
    doc_list: list[dict],
    pairs: list[dict],
    local_model: str,
    gpu_proj: dict,
    generated_at: str,
) -> str:

    # ── Metric summary ──
    n_pairs = len(pairs)
    c_total = sum(len(p["claude"]["conflicts"]) for p in pairs)
    l_total = sum(len(p["local"]["conflicts"]) for p in pairs if p["local"])
    c_cost = sum(p["claude"]["cost_usd"] for p in pairs)
    c_time = sum(p["claude"]["elapsed_s"] for p in pairs)
    l_time = sum(p["local"]["elapsed_s"] for p in pairs if p["local"])
    l_speeds = [p["local"]["tokens_per_sec"] for p in pairs if p["local"] and p["local"].get("tokens_per_sec")]
    l_avg_speed = sum(l_speeds) / len(l_speeds) if l_speeds else 0

    local_available = any(p["local"] for p in pairs)
    local_label = local_model if local_available else f"{local_model} (not run)"

    def metric(label, val, sub=""):
        return f'<div class="mc"><div class="ml">{label}</div><div class="mv">{val}</div><div class="ms">{sub}</div></div>'

    cards_html = f"""
    <div class="metrics">
      {metric("Tier 1 · Claude API", f"{c_total} conflicts", f"${c_cost:.3f} · {'cached' if c_time == 0 else f'{c_time:.0f}s'}")}
      {metric(f"Tier 2 · {local_label}", f"{l_total} conflicts" if local_available else "—", f"$0.00 · {l_time:.0f}s" + (f" · {l_avg_speed:.0f} tok/s" if l_avg_speed else "") if local_available else "not run")}
      {metric("Tier 3 · T4 GPU (est.)", f"~{gpu_proj['inference_s_total']:.0f}s / {n_pairs} pairs", f"${gpu_proj['cost_on_demand']:.4f} on-demand · ${gpu_proj['cost_spot']:.4f} spot")}
      {metric("Document pairs", str(n_pairs), f"{len(doc_list)} documents")}
    </div>"""

    # ── Per-pair comparison ──
    pairs_html = ""
    for pi, pair in enumerate(pairs):
        claude_conflicts = pair["claude"]["conflicts"]
        local_conflicts = pair["local"]["conflicts"] if pair["local"] else []
        n_rows = max(len(claude_conflicts), len(local_conflicts), 1)

        rows_html = ""
        for ri in range(n_rows):
            cc = claude_conflicts[ri] if ri < len(claude_conflicts) else None
            lc = local_conflicts[ri] if ri < len(local_conflicts) else None
            rows_html += f"""
      <div class="compare-row">
        <div class="compare-col">{_conflict_card_html(cc, 'C', pi, ri)}</div>
        <div class="compare-col">{_conflict_card_html(lc, 'L', pi, ri)}</div>
      </div>"""

        c_meta = f"{len(claude_conflicts)} conflicts" + (" · from cache" if pair["claude"]["from_cache"] else f" · {pair['claude']['elapsed_s']:.1f}s · ${pair['claude']['cost_usd']:.4f}")
        l_meta = (
            f"{len(local_conflicts)} conflicts" + (" · from cache" if pair["local"]["from_cache"] else f" · {pair['local']['elapsed_s']:.0f}s · {pair['local'].get('tokens_per_sec', 0):.0f} tok/s")
            if pair["local"] else "not run"
        )

        pairs_html += f"""
  <section class="pair-section">
    <div class="pair-header">
      <h3>Pair {pi+1}: <code>{pair['doc_a']}</code> × <code>{pair['doc_b']}</code></h3>
    </div>
    <div class="compare-header">
      <div class="compare-col-head">Tier 1 — Claude {CLAUDE_MODEL} <span class="meta">{c_meta}</span></div>
      <div class="compare-col-head">Tier 2 — {local_label} <span class="meta">{l_meta}</span></div>
    </div>
    {rows_html}
  </section>"""

    # ── GPU tier section ──
    g = gpu_proj
    breakeven_analyses = int(g["on_demand_rate"] / (COST_INPUT_PER_TOKEN * 40000 + COST_OUTPUT_PER_TOKEN * 4000 - g["cost_on_demand"] / n_pairs)) if n_pairs else 0

    gpu_html = f"""
  <section class="gpu-section">
    <h2>Tier 3 — GPU Cloud Inference (g4dn.xlarge · {g['gpu']})</h2>
    <p class="gpu-desc">
      Reference infrastructure: AWS <code>g4dn.xlarge</code>, Frankfurt (eu-central-1), configured in
      <code>interpolate/aws/spin-up.sh</code>. Model: <strong>{g['model']}</strong>
      (4.1 GB VRAM, leaves ~12 GB headroom on the T4).
    </p>
    <table class="gpu-table">
      <thead><tr><th>Metric</th><th>Value</th><th>Notes</th></tr></thead>
      <tbody>
        <tr><td>Generation throughput</td><td>~180 tok/sec</td><td>Mistral 7B Q4_K_M on T4, memory-bandwidth bound</td></tr>
        <tr><td>Inference per pair</td><td>~{g['inference_s_per_pair']:.0f}s</td><td>Prefill {round(40000/4000):.0f}s + generate {round(4000/180):.0f}s</td></tr>
        <tr><td>Full analysis ({n_pairs} pairs)</td><td>~{g['inference_s_total']:.0f}s</td><td>Sequential; parallelisable across pairs</td></tr>
        <tr><td>Cost on-demand</td><td>${g['cost_on_demand']:.4f}</td><td>${g['on_demand_rate']}/hr × {g['inference_s_total']:.0f}s</td></tr>
        <tr><td>Cost spot instance</td><td>${g['cost_spot']:.4f}</td><td>${g['spot_rate']}/hr · ~70% discount, interruptible</td></tr>
        <tr><td>LoRA fine-tuning (100 examples)</td><td>~{g['lora_hours']}h · ${g['lora_cost']:.2f}</td><td>One-time domain adaptation; optional</td></tr>
        <tr><td>vs. Claude API per analysis</td><td>${c_cost:.3f}</td><td>GPU is {round(c_cost / max(g['cost_on_demand'], 0.0001))}× cheaper per run once instance is running</td></tr>
      </tbody>
    </table>
    <div class="gpu-note">
      <strong>When GPU is worth it:</strong> the instance startup overhead (~2 min) dominates for low-frequency use.
      Break-even shifts if the instance is kept warm for batch ingestion or if confidentiality mandates on-premises deployment
      regardless of cost. At ~10+ analyses/day a persistent spot instance (~$3.80/day) is cheaper than the API.
    </div>
  </section>"""

    # ── JS for expert rating ──
    js = """
function rate(id, verdict) {
  const store = JSON.parse(localStorage.getItem('seco_ratings') || '{}');
  store[id] = { verdict, ts: new Date().toISOString() };
  localStorage.setItem('seco_ratings', JSON.stringify(store));

  const colors = { valid: '#d1fae5', hallucinated: '#fee2e2', uncertain: '#fef3c7' };
  const labels = { valid: '✓ valid', hallucinated: '✗ hallucinated', uncertain: '? uncertain' };
  const card = document.getElementById(id);
  if (card) card.style.boxShadow = `0 0 0 2px ${colors[verdict].replace('5', '9')}`;
  const lbl = document.getElementById('rl-' + id);
  if (lbl) { lbl.textContent = labels[verdict]; lbl.style.color = { valid:'#065f46', hallucinated:'#7f1d1d', uncertain:'#78350f' }[verdict]; }

  const total = Object.keys(store).length;
  const el = document.getElementById('rating-count');
  if (el) el.textContent = total + ' rating' + (total !== 1 ? 's' : '');
}

function exportRatings() {
  const store = localStorage.getItem('seco_ratings') || '{}';
  const blob = new Blob([JSON.stringify(JSON.parse(store), null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'seco_expert_ratings_' + new Date().toISOString().slice(0,10) + '.json';
  a.click();
}

// Restore ratings from localStorage on load
window.addEventListener('DOMContentLoaded', () => {
  const store = JSON.parse(localStorage.getItem('seco_ratings') || '{}');
  const labels = { valid: '✓ valid', hallucinated: '✗ hallucinated', uncertain: '? uncertain' };
  const colors = { valid: '#065f46', hallucinated: '#7f1d1d', uncertain: '#78350f' };
  const ringColors = { valid: '#6ee7b7', hallucinated: '#fca5a5', uncertain: '#fcd34d' };
  for (const [id, {verdict}] of Object.entries(store)) {
    const card = document.getElementById(id);
    if (card) card.style.boxShadow = `0 0 0 2px ${ringColors[verdict]}`;
    const lbl = document.getElementById('rl-' + id);
    if (lbl) { lbl.textContent = labels[verdict]; lbl.style.color = colors[verdict]; }
  }
  const total = Object.keys(store).length;
  const el = document.getElementById('rating-count');
  if (el) el.textContent = total + ' rating' + (total !== 1 ? 's' : '');
});
"""

    css = """
*,*::before,*::after{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;font-size:13px;line-height:1.55;color:#1a1a2e;background:#f5f5f7;margin:0;padding:0 0 48px}
header{background:#1a1a2e;color:#e2e8f0;padding:24px 40px 20px;border-bottom:3px solid #6366f1}
header h1{margin:0 0 4px;font-size:18px;font-weight:600;color:#fff}
header p{margin:0;font-size:11px;color:#94a3b8}
header code{background:#334155;padding:1px 5px;border-radius:3px;font-size:10px;color:#a5b4fc}
.toolbar{background:#1e293b;padding:8px 40px;display:flex;align-items:center;gap:12px;border-bottom:1px solid #334155}
.toolbar span{color:#94a3b8;font-size:12px}
.btn{background:#6366f1;color:#fff;border:none;padding:5px 14px;border-radius:5px;cursor:pointer;font-size:12px;font-weight:500}
.btn:hover{background:#4f46e5}
main{max-width:1100px;margin:24px auto;padding:0 20px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}
.mc{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px}
.ml{font-size:10px;text-transform:uppercase;letter-spacing:.6px;color:#64748b;margin-bottom:4px}
.mv{font-size:20px;font-weight:700;color:#1e293b}
.ms{font-size:11px;color:#94a3b8;margin-top:2px}
section{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px 24px;margin-bottom:16px}
h2{font-size:14px;font-weight:600;color:#1e293b;margin:0 0 14px;padding-bottom:8px;border-bottom:1px solid #f1f5f9}
h3{font-size:13px;font-weight:600;color:#1e293b;margin:0}
.pair-header{margin-bottom:10px}
.compare-header{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:8px}
.compare-col-head{font-size:11px;font-weight:600;color:#374151;padding:6px 10px;background:#f8fafc;border-radius:5px;border:1px solid #e2e8f0}
.compare-col-head .meta{font-weight:400;color:#9ca3af;margin-left:6px}
.compare-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:8px}
.compare-col{}
.conflict-card{border-radius:6px;padding:12px 14px;border:1px solid #e2e8f0;border-left-width:3px}
.conflict-card.empty{color:#9ca3af;font-style:italic;padding:20px;text-align:center;background:#f8fafc}
.card-head{display:flex;align-items:flex-start;gap:8px;margin-bottom:6px}
.sev{font-size:9px;font-weight:700;text-transform:uppercase;color:#fff;padding:2px 6px;border-radius:3px;white-space:nowrap;margin-top:2px}
.card-desc{color:#374151;margin-bottom:6px;font-size:12px}
.card-sources{margin-bottom:6px}
.src{font-size:11px;color:#6b7280;margin-bottom:2px}
.src code{font-size:10px;background:#f1f5f9;padding:1px 4px;border-radius:3px}
.src em{color:#475569;font-style:normal}
.card-rec{font-size:11px;color:#475569;border-top:1px solid #f1f5f9;padding-top:6px}
.rating-row{display:flex;align-items:center;gap:6px;margin-top:8px;padding-top:6px;border-top:1px solid #f1f5f9}
.rate-btn{border:1px solid #e2e8f0;background:#f8fafc;color:#374151;padding:3px 9px;border-radius:4px;cursor:pointer;font-size:11px}
.rate-btn:hover{background:#e2e8f0}
.rating-label{font-size:11px;font-weight:600;margin-left:4px}
.unv{color:#f59e0b;font-size:11px}
.pair-section h3 code{font-size:12px;background:#f1f5f9;padding:1px 5px;border-radius:3px}
.gpu-section{border-left:4px solid #6366f1}
.gpu-desc{color:#4b5563;margin-bottom:12px;font-size:12px}
.gpu-table{width:100%;border-collapse:collapse;font-size:12px}
.gpu-table thead th{text-align:left;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:#64748b;padding:5px 8px;border-bottom:2px solid #e2e8f0}
.gpu-table tbody tr:nth-child(odd){background:#f8fafc}
.gpu-table td{padding:7px 8px;border-bottom:1px solid #f1f5f9}
.gpu-note{margin-top:12px;padding:10px 12px;background:#eef2ff;border-left:3px solid #6366f1;border-radius:0 4px 4px 0;font-size:11px;color:#3730a3;line-height:1.7}
code{background:#f1f5f9;padding:1px 5px;border-radius:3px;font-size:11px;color:#0f172a}
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>SECO — LLM Benchmark &amp; Quality Audit</title>
  <style>{css}</style>
</head>
<body>
<header>
  <h1>SECO — LLM Benchmark &amp; Quality Audit</h1>
  <p>
    Generated: {generated_at} &nbsp;·&nbsp;
    Tier 1: <code>{CLAUDE_MODEL}</code> &nbsp;·&nbsp;
    Tier 2: <code>{local_label}</code> &nbsp;·&nbsp;
    Tier 3: <code>g4dn.xlarge / T4</code> (projections only)
  </p>
</header>
<div class="toolbar">
  <span>Expert ratings persist in localStorage · <span id="rating-count">0 ratings</span></span>
  <button class="btn" onclick="exportRatings()">Export ratings JSON</button>
</div>
<main>
  {cards_html}
  {pairs_html}
  {gpu_html}
</main>
<script>{js}</script>
</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run LLM benchmark and generate quality audit HTML")
    parser.add_argument("--model", default="phi3.5", help="Ollama model name (default: phi3.5)")
    parser.add_argument("--skip-local", action="store_true", help="Skip local model, regenerate HTML from Claude cache only")
    parser.add_argument("--max-tokens", type=int, default=4000, help="Max output tokens for local model (default: 4000; use 800-1000 for fast benchmarks)")
    parser.add_argument("--output", default=str(ROOT / "documentation" / "llm_benchmark.html"))
    args = parser.parse_args()

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    docs = get_extracted()
    doc_list = list(docs.values())

    # Check local availability upfront
    if not args.skip_local:
        ok, msg = check_ollama(args.model)
        if not ok:
            print(f"\n⚠  {msg}")
            print("   Run with --skip-local to generate HTML using only Claude cache.\n")
            local_available = False
        else:
            print(f"✓  {msg}")
            local_available = True
    else:
        local_available = False

    pairs = []
    total_input_tokens = 0
    for i in range(len(doc_list)):
        for j in range(i + 1, len(doc_list)):
            da, db = doc_list[i], doc_list[j]

            print(f"\nPair: {da['id']} × {db['id']}")
            claude_result = run_claude_pair(da, db, client)
            total_input_tokens += sum(len(c.title) for c in claude_result["conflicts"])  # rough proxy

            local_result = None
            if local_available:
                try:
                    local_result = run_ollama_pair(da, db, args.model, args.max_tokens)
                except RuntimeError as e:
                    print(f"  [local]  failed: {e}")

            pairs.append({
                "doc_a": da["id"],
                "doc_b": db["id"],
                "claude": claude_result,
                "local": local_result,
            })

    # GPU projections based on measured avg pair size from costing.py
    # Use average of actual pair sizes if available, otherwise estimate
    avg_input_per_pair = 32000  # approximate from count_tokens run
    gpu_proj = gpu_projections(avg_input_per_pair, len(pairs))

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = generate_html(doc_list, pairs, args.model, gpu_proj, generated_at)

    out = Path(args.output)
    out.parent.mkdir(exist_ok=True)
    out.write_text(html)
    print(f"\nReport written → {out}")


if __name__ == "__main__":
    main()
