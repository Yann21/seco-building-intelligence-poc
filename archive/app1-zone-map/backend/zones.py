"""Spatial index over PAG zones for point-in-polygon queries."""
import json
from pathlib import Path
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

DATA_DIR = Path(__file__).parent.parent / "data" / "processed"

_zonage_tree: STRtree | None = None
_zonage_geoms: list = []
_zonage_props: list[dict] = []

_nq_pap_tree: STRtree | None = None
_nq_pap_geoms: list = []
_nq_pap_props: list[dict] = []


def _load(filename: str):
    path = DATA_DIR / filename
    with open(path) as f:
        data = json.load(f)
    geoms = [shape(feat["geometry"]) for feat in data["features"]]
    props = [feat["properties"] for feat in data["features"]]
    return STRtree(geoms), geoms, props


def init():
    global _zonage_tree, _zonage_geoms, _zonage_props
    global _nq_pap_tree, _nq_pap_geoms, _nq_pap_props
    print("Loading spatial indexes...")
    _zonage_tree, _zonage_geoms, _zonage_props = _load("pag_zonage.geojson")
    _nq_pap_tree, _nq_pap_geoms, _nq_pap_props = _load("pag_nq_pap.geojson")
    print(f"  zonage: {len(_zonage_geoms)} zones")
    print(f"  nq_pap: {len(_nq_pap_geoms)} zones")


def query_point(lat: float, lng: float) -> dict | None:
    pt = Point(lng, lat)
    candidates = _zonage_tree.query(pt, predicate="within")
    if len(candidates) == 0:
        return None
    idx = int(candidates[0])
    return _zonage_props[idx]


def query_nq_pap_nearby(lat: float, lng: float, radius_deg: float = 0.005) -> list[dict]:
    pt = Point(lng, lat)
    candidates = _nq_pap_tree.query(pt.buffer(radius_deg), predicate="intersects")
    return [_nq_pap_props[int(i)] for i in candidates[:5]]
