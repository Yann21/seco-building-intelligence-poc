"""Pairing, hashing, JSON extraction, and the offline merge path."""
from pipeline.analyze import (
    _doc_hash,
    _extract_json_block,
    cluster_pairs,
    get_analysis,
)
from pipeline.extract import get_extracted


def test_extract_json_block_unwraps_fences_and_prose():
    assert _extract_json_block('```json\n{"a": 1}\n```').strip() == '{"a": 1}'
    assert _extract_json_block('```\n{"a": 1}\n```').strip() == '{"a": 1}'
    assert _extract_json_block('voici: {"a": 1} fin').strip() == '{"a": 1}'


def test_doc_hash_is_stable_and_truncated():
    d = {"full_text": "bonjour le monde"}
    assert _doc_hash(d) == _doc_hash(d)
    assert len(_doc_hash(d)) == 12


def test_cluster_pairs_never_cross_cluster():
    docs = get_extracted()
    for a, b in cluster_pairs(docs):
        assert a["cluster"] == b["cluster"]


def test_lighting_cluster_has_three_pairs():
    docs = get_extracted()
    lighting = [p for p in cluster_pairs(docs) if p[0]["cluster"] == "lighting"]
    assert len(lighting) == 3  # 3 documents → C(3,2) = 3 pairs


def test_get_analysis_offline_fast_path():
    res = get_analysis()  # warm caches → no API call
    assert res["conflicts"]
    assert res["_meta"]["prompt_version"]
    # merged conflict ids encode their originating document pair
    assert all("__" in c["id"] for c in res["conflicts"])
