"""Extract text from PDFs and cache as JSON."""
import hashlib
import json
from pathlib import Path
import pdfplumber

DOCS_DIR = Path(__file__).parent.parent / "documents"
CACHE_PATH = Path(__file__).parent / "extracted.json"

DOCS_META = {
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


def extract_all() -> dict:
    result = {}
    for filename, meta in DOCS_META.items():
        path = DOCS_DIR / filename
        pages = []
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and text.strip():
                    pages.append({"page": i + 1, "text": text})
        full_text = "\n\n".join(p["text"] for p in pages)
        result[meta["id"]] = {
            **meta,
            "pages": pages,
            "full_text": full_text,
            "content_hash": hashlib.sha256(full_text.encode()).hexdigest()[:12],
        }
        print(f"  {meta['id']}: {len(pages)} pages extracted")
    return result


def get_extracted() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    print("Extracting PDFs...")
    data = extract_all()
    CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print("Cached to extracted.json")
    return data


if __name__ == "__main__":
    get_extracted()
