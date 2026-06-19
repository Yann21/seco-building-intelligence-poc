"""Download PAG zone data from geoportail.lu WFS."""
import json
import time
import urllib.request
from pathlib import Path

WFS_BASE = "https://wms.inspire.geoportail.lu/geoserver/wfs"
OUT_DIR = Path(__file__).parent / "raw"

LAYERS = {
    "pag_zonage": {
        "filter": "specificlanduse0_xlink_title='PAG_PAG_ZONAGE'",
        "total": 21938,
    },
    "pag_nq_pap": {
        "filter": "specificlanduse0_xlink_title='PAG_PAG_NQ_PAP'",
        "total": 1404,
    },
}

PAGE_SIZE = 5000


def fetch_page(layer_filter: str, start: int, count: int) -> dict:
    params = (
        f"SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
        f"&TYPENAMES=lu:LU.SpatialPlan.PAG"
        f"&OUTPUTFORMAT=application/json"
        f"&CQL_FILTER={urllib.parse.quote(layer_filter)}"
        f"&COUNT={count}&STARTINDEX={start}"
    )
    url = f"{WFS_BASE}?{params}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


import urllib.parse


def download_layer(name: str, layer_filter: str, total: int):
    out_path = OUT_DIR / f"{name}.geojson"
    if out_path.exists():
        print(f"{name}: already exists, skipping")
        return

    all_features = []
    start = 0
    while start < total:
        count = min(PAGE_SIZE, total - start)
        print(f"{name}: fetching {start}–{start+count} of {total}...")
        data = fetch_page(layer_filter, start, count)
        all_features.extend(data["features"])
        start += count
        if start < total:
            time.sleep(0.5)

    geojson = {
        "type": "FeatureCollection",
        "features": all_features,
    }
    out_path.write_text(json.dumps(geojson))
    print(f"{name}: saved {len(all_features)} features → {out_path}")


if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)
    for name, cfg in LAYERS.items():
        download_layer(name, cfg["filter"], cfg["total"])
