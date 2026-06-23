"""Stage 1 — ingest: PDFs organised into topic clusters → structured text.

    documents/
      lighting/          ← cluster name (immediate subfolder)
        ITM-CL-55.2.pdf
        ITM-ET-32.10.pdf
        ITM-CL-144.1.pdf
      ventilation/
        ...

Each subfolder is one cluster; pairwise analysis only runs within a cluster.
PDFs dropped directly in ``documents/`` fall into a ``default`` cluster.

Output is cached to ``data/extracted.json`` and keyed by document id. The cache
also stores a ``content_hash`` per document, which is what the analysis stage
uses to decide whether a pair needs re-running.
"""
import hashlib
import json
from pathlib import Path

import pdfplumber

from .config import DOCS_DIR, EXTRACTED_CACHE
from .docs_meta import DOCS_META


def discover_pdfs() -> list[tuple[Path, str]]:
    """Scan ``DOCS_DIR`` recursively, returning (pdf_path, cluster) pairs.

    Cluster = immediate subfolder name; ``default`` for PDFs at the top level.
    Sorted by cluster then filename for stable, reproducible ordering.
    """
    results = []
    for pdf_path in sorted(DOCS_DIR.rglob("*.pdf")):
        rel = pdf_path.relative_to(DOCS_DIR)
        cluster = rel.parts[0] if len(rel.parts) > 1 else "default"
        results.append((pdf_path, cluster))
    return results


def extract_all() -> dict:
    """Extract every discovered PDF into a {doc_id: document} mapping."""
    result = {}
    for pdf_path, cluster in discover_pdfs():
        filename = pdf_path.name
        meta = DOCS_META.get(filename, {
            "id": pdf_path.stem,
            "title": pdf_path.stem.replace("-", " "),
            "authority": "Unknown",
            "date": "Unknown",
            "scope": "",
            "url": "",
        })
        pages = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and text.strip():
                    pages.append({"page": i + 1, "text": text})
        full_text = "\n\n".join(p["text"] for p in pages)
        doc_id = meta["id"]
        result[doc_id] = {
            **meta,
            "cluster": cluster,
            "pages": pages,
            "full_text": full_text,
            "content_hash": hashlib.sha256(full_text.encode()).hexdigest()[:12],
        }
        print(f"  {doc_id} [{cluster}]: {len(pages)} pages")
    return result


def get_extracted() -> dict:
    """Return cached extraction, rebuilding if the cache is stale or missing."""
    if EXTRACTED_CACHE.exists():
        cached = json.loads(EXTRACTED_CACHE.read_text())
        # Bust cache if it predates the cluster field (pre-cluster format).
        first = next(iter(cached.values()), {})
        if "cluster" not in first:
            print("Extracting PDFs (cluster field added)...")
            return _extract_and_cache()
        return cached
    print("Extracting PDFs...")
    return _extract_and_cache()


def _extract_and_cache() -> dict:
    data = extract_all()
    EXTRACTED_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"Cached to {EXTRACTED_CACHE.name}")
    return data
