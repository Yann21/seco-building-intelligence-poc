"""PAG Insight – FastAPI backend."""
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import zones
from zone_rules import get_rule

DATA_DIR = Path(__file__).parent.parent / "data" / "processed"


@asynccontextmanager
async def lifespan(app: FastAPI):
    zones.init()
    yield


app = FastAPI(title="PAG Insight", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_geojson_cache: dict[str, bytes] = {}


def _load_geojson(name: str) -> bytes:
    if name not in _geojson_cache:
        path = DATA_DIR / f"{name}.geojson"
        _geojson_cache[name] = path.read_bytes()
    return _geojson_cache[name]


@app.get("/api/zone")
def query_zone(lat: float = Query(...), lng: float = Query(...)):
    zone_props = zones.query_point(lat, lng)
    if zone_props is None:
        raise HTTPException(status_code=404, detail="No zone found at this location")

    categorie = zone_props.get("categorie", "")
    rule = get_rule(categorie)
    nq_pap_nearby = zones.query_nq_pap_nearby(lat, lng)

    return {
        "zone": {
            "id": zone_props.get("id"),
            "categorie": categorie,
            "label": zone_props.get("label"),
            "color": zone_props.get("color"),
            "nom_fichier": zone_props.get("nom_fichier"),
        },
        "rules": rule,
        "nq_pap_nearby": nq_pap_nearby,
        "coordinates": {"lat": lat, "lng": lng},
    }


@app.get("/api/geojson/zonage")
def geojson_zonage():
    data = _load_geojson("pag_zonage")
    return Response(content=data, media_type="application/json")


@app.get("/api/geojson/nq_pap")
def geojson_nq_pap():
    data = _load_geojson("pag_nq_pap")
    return Response(content=data, media_type="application/json")


@app.get("/api/health")
def health():
    return {"status": "ok"}
