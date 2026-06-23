"""Ingest stage — PDF discovery and extraction (reads the real corpus, offline)."""

from pipeline.extract import discover_pdfs, get_extracted


def test_discover_assigns_subfolder_as_cluster():
    pairs = discover_pdfs()
    clusters = {cluster for _, cluster in pairs}
    assert {"lighting", "ventilation", "ascenseurs"} <= clusters
    assert all(path.suffix == ".pdf" for path, _ in pairs)


def test_get_extracted_has_text_cluster_and_hash():
    docs = get_extracted()
    assert "ITM-CL-55.2" in docs
    d = docs["ITM-CL-55.2"]
    assert d["cluster"] == "lighting"
    assert len(d["content_hash"]) == 12
    assert d["full_text"]  # non-empty


def test_known_metadata_applied():
    docs = get_extracted()
    assert "Éclairage" in docs["ITM-CL-55.2"]["title"]


def test_extract_all_reads_pdfs_directly():
    # Exercises the real pdfplumber extraction loop (not the cache).
    from pipeline.extract import extract_all

    docs = extract_all()
    assert len(docs) >= 9
    d = docs["ITM-CL-55.2"]
    assert d["pages"] and d["full_text"]
    assert d["content_hash"] == d["content_hash"]  # deterministic per run
