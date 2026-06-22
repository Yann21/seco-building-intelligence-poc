"""
Extract text from PDFs organized into topic clusters (subfolders).

documents/
  lighting/          ← cluster name
    ITM-CL-55.2.pdf
    ITM-ET-32.10.pdf
    ITM-CL-144.1.pdf
  fire-safety/       ← future cluster
    ...

Each subfolder is one cluster. Pairwise conflict analysis only runs within
a cluster — documents in different topic areas are never compared.
PDFs placed directly in documents/ go into a "default" cluster.

To add a new document: drop the PDF in the appropriate subfolder and add
a metadata entry to DOCS_META below. If no entry exists the document is
still processed using the filename as a fallback identifier.
"""
import hashlib
import json
from pathlib import Path

import pdfplumber

DOCS_DIR = Path(__file__).parent.parent / "documents"
CACHE_PATH = Path(__file__).parent / "extracted.json"

# Known document metadata keyed by filename.
# Documents not listed here are still extracted; filename stem is used as ID.
DOCS_META: dict[str, dict] = {
    "ITM-CL-55.2.pdf": {
        "id": "ITM-CL-55.2",
        "title": "ITM-CL 55.2 – Éclairage des lieux de travail",
        "authority": "Inspection du Travail et des Mines (ITM)",
        "date": "1997-10-16",
        "scope": "Prescriptions de sécurité et de santé types pour l'éclairage de tous les lieux de travail au Luxembourg",
        "url": "https://itm.public.lu/dam-assets/fr/securite-sante/conditions-types/itm-cl-1-100/ITM-CL-55-2.pdf",
    },
    "ITM-ET-32.10.pdf": {
        "id": "ITM-ET-32.10",
        "title": "ITM-ET 32.10 – Protection des Travailleurs (Art. 15 Éclairage)",
        "authority": "Inspection du Travail et des Mines (ITM)",
        "date": "1997-10-16",
        "scope": "Prescriptions générales de sécurité, de santé et d'hygiène pour les entreprises industrielles, commerciales et tertiaires",
        "url": "https://itm.public.lu/dam-assets/fr/securite-sante/conditions-types/itm-cl-1-100/ITM-ET-32-10.pdf",
    },
    "ITM-CL-144.1.pdf": {
        "id": "ITM-CL-144.1",
        "title": "ITM-CL 144.1 – Installations électriques de chantier (Art. 7 Éclairage)",
        "authority": "Inspection du Travail et des Mines (ITM)",
        "date": "2004-07-15",
        "scope": "Prescriptions de sécurité types pour les installations électriques provisoires sur chantiers de construction",
        "url": "https://itm.public.lu/dam-assets/fr/securite-sante/conditions-types/itm-cl-101-200/ITM-CL-144-1.pdf",
    },
}


def discover_pdfs() -> list[tuple[Path, str]]:
    """
    Scan DOCS_DIR recursively for PDFs.
    Returns (pdf_path, cluster_name) pairs sorted by cluster then filename.
    Cluster = immediate subfolder name; 'default' for PDFs at top level.
    """
    results = []
    for pdf_path in sorted(DOCS_DIR.rglob("*.pdf")):
        rel = pdf_path.relative_to(DOCS_DIR)
        cluster = rel.parts[0] if len(rel.parts) > 1 else "default"
        results.append((pdf_path, cluster))
    return results


def extract_all() -> dict:
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
    if CACHE_PATH.exists():
        cached = json.loads(CACHE_PATH.read_text())
        # Bust cache if cluster field is missing (pre-cluster version)
        first = next(iter(cached.values()), {})
        if "cluster" not in first:
            print("Extracting PDFs (cluster field added)...")
            return _extract_and_cache()
        return cached
    print("Extracting PDFs...")
    return _extract_and_cache()


def _extract_and_cache() -> dict:
    data = extract_all()
    CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print("Cached to extracted.json")
    return data


if __name__ == "__main__":
    get_extracted()
