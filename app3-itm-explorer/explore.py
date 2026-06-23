#!/usr/bin/env python3
"""
ITM Corpus Explorer
  1. Scrape itm.public.lu for all French ITM-CL/ET/SST PDFs
  2. Download PDFs (cached — skips existing files)
  3. Extract text with pdfplumber
  4. Keep only text-extractable docs; derive a meaningful title via LLM
  5. Embed with OpenAI text-embedding-3-small
  6. Reduce to 2D with UMAP
  7. Generate interactive HTML report with Plotly

Scanned docs (no extractable text) are excluded from the semantic map and
reported separately as an OCR backlog.

Run: python explore.py
Output: report.html
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import dotenv
import numpy as np
import openai
import pdfplumber
import plotly.graph_objects as go
import requests
import umap
from bs4 import BeautifulSoup

dotenv.load_dotenv(Path(__file__).parent.parent / ".env")

BASE = Path(__file__).parent
PDFS = BASE / "data" / "pdfs"
CACHE = BASE / "data" / "cache"
PDFS.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://itm.public.lu"
INDEX_URL = f"{BASE_URL}/fr/securite-sante-travail/etablissements-classes/conditions-types.html"
EMBED_MODEL = "text-embedding-3-small"
TITLE_MODEL = "gpt-4o-mini"
MIN_WORDS = 100  # below this a doc is considered scanned / non-extractable
SKIP_LANGS = {"-en.pdf", "-de.pdf", "-lu.pdf", "-pt.pdf", "-fr.pdf"}


# ── 1. Scrape ─────────────────────────────────────────────────────────────────


def scrape_links() -> list[dict]:
    cached = CACHE / "links.json"
    if cached.exists():
        data = json.loads(cached.read_text())
        print(f"Links (cached): {len(data)} documents")
        return data

    print("Scraping ITM conditions-types page...")
    r = requests.get(INDEX_URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    seen: set[str] = set()
    links = []
    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if ".pdf" not in href.lower():
            continue
        if not href.startswith("http"):
            href = BASE_URL + href
        # Drop non-French versions
        lower = href.lower()
        if any(lower.endswith(s) for s in SKIP_LANGS):
            continue
        fname = href.split("/")[-1]
        # Only ITM-CL, ITM-ET, ITM-SST series
        if not re.match(r"^ITM-(CL|ET|SST)\b", fname, re.IGNORECASE):
            continue
        if href in seen:
            continue
        seen.add(href)
        label = a.get_text(strip=True) or re.sub(r"[-_]", " ", fname.replace(".pdf", ""))
        links.append({"label": label, "url": href, "filename": fname})

    cached.write_text(json.dumps(links, indent=2, ensure_ascii=False))
    print(f"  Found {len(links)} documents")
    return links


# ── 2. Download ───────────────────────────────────────────────────────────────


def download_pdfs(links: list[dict]) -> None:
    missing = [d for d in links if not (PDFS / d["filename"]).exists()]
    if not missing:
        print(f"PDFs (cached): all {len(links)} present")
        return
    print(f"\nDownloading {len(missing)}/{len(links)} PDFs...")
    for i, doc in enumerate(missing, 1):
        dest = PDFS / doc["filename"]
        try:
            r = requests.get(doc["url"], timeout=30)
            r.raise_for_status()
            dest.write_bytes(r.content)
            print(f"  [{i}/{len(missing)}] {doc['filename']}")
            time.sleep(0.25)
        except Exception as e:
            print(f"  [{i}/{len(missing)}] FAILED {doc['filename']}: {e}")


# ── 3. Extract text ───────────────────────────────────────────────────────────


def extract_texts(links: list[dict]) -> dict:
    cache_file = CACHE / "extracted.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
        print(f"Text extraction (cached): {len(data)} entries")
        return data

    print(f"\nExtracting text from {len(links)} PDFs...")
    result = {}
    for i, doc in enumerate(links, 1):
        pdf = PDFS / doc["filename"]
        if not pdf.exists():
            result[doc["filename"]] = {"text": "", "words": 0, "pages": 0}
            continue
        try:
            with pdfplumber.open(pdf) as p:
                pages = len(p.pages)
                text = " ".join((page.extract_text() or "").strip() for page in p.pages)
            words = len(text.split())
            result[doc["filename"]] = {"text": text[:10_000], "words": words, "pages": pages}
            if i % 20 == 0 or i == len(links):
                print(f"  [{i}/{len(links)}] {doc['filename']}: {words}w/{pages}p")
        except Exception as e:
            result[doc["filename"]] = {"text": "", "words": 0, "pages": 0}
            print(f"  [{i}/{len(links)}] ERROR {doc['filename']}: {e}")

    cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# ── 3b. Filter extractable ──────────────────────────────────────────────────


def split_extractable(links: list[dict], texts: dict) -> tuple[list[dict], list[dict]]:
    """Partition links into (extractable, scanned) by extracted word count."""
    extractable, scanned = [], []
    for doc in links:
        words = texts.get(doc["filename"], {}).get("words", 0)
        (extractable if words >= MIN_WORDS else scanned).append(doc)
    print(f"\nExtractable: {len(extractable)} · Scanned (OCR backlog): {len(scanned)}")
    return extractable, scanned


# ── 4a. LLM titles ────────────────────────────────────────────────────────────

TITLE_PROMPT = (
    "Voici le début d'un document réglementaire luxembourgeois de l'ITM. "
    "Donne UNIQUEMENT son objet/sujet en une courte phrase nominale française "
    "(max ~10 mots), sans le code ITM, sans guillemets, sans ponctuation finale. "
    "Exemple de réponse: Sécurité relative aux travaux en hauteur sur cordes\n\n---\n"
)


def extract_titles(links: list[dict], texts: dict) -> dict:
    cache_file = CACHE / "titles.json"
    cached = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    todo = [d for d in links if d["filename"] not in cached]
    if not todo:
        print(f"Titles (cached): {len(cached)}")
        return cached

    print(f"\nExtracting titles for {len(todo)} docs via {TITLE_MODEL}...")
    client = openai.OpenAI()

    def one(doc: dict) -> tuple[str, str]:
        snippet = texts.get(doc["filename"], {}).get("text", "")[:1200]
        try:
            resp = client.chat.completions.create(
                model=TITLE_MODEL,
                messages=[{"role": "user", "content": TITLE_PROMPT + snippet}],
                max_tokens=40,
                temperature=0,
            )
            title = resp.choices[0].message.content.strip().strip('"').rstrip(".")
            return doc["filename"], title[:90]
        except Exception as e:
            print(f"  title FAILED {doc['filename']}: {e}")
            return doc["filename"], doc["label"]

    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for fname, title in pool.map(one, todo):
            cached[fname] = title
            done += 1
            if done % 25 == 0 or done == len(todo):
                print(f"  [{done}/{len(todo)}] titled")

    cache_file.write_text(json.dumps(cached, ensure_ascii=False, indent=2))
    return cached


# ── 4b. Embed ─────────────────────────────────────────────────────────────────


def embed(links: list[dict], texts: dict, titles: dict) -> tuple[np.ndarray, list[dict]]:
    emb_file = CACHE / "embeddings.npy"
    meta_file = CACHE / "emb_meta.json"
    if emb_file.exists() and meta_file.exists():
        arr = np.load(emb_file)
        meta = json.loads(meta_file.read_text())
        print(f"Embeddings (cached): {arr.shape}")
        return arr, meta

    print(f"\nEmbedding {len(links)} docs with OpenAI {EMBED_MODEL}...")
    client = openai.OpenAI()

    sentences = []
    meta = []
    for doc in links:
        t = texts.get(doc["filename"], {})
        sentences.append(t.get("text", "").strip()[:8000])  # ~2k tokens max
        meta.append(
            {
                "code": doc["label"],
                "title": titles.get(doc["filename"], doc["label"]),
                "url": doc["url"],
                "filename": doc["filename"],
                "words": t.get("words", 0),
                "pages": t.get("pages", 0),
            }
        )

    all_embeddings = []
    BATCH = 100
    for i in range(0, len(sentences), BATCH):
        batch = sentences[i : i + BATCH]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch, encoding_format="float")
        all_embeddings.extend(e.embedding for e in resp.data)
        print(f"  [{min(i + BATCH, len(sentences))}/{len(sentences)}] embedded")

    arr = np.array(all_embeddings, dtype=np.float32)
    np.save(emb_file, arr)
    meta_file.write_text(json.dumps(meta, ensure_ascii=False))
    print(f"  Done: {arr.shape}")
    return arr, meta


# ── 5. UMAP ───────────────────────────────────────────────────────────────────


def run_umap(embeddings: np.ndarray) -> np.ndarray:
    umap_file = CACHE / "umap2d.npy"
    if umap_file.exists():
        coords = np.load(umap_file)
        print(f"UMAP (cached): {coords.shape}")
        return coords

    print("\nRunning UMAP...")
    n = len(embeddings)
    reducer = umap.UMAP(
        n_neighbors=min(15, n - 1),
        min_dist=0.1,
        metric="cosine",
        random_state=42,
        verbose=False,
    )
    coords = reducer.fit_transform(embeddings).astype(np.float32)
    np.save(umap_file, coords)
    print(f"  Done: {coords.shape}")
    return coords


# ── 6. Report ─────────────────────────────────────────────────────────────────

SERIES_COLORS = {
    "ITM-CL": "#3b82f6",
    "ITM-ET": "#f59e0b",
    "ITM-SST": "#10b981",
    "OTHER": "#94a3b8",
}

# Click-to-sort for any table.sortable. Headers carry data-type ("text"|"num");
# columns without it are not sortable. Missing/"—" values sort to the bottom in
# both directions. Plain JS string (not an f-string) so braces stay un-escaped.
SORT_SCRIPT = """<script>
(function () {
  function val(cell, type) {
    var t = cell.textContent.trim();
    if (type === 'num') {
      if (t === '' || t === '\\u2014') return null;
      var n = parseFloat(t.replace(/[^0-9.\\-]/g, ''));
      return isNaN(n) ? null : n;
    }
    return t.toLowerCase();
  }
  document.querySelectorAll('table.sortable').forEach(function (table) {
    var headers = Array.prototype.slice.call(table.tHead.rows[0].cells);
    headers.forEach(function (th, idx) {
      var type = th.getAttribute('data-type');
      if (!type) return;
      th.addEventListener('click', function () {
        var tbody = table.tBodies[0];
        var rows = Array.prototype.slice.call(tbody.rows);
        var asc = th.getAttribute('data-asc') !== 'true';
        headers.forEach(function (h) {
          h.removeAttribute('data-asc');
          h.classList.remove('sorted-asc', 'sorted-desc');
        });
        th.setAttribute('data-asc', asc);
        th.classList.add(asc ? 'sorted-asc' : 'sorted-desc');
        rows.sort(function (a, b) {
          var x = val(a.cells[idx], type), y = val(b.cells[idx], type);
          if (x === null && y === null) return 0;
          if (x === null) return 1;
          if (y === null) return -1;
          if (x < y) return asc ? -1 : 1;
          if (x > y) return asc ? 1 : -1;
          return 0;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });
})();
</script>"""


def parse_series(filename: str) -> str:
    m = re.match(r"^(ITM-(?:CL|ET|SST))", filename, re.IGNORECASE)
    return m.group(1).upper() if m else "OTHER"


# ── SECO relevance classifier ─────────────────────────────────────────────────
# Ground truth: ITM-SST-10001.4 (Missions des organismes de contrôle agréés).
# SECO = organismes de contrôle agréés acting on ITM's behalf.
# Relevant annexes: 4 (building safety + fire), 6 (refrigeration),
#   8 (construction sites), 9 (electrical), 10B (vertical transport), 16 (pressure).
# Three labels:
#   'seco'  — directly in SECO's inspection mandate
#   'maybe' — relevant for specific project types (healthcare, natation, etc.)
#   'out'   — worker/process safety, mobile equipment, industrial, agricultural

SECO_LABEL_META = {
    "seco": ("SECO", "#16a34a", "#dcfce7"),
    "maybe": ("Projet", "#b45309", "#fef9c3"),
    "out": ("—", "#94a3b8", "#f1f5f9"),
}


def seco_relevance(filename: str, title: str) -> str:
    t = title.lower()
    f = filename.lower()

    # Control body framework — defines SECO's mandate
    if "10001" in f:
        return "seco"

    # Annexe 10B — Vertical transport installed in buildings
    if any(
        kw in t
        for kw in [
            "ascenseur",
            "monte-charge",
            "monte charge",
            "escalier mécanique",
            "escaliers mécaniques",
            "trottoir roulant",
            "monte-escalier",
            "élévateur à plateforme",
            "plateformes de transport",
            "mobilité réduite",
            "appareils élévateurs à plateforme",
            "distinction entre ascenseur",
        ]
    ):
        return "seco"

    # Annexe 4B — Fire prevention by building type / fire systems
    if any(
        kw in t
        for kw in [
            "incendie",
            "désenfumage",
            "compartimentage",
            "extinction automatique",
            "stabilité au feu",
        ]
    ):
        if not any(neg in t for neg in ["pyrotechnique", "explosif", "concert en plein"]):
            return "seco"
    if "anti-feu" in t or "moyens de défense" in t:
        return "seco"
    # Facade fire resistance
    if "façades" in t and ("résistance" in t or "prévention" in t):
        return "seco"

    # Annexe 9 — Electrical in buildings
    if any(
        kw in t
        for kw in [
            "groupe électrogène",
            "poste de transformation",
            "coups de foudre",
            "impacts des coups",
            "risques liés aux éclairs",
            "règlement sur la protection contre",
        ]
    ):
        return "seco"
    if "foudre" in t:
        return "seco"
    if "installations électriques" in t and "atmosphère" not in t:
        return "seco"

    # Annexe 16 — Fixed pressure equipment in buildings
    if any(
        kw in t
        for kw in [
            "appareils sous pression fixes",
            "appareils et installations à vapeur",
            "réservoirs sous pression",
            "tuyauteries métalliques",
            "installations à fluide thermique",
            "appareils à vapeur",
        ]
    ):
        if not any(neg in t for neg in ["hydrogène", "oxygène", "cryogénique", "gaz liquéfié"]):
            return "seco"

    # Annexe 6 — Refrigeration
    if "production de froid" in t or "installations frigorifiques" in t:
        return "seco"

    # Annexe 8 — Construction / demolition sites
    if any(
        kw in t
        for kw in [
            "chantiers de construction",
            "chantier de construction",
            "sécurité sur les chantiers",
            "prévention dans le bâtiment",
            "travaux de démolition",
        ]
    ):
        return "seco"

    # Building HVAC
    if "ventilation et de conditionnement" in t or "conditionnement d'air" in t:
        return "seco"

    # Automated building access
    if "portes et portails" in t:
        return "seco"

    # Covered parking / pits in constructions
    if "parkings couverts" in t or "parkings mécaniques" in t or "garages et parkings" in t:
        return "seco"
    if "fosses de visite" in t:
        return "seco"

    # --- MAYBE (project-specific) ---
    if any(
        kw in t
        for kw in [
            "secteur santé",
            "établissements de soins",
            "établissements de santé",
            "stérilisation",
            "dialyse",
            "stations de soins",
            "pneumatique",
            "psychiatrique",
            "microbiologique",
            "pédiatrique",
            "lasers médicaux",
            "stockage dans le secteur",
            "hébergement pour",
            "structures d'accueil",
            "structures éducatives",
            "vestiaires",
            "cytostatique",
            "natation",
            "logements encadrés",
            "hébergement provisoire",
            "simulation d'évacuation",
            "évacuation de personnes",
            "salles d'exposition de véhicules",
            "éclairage de sécurité",
            "éclairage sur les lieux",
            "chantiers d'assainissement",
            "échafaudage",
            "ponts élévateurs de véhicules",
            "amiante",
            "installations de levage pour personnes",
            "appareils de levage pour personnes",
        ]
    ):
        return "maybe"

    return "out"


_FR_MONTHS = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
}
_DATE_RE = re.compile(
    r"\b(" + "|".join(_FR_MONTHS) + r")\s+((?:19|20)\d{2})\b"
    r"|\b(\d{1,2})[./](\d{1,2})[./]((?:19|20)\d{2})\b",
    re.IGNORECASE,
)


def doc_year(text: str) -> int | None:
    """Best-effort publication year from a document's header.

    ITM texts carry their édition date in the first lines (e.g. "mai 2006").
    We scan the opening ~1000 chars for the first French month-year or a
    numeric dd/mm/yyyy and keep only the year. Returns None when no date is
    found (e.g. scanned docs with no text layer)."""
    m = _DATE_RE.search(text[:1000])
    if not m:
        return None
    return int(m.group(2)) if m.group(1) else int(m.group(5))


def generate_report(meta: list[dict], coords: np.ndarray, scanned: list[dict], texts: dict) -> str:
    # Classify SECO relevance first — needed in UMAP customdata
    for m in meta:
        m["seco"] = seco_relevance(m["filename"], m["title"])

    series_map: dict[str, list[int]] = {}
    for i, m in enumerate(meta):
        s = parse_series(m["filename"])
        series_map.setdefault(s, []).append(i)

    fig = go.Figure()
    for series, idxs in sorted(series_map.items()):
        x = coords[idxs, 0].tolist()
        y = coords[idxs, 1].tolist()
        words_list = [meta[i]["words"] for i in idxs]
        hover = [
            f"<b>{meta[i]['title']}</b><br>"
            f"{meta[i]['code']} · {meta[i]['words']:,} mots · {meta[i]['pages']} p."
            for i in idxs
        ]

        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="markers",
                name=series,
                marker=dict(
                    color=SERIES_COLORS.get(series, "#94a3b8"),
                    size=[max(7, min(22, w / 80)) for w in words_list],
                    opacity=0.82,
                    line=dict(width=1, color="rgba(255,255,255,0.4)"),
                ),
                text=hover,
                hovertemplate="%{text}<extra></extra>",
                customdata=[[meta[i]["url"], meta[i]["seco"]] for i in idxs],
            )
        )

    fig.update_layout(
        title=dict(
            text="ITM — carte sémantique des documents à texte extractible",
            font=dict(size=17, color="#1e293b"),
        ),
        paper_bgcolor="#f8fafc",
        plot_bgcolor="#ffffff",
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
        legend=dict(
            title="Série", bgcolor="rgba(255,255,255,0.9)", bordercolor="#e2e8f0", borderwidth=1
        ),
        height=620,
        margin=dict(l=20, r=20, t=60, b=20),
    )

    # Stacked histogram: documents per édition year, by series (all + SECO-only).
    year_series: dict[int, dict[str, int]] = {}
    year_series_seco: dict[int, dict[str, int]] = {}
    for d in meta + scanned:
        text = texts.get(d["filename"], {}).get("text", "")
        y = doc_year(text)
        if y is None:
            continue
        s = parse_series(d["filename"])
        year_series.setdefault(y, {})[s] = year_series.setdefault(y, {}).get(s, 0) + 1
        seco_lbl = d.get("seco") or seco_relevance(d["filename"], d.get("title", ""))
        if seco_lbl == "seco":
            year_series_seco.setdefault(y, {})[s] = year_series_seco.setdefault(y, {}).get(s, 0) + 1

    n_dated = sum(c for ys in year_series.values() for c in ys.values())
    hist_fig = go.Figure()
    yr_range: list[int] = []
    if year_series:
        yr_range = list(range(min(year_series), max(year_series) + 1))
        for series in ("ITM-CL", "ITM-ET", "ITM-SST"):
            counts = [year_series.get(y, {}).get(series, 0) for y in yr_range]
            if not any(counts):
                continue
            hist_fig.add_trace(
                go.Bar(
                    x=yr_range,
                    y=counts,
                    name=series,
                    marker_color=SERIES_COLORS[series],
                )
            )
        hist_fig.update_layout(
            barmode="stack",
            paper_bgcolor="#f8fafc",
            plot_bgcolor="#ffffff",
            xaxis=dict(showgrid=False, dtick=5, tickfont=dict(size=11)),
            yaxis=dict(title="Documents", showgrid=True, gridcolor="#f1f5f9"),
            legend=dict(bgcolor="rgba(255,255,255,0.9)", bordercolor="#e2e8f0", borderwidth=1),
            height=300,
            margin=dict(l=44, r=20, t=16, b=30),
            bargap=0.12,
        )

    # Pre-compute SECO histogram y-values as JS literal
    hist_seco_js = "{"
    for series in ("ITM-CL", "ITM-ET", "ITM-SST"):
        counts = [year_series_seco.get(y, {}).get(series, 0) for y in yr_range]
        hist_seco_js += f'"{series}":{json.dumps(counts)},'
    hist_seco_js += "}"

    mapped = len(meta)
    n_scanned = len(scanned)
    total = mapped + n_scanned
    total_words = sum(m["words"] for m in meta)
    avg_words = total_words // max(mapped, 1)
    pct_scanned = round(n_scanned / total * 100) if total else 0
    n_seco = sum(1 for m in meta if m["seco"] == "seco")
    n_maybe = sum(1 for m in meta if m["seco"] == "maybe")

    stats_items = [
        (str(total), "Documents ITM total"),
        (str(mapped), "Cartographiés (texte)"),
        (f"{n_scanned} ({pct_scanned}%)", "Backlog OCR (scannés)"),
        (f"{total_words:,}", "Mots cartographiés"),
        (f"{avg_words:,}", "Mots moy. / doc"),
    ]
    for s, idxs in sorted(series_map.items()):
        stats_items.append((str(len(idxs)), s + " (texte)"))
    stats_items.append((str(n_seco), "Périmètre SECO (direct)"))
    stats_items.append((str(n_maybe), "Périmètre SECO (projet)"))

    stats_html = (
        '<div class="stats-grid">'
        + "".join(
            f'<div class="stat"><div class="stat-val">{v}</div><div class="stat-lbl">{lbl}</div></div>'
            for v, lbl in stats_items
        )
        + "</div>"
    )

    def seco_badge(label: str) -> str:
        lbl, color, bg = SECO_LABEL_META[label]
        return (
            f"<span style='display:inline-block;padding:2px 7px;border-radius:4px;"
            f"font-size:9.5px;font-weight:700;letter-spacing:.3px;"
            f"background:{bg};color:{color}'>{lbl}</span>"
        )

    rows_sorted = sorted(meta, key=lambda m: m["words"], reverse=True)
    table_rows = ""
    for m in rows_sorted:
        year = doc_year(texts.get(m["filename"], {}).get("text", ""))
        table_rows += (
            f"<tr data-seco='{m['seco']}'>"
            f"<td>{parse_series(m['filename'])}</td>"
            f"<td><code>{m['code']}</code></td>"
            f"<td>{m['title']}</td>"
            f"<td style='text-align:right'>{year or '—'}</td>"
            f"<td style='text-align:right'>{m['words']:,}</td>"
            f"<td style='text-align:right'>{m['pages']}</td>"
            f"<td style='text-align:center'>{seco_badge(m['seco'])}</td>"
            f"<td><a href='{m['url']}' target='_blank'>↗</a></td>"
            f"</tr>"
        )

    scanned_rows = ""
    scanned_by_series: dict[str, int] = {}
    for d in sorted(scanned, key=lambda d: d["label"]):
        s = parse_series(d["filename"])
        scanned_by_series[s] = scanned_by_series.get(s, 0) + 1
        year = doc_year(texts.get(d["filename"], {}).get("text", ""))
        scanned_rows += (
            f"<tr><td>{s}</td><td><code>{d['label']}</code></td>"
            f"<td style='text-align:right'>{year or '—'}</td>"
            f"<td><a href='{d['url']}' target='_blank'>↗</a></td></tr>"
        )
    # e.g. "101 CL · 14 ET · 13 SST" — shows which series the OCR gap is in.
    scanned_breakdown = " · ".join(
        f"{scanned_by_series[s]} {s.replace('ITM-', '')}"
        for s in ("ITM-CL", "ITM-ET", "ITM-SST")
        if scanned_by_series.get(s)
    )

    fig_html = fig.to_html(
        include_plotlyjs="cdn",
        full_html=False,
        config={"displayModeBar": False},
        div_id="umap-chart",
    )
    hist_html = (
        hist_fig.to_html(
            include_plotlyjs=False,
            full_html=False,
            config={"displayModeBar": False},
            div_id="hist-chart",
        )
        if year_series
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>ITM Explorer — SECO PoC</title>
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
          background:#f8fafc;color:#1e293b;padding:0 0 80px}}
    .topbar{{background:#1a1a2e;color:#e2e8f0;padding:14px 40px;display:flex;
             align-items:center;gap:16px;border-bottom:3px solid #3b82f6;
             position:sticky;top:0;z-index:100}}
    .topbar h1{{font-size:17px;font-weight:700;color:#fff}}
    .topbar p{{font-size:11px;color:#94a3b8;margin-top:2px}}
    .topbar-right{{margin-left:auto}}
    #seco-toggle{{background:transparent;border:1.5px solid #3b82f6;color:#93c5fd;
      padding:7px 16px;border-radius:6px;font-size:12px;font-weight:600;
      cursor:pointer;transition:all .15s;white-space:nowrap;letter-spacing:.2px}}
    #seco-toggle:hover{{background:#1e3a5f;color:#fff;box-shadow:0 0 0 3px rgba(59,130,246,.35);transform:translateY(-1px)}}
    #seco-toggle.active{{background:#3b82f6;border-color:#3b82f6;color:#fff;box-shadow:0 0 0 3px rgba(59,130,246,.35)}}
    .body{{max-width:1200px;margin:32px auto;padding:0 24px}}
    h2{{font-size:14px;font-weight:600;color:#1e293b;margin:32px 0 12px;
        border-bottom:1px solid #e2e8f0;padding-bottom:6px;text-transform:uppercase;
        letter-spacing:.4px}}
    .stats-grid{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:8px}}
    .stat{{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:14px 20px;min-width:140px}}
    .stat-val{{font-size:22px;font-weight:700;color:#1e293b;font-variant-numeric:tabular-nums}}
    .stat-lbl{{font-size:10px;color:#64748b;margin-top:3px;text-transform:uppercase;letter-spacing:.5px}}
    .chart-wrap{{background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden}}
    .note{{font-size:11px;color:#64748b;line-height:1.6;margin:6px 0 20px 4px;max-width:900px}}
    .note strong{{color:#334155}}
    .series-legend{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-bottom:8px}}
    .series-card{{background:#fff;border:1px solid #e2e8f0;border-left:4px solid #94a3b8;
                  border-radius:8px;padding:14px 16px}}
    .series-head{{font-size:13px;font-weight:700;color:#1e293b;display:flex;align-items:center;gap:8px;margin-bottom:6px}}
    .series-card p{{font-size:12px;color:#475569;line-height:1.6}}
    .series-card em{{color:#1e293b;font-style:italic}}
    .dot{{width:10px;height:10px;border-radius:50%;display:inline-block;flex-shrink:0}}
    .series-meta{{display:block;margin-top:8px;font-size:10.5px;color:#94a3b8;
                  text-transform:uppercase;letter-spacing:.4px;font-weight:600}}
    table{{width:100%;border-collapse:collapse;font-size:12px;background:#fff;
           border:1px solid #e2e8f0;border-radius:8px;overflow:hidden}}
    thead th{{text-align:left;font-size:10px;font-weight:600;text-transform:uppercase;
              letter-spacing:.5px;color:#64748b;padding:8px 12px;
              border-bottom:2px solid #e2e8f0;background:#f8fafc}}
    tbody td{{padding:6px 12px;border-bottom:1px solid #f1f5f9;vertical-align:middle}}
    tbody tr:hover{{background:#f8fafc}}
    a{{color:#3b82f6;text-decoration:none}}
    table.sortable thead th[data-type]{{cursor:pointer;user-select:none;white-space:nowrap}}
    table.sortable thead th[data-type]:hover{{color:#3b82f6}}
    table.sortable thead th[data-type]::after{{content:' ⇅';color:#cbd5e1;font-size:9px}}
    table.sortable thead th.sorted-asc::after{{content:' ▲';color:#3b82f6}}
    table.sortable thead th.sorted-desc::after{{content:' ▼';color:#3b82f6}}
    .seco-note{{background:#f0fdf4;border:1px solid #bbf7d0;border-left:4px solid #16a34a;
      border-radius:8px;padding:14px 18px;font-size:12px;color:#166534;
      line-height:1.7;margin-bottom:20px;max-width:900px}}
    .seco-note strong{{color:#14532d}}
    .analysis-intro{{background:#fff;border:1px solid #e2e8f0;border-left:4px solid #6366f1;
      border-radius:8px;padding:16px 20px;margin-bottom:20px;font-size:12.5px;
      color:#475569;line-height:1.7;max-width:900px}}
    .analysis-intro strong{{color:#1e293b}}
    .track-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}}
    .track-card{{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 18px}}
    .track-card h3{{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
      margin-bottom:10px;display:flex;align-items:center;gap:8px}}
    .track-card ul{{list-style:none;padding:0}}
    .track-card li{{font-size:11.5px;color:#475569;padding:3px 0;
      border-bottom:1px solid #f1f5f9;line-height:1.5}}
    .track-card li:last-child{{border-bottom:none}}
    .track-card li strong{{color:#1e293b}}
    .timeline-strip{{display:flex;align-items:flex-start;gap:0;margin:0 0 20px;
      overflow-x:auto;padding-bottom:4px}}
    .tl-item{{display:flex;flex-direction:column;align-items:center;min-width:140px;
      position:relative}}
    .tl-item:not(:last-child)::after{{content:'';position:absolute;top:16px;left:50%;
      width:100%;height:2px;background:#e2e8f0;z-index:0}}
    .tl-dot{{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;
      justify-content:center;font-size:9px;font-weight:700;color:#fff;z-index:1;
      position:relative;flex-shrink:0}}
    .tl-label{{font-size:10px;font-weight:700;margin-top:8px;text-align:center;color:#1e293b}}
    .tl-date{{font-size:9.5px;color:#94a3b8;margin-top:2px;text-align:center}}
    .tl-note{{font-size:9px;color:#64748b;margin-top:4px;text-align:center;
      max-width:130px;line-height:1.4}}
    .diff-table{{width:100%;border-collapse:collapse;font-size:11.5px;background:#fff;
      border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-bottom:20px}}
    .diff-table thead th{{text-align:left;font-size:10px;font-weight:600;
      text-transform:uppercase;letter-spacing:.5px;color:#64748b;padding:8px 14px;
      border-bottom:2px solid #e2e8f0;background:#f8fafc}}
    .diff-table tbody td{{padding:7px 14px;border-bottom:1px solid #f1f5f9;
      vertical-align:top;line-height:1.5}}
    .diff-table tbody td:first-child{{font-weight:600;color:#374151;width:160px}}
    .diff-table tbody td:nth-child(2){{color:#2563eb}}
    .diff-table tbody td:nth-child(3){{color:#059669}}
    .diff-table tbody tr:hover{{background:#fafafa}}
    .tension-box{{background:#fef9ec;border:1px solid #fcd34d;border-radius:8px;
      padding:14px 18px;font-size:12px;color:#78350f;line-height:1.7;margin-bottom:20px;
      max-width:900px}}
    .tension-box strong{{color:#92400e}}
    .badge{{display:inline-block;padding:2px 7px;border-radius:4px;font-size:9.5px;
      font-weight:700;letter-spacing:.3px;text-transform:uppercase}}
    .badge-a{{background:#eff6ff;color:#1d4ed8}}
    .badge-b{{background:#f0fdf4;color:#15803d}}
    details{{margin:32px 0 0}}
    details>summary{{font-size:14px;font-weight:600;color:#1e293b;margin:0 0 12px;
        border-bottom:1px solid #e2e8f0;padding-bottom:6px;text-transform:uppercase;
        letter-spacing:.4px;cursor:pointer;list-style:none;display:flex;
        align-items:center;gap:8px}}
    details>summary::-webkit-details-marker{{display:none}}
    details>summary::before{{content:'▸';color:#94a3b8;font-size:11px;
        transition:transform .15s}}
    details[open]>summary::before{{transform:rotate(90deg)}}
    details>summary:hover{{color:#3b82f6}}
    summary .count{{font-weight:500;color:#94a3b8;text-transform:none;
        letter-spacing:0;font-size:12px}}
  </style>
</head>
<body>
  <div class="topbar">
    <div>
      <h1>ITM Corpus Explorer</h1>
      <p>SECO PoC · Inspection du Travail et des Mines · Luxembourg · App 3</p>
    </div>
    <div class="topbar-right">
      <button id="seco-toggle">◉ Vue SECO</button>
    </div>
  </div>
  <div class="body">
    <h2>Vue d'ensemble du corpus</h2>
    {stats_html}
    <h2>Carte sémantique — UMAP</h2>
    <div class="chart-wrap">{fig_html}</div>
    <p class="note">
      Chaque point = un document à texte extractible &nbsp;·&nbsp; couleur = série
      &nbsp;·&nbsp; taille ∝ nombre de mots &nbsp;·&nbsp; survol = objet du document
      &nbsp;·&nbsp; titres extraits via {TITLE_MODEL} · embeddings {EMBED_MODEL} · UMAP cosine.
      Les {n_scanned} documents scannés (sans texte extractible) sont exclus de la carte
      et listés comme backlog OCR ci-dessous.
    </p>
    <p class="note">
      <strong>Note méthodologique — troncature.</strong> Chaque document est embarqué
      sur ses <strong>~8 000 premiers caractères</strong> (≈ 2 000 tokens). Pour les
      textes longs (certains dépassent 29 000 mots), seul le début — objet, domaine
      d'application, premiers articles — alimente l'embedding. C'est suffisant pour
      le regroupement thématique visible ici, mais la position d'un document très long
      reflète son ouverture, pas l'intégralité de son contenu. Une version production
      découperait les longs documents en sections (chunking) et moyennerait leurs vecteurs.
    </p>

    <h2>Les trois séries : CL · ET · SST</h2>
    <div class="series-legend">
      <div class="series-card" style="border-left-color:#3b82f6">
        <div class="series-head"><span class="dot" style="background:#3b82f6"></span> ITM-CL — Conditions-types</div>
        <p>Prescriptions de sécurité <em>types</em> attachées à l'exploitation d'installations
        ou d'équipements précis (émetteurs, citernes, ascenseurs, éclairage…). Cœur historique
        du référentiel <em>commodo / incommodo</em> des établissements classés.
        <span class="series-meta">≈ 1990–2016 · médiane 1998</span></p>
      </div>
      <div class="series-card" style="border-left-color:#f59e0b">
        <div class="series-head"><span class="dot" style="background:#f59e0b"></span> ITM-ET — Établissements-types</div>
        <p>Prescriptions par <em>type de bâtiment / établissement recevant du public</em>
        (grandes surfaces, centres pour jeunes, hébergements pour personnes âgées…).
        La plus ancienne et la plus petite série — largement gelée aujourd'hui.
        <span class="series-meta">≈ 1991–2005 · médiane 1997</span></p>
      </div>
      <div class="series-card" style="border-left-color:#10b981">
        <div class="series-head"><span class="dot" style="background:#10b981"></span> ITM-SST — Sécurité &amp; Santé au Travail</div>
        <p>Série <em>moderne et unifiée</em> : prescriptions d'exécution et textes coordonnés
        des règlements grand-ducaux (EPI, amiante, risques majeurs…). Elle reprend
        progressivement le rôle des séries CL et ET sous une numérotation unique.
        <span class="series-meta">≈ 2007–2025 · médiane 2012</span></p>
      </div>
    </div>
    <p class="note">
      En clair : <strong>CL</strong> et <strong>ET</strong> sont les séries <em>héritées</em>
      (par équipement, et par type d'établissement), <strong>SST</strong> est le référentiel
      <em>actuel</em> qui les absorbe. Cette transition est exactement ce qui rend le suivi
      de versions (app 2) critique : une prescription CL des années 1990 peut avoir été
      remplacée par un texte SST récent sans que les deux soient jamais croisés.
    </p>

    <h2>Chronologie — documents par année d'édition</h2>
    <div class="chart-wrap">{hist_html}</div>
    <p class="note">
      Année d'édition extraite de l'en-tête de chaque PDF, empilée par série.
      On lit directement la transition : les barres <strong>CL</strong> (bleu) et
      <strong>ET</strong> (orange) dominent les années 1990–2000, puis cèdent la place
      aux barres <strong>SST</strong> (vert) à partir de ~2010. Couvre les
      {n_dated} documents dont la date est lisible dans le texte (les {n_scanned}
      scannés et quelques PDF sans date d'en-tête sont exclus).
    </p>

    <h2>Périmètre SECO — documents pertinents pour le contrôle technique</h2>
    <div class="seco-note">
      <strong>Comment lire ce signal.</strong> SECO est un organisme de contrôle agréé
      qui intervient <em>au nom de l'ITM</em> (ITM-SST 10001.4, Art. 1er).
      Son mandat couvre les Annexes 4 (sécurité des bâtiments + incendie), 6 (froid),
      8 (chantiers), 9 (électrique), 10B (levage vertical) et 16 (pression).
      Sur les {mapped} documents cartographiés : <strong>{n_seco} directement dans le périmètre</strong>
      · {n_maybe} selon le type de projet · {mapped - n_seco - n_maybe} hors périmètre.
      Utilisez le bouton <strong>◉ Vue SECO</strong> en haut à droite pour filtrer
      les trois visualisations simultanément.
    </div>

    <details>
    <summary>Analyse de cluster — Monte-charges (2006–2007) <span class="count">— 5 documents · 2 filières · 2006–2007</span></summary>
    <div class="analysis-intro">
      Cinq documents partagent le même sujet (<em>prescriptions de sécurité pour monte-charges</em>)
      et forment un cluster dense dans l'espace sémantique. Ils ne sont pas de simples révisions
      successives : ils représentent <strong>deux filières réglementaires parallèles</strong>
      coexistant simultanément, chacune gérant un type d'équipement différent.
    </div>
    <div class="track-grid">
      <div class="track-card" style="border-top:3px solid #3b82f6">
        <h3><span class="badge badge-a">Filière A</span> Filière générale → ITM-CL 91.x → ITM-SST 1213.1</h3>
        <ul>
          <li><strong>Équipements :</strong> Monte-charges traditionnels, non nécessairement CE</li>
          <li><strong>Guides :</strong> Verticaux ou inclinés &lt;15° de la verticale</li>
          <li><strong>Certification :</strong> L'ITM spécifie tous les détails (câbles ≥8 mm, coeff. ≥12, parachutes, taquets…)</li>
          <li><strong>Tension :</strong> 230 V / 16 A · <strong>Articles :</strong> 10</li>
          <li><strong>Exclut (ajouté en 91.2) :</strong> Monte-poubelles, monte-plats, monte-documents</li>
        </ul>
      </div>
      <div class="track-card" style="border-top:3px solid #10b981">
        <h3><span class="badge badge-b">Filière B</span> Filière directive machines → ITM-CL 291.x</h3>
        <ul>
          <li><strong>Équipements :</strong> Monte-charges conçus d'après la directive 98/37/CE</li>
          <li><strong>Guides :</strong> Rigides (inclinaison libre — périmètre plus large)</li>
          <li><strong>Certification :</strong> Le marquage CE couvre les exigences techniques ; l'ITM encadre uniquement l'installation</li>
          <li><strong>Tension :</strong> 240 V / 16 A · <strong>Articles :</strong> 12 (+ Déclaration CE, Modifications, Autorisation)</li>
          <li><strong>Exclut (291.1 seulement) :</strong> Monte-poubelles, monte-plats, monte-documents — <em>supprimé en 291.2</em></li>
        </ul>
      </div>
    </div>
    <div class="timeline-strip">
      <div class="tl-item"><div class="tl-dot" style="background:#10b981">B1</div>
        <div class="tl-label">ITM-CL 291.1</div><div class="tl-date">Mars 2006</div>
        <div class="tl-note">Filière CE v1 — scope « industriel »</div></div>
      <div class="tl-item"><div class="tl-dot" style="background:#10b981">B2</div>
        <div class="tl-label">ITM-CL 291.2</div><div class="tl-date">Nov. 2006</div>
        <div class="tl-note">Filière CE v2 — supprime « industriel », élargit le périmètre</div></div>
      <div class="tl-item"><div class="tl-dot" style="background:#3b82f6">A3</div>
        <div class="tl-label">ITM-CL 91.3</div><div class="tl-date">Nov. 2006</div>
        <div class="tl-note">Filière générale — version active</div></div>
      <div class="tl-item"><div class="tl-dot" style="background:#6366f1">A†</div>
        <div class="tl-label">ITM-CL 91.2</div><div class="tl-date">Juil. 2007</div>
        <div class="tl-note">Document de transition — annonce renommage vers 1213</div></div>
      <div class="tl-item"><div class="tl-dot" style="background:#f59e0b">A4</div>
        <div class="tl-label">ITM-SST 1213.1</div><div class="tl-date">Déc. 2007</div>
        <div class="tl-note">Version finale — nouveau préfixe SST, 8 p. (−1 p.)</div></div>
    </div>
    <p class="note" style="margin-top:8px;margin-bottom:24px">
      La présence de 91.2 <em>après</em> 91.3 s'explique : le document 91.2 est republié
      en juillet 2007 avec un en-tête de transition annonçant son renommage en 1213.
      <br><strong>Point critique SECO :</strong> déterminer quelle filière s'applique à une
      installation donnée requiert de savoir si un marquage CE a été obtenu à la mise en service —
      information qui réside dans le registre de sécurité, pas dans les ITM eux-mêmes.
    </p>
    </details>

    <details>
      <summary>Inventaire cartographié <span class="count">— {mapped} documents</span></summary>
      <table id="inv-table" class="sortable">
        <thead>
          <tr>
            <th data-type="text">Série</th><th data-type="text">Code</th>
            <th data-type="text">Objet</th><th data-type="num">Année</th>
            <th data-type="num">Mots</th><th data-type="num">Pages</th>
            <th>SECO</th><th>PDF</th>
          </tr>
        </thead>
        <tbody>{table_rows}</tbody>
      </table>
    </details>
    <details>
      <summary>Backlog OCR — documents scannés <span class="count">— {n_scanned} ({scanned_breakdown})</span></summary>
      <p class="note">
        Ces documents n'ont pas de couche texte extractible. Ils nécessitent une étape
        OCR (p. ex. Claude vision) avant de pouvoir être cartographiés ou analysés.
      </p>
      <table class="sortable">
        <thead><tr><th data-type="text">Série</th><th data-type="text">Code</th>
        <th data-type="num">Année</th><th>PDF</th></tr></thead>
        <tbody>{scanned_rows}</tbody>
      </table>
    </details>
  </div>
  {SORT_SCRIPT}
  <script>
  (function() {{
    var active = false;
    var btn = document.getElementById('seco-toggle');
    var SECO_COLOR = {{"ITM-CL":"#3b82f6","ITM-ET":"#f59e0b","ITM-SST":"#10b981"}};
    var GRAY = '#cbd5e1';
    var histSecoY = {hist_seco_js};

    // Capture original histogram y-values once Plotly is ready
    var histOrigY = null;
    function getHistOrig() {{
      var el = document.getElementById('hist-chart');
      if (!el || !el.data) return false;
      histOrigY = {{}};
      el.data.forEach(function(t) {{ histOrigY[t.name] = t.y.slice(); }});
      return true;
    }}

    btn.addEventListener('click', function() {{
      active = !active;
      btn.classList.toggle('active', active);
      btn.textContent = active ? '✕ Tout afficher' : '◉ Vue SECO';

      // ── Table ──────────────────────────────────────────────────────────────
      document.querySelectorAll('#inv-table tbody tr').forEach(function(row) {{
        var s = row.dataset.seco;
        row.style.display = (!active || s === 'seco') ? '' : 'none';
      }});

      // ── UMAP ───────────────────────────────────────────────────────────────
      var umap = document.getElementById('umap-chart');
      if (umap && umap.data) {{
        var newColors = [], newOpacities = [];
        umap.data.forEach(function(trace, ti) {{
          var baseColor = SECO_COLOR[trace.name] || '#94a3b8';
          if (active) {{
            var colors = trace.customdata.map(function(d) {{
              return d[1] === 'seco' ? baseColor : GRAY;
            }});
            var opacities = trace.customdata.map(function(d) {{
              return d[1] === 'seco' ? 0.88 : 0.18;
            }});
            newColors.push(colors);
            newOpacities.push(opacities);
          }} else {{
            newColors.push(baseColor);
            newOpacities.push(0.82);
          }}
        }});
        Plotly.restyle('umap-chart', {{
          'marker.color': newColors,
          'marker.opacity': newOpacities
        }});
      }}

      // ── Histogram ──────────────────────────────────────────────────────────
      if (!histOrigY && !getHistOrig()) return;
      var hist = document.getElementById('hist-chart');
      if (hist && hist.data) {{
        var ySource = active ? histSecoY : histOrigY;
        var newData = hist.data.map(function(t) {{
          return Object.assign({{}}, t, {{y: ySource[t.name] || t.y}});
        }});
        Plotly.react('hist-chart', newData, hist.layout);
      }}
    }});
  }})();
  </script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    links = scrape_links()
    download_pdfs(links)
    texts = extract_texts(links)
    extractable, scanned = split_extractable(links, texts)
    titles = extract_titles(extractable, texts)
    embeddings, meta = embed(extractable, texts, titles)
    coords = run_umap(embeddings)
    html = generate_report(meta, coords, scanned, texts)
    out = BASE / "report.html"
    out.write_text(html, encoding="utf-8")
    print(f"\n✓ Report → {out}")
    print(f"  Open: xdg-open {out}")


if __name__ == "__main__":
    main()
