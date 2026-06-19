"""Reproject PAG GeoJSON from EPSG:3035 to WGS84 and slim properties."""
import json
from pathlib import Path
from pyproj import Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform as shapely_transform
import functools

IN_DIR = Path(__file__).parent / "raw"
OUT_DIR = Path(__file__).parent / "processed"

ZONE_LABELS = {
    "HAB_1": "Zone d'habitation 1",
    "HAB_2": "Zone d'habitation 2",
    "MIX_u": "Zone mixte urbaine",
    "MIX_v": "Zone mixte villageoise",
    "MIX_r": "Zone mixte rurale",
    "MIX_c": "Zone mixte centrale",
    "FOR": "Zone forestière",
    "AGR": "Zone agricole",
    "BEP": "Zone de bâtiments et équipements publics",
    "VERD": "Zone de verdure",
    "JAR": "Zone de jardins",
    "PARC": "Zone de parcs",
    "REC": "Zone de récréation",
    "ECO_c1": "Zone d'activités économiques (commerce/artisanat)",
    "ECO_c2": "Zone d'activités économiques (commerce)",
    "ECO_c3": "Zone d'activités économiques (grands commerces)",
    "ECO_n": "Zone d'activités économiques (industrie)",
    "ECO_r": "Zone d'activités économiques (recherche)",
    "ECO_r1": "Zone d'activités économiques (recherche 1)",
    "ECO_r2": "Zone d'activités économiques (recherche 2)",
    "COM": "Zone commerciale",
    "SPEC": "Zone spéciale",
    "GARE": "Zone de gare",
    "VIT": "Zone viticole",
    "HOR": "Zone horticole",
    "AERO": "Zone aéroportuaire",
    "PORT_m": "Zone portuaire",
    "SP_n": "Zone de sports et loisirs",
    "MIL": "Zone militaire",
    "RUR": "Zone rurale",
    "AGR2000": "Zone agricole protégée",
}

CATEGORY_COLORS = {
    "HAB_1": "#fde68a",
    "HAB_2": "#fbbf24",
    "MIX_u": "#f97316",
    "MIX_v": "#fb923c",
    "MIX_r": "#fdba74",
    "MIX_c": "#ef4444",
    "FOR": "#16a34a",
    "AGR": "#86efac",
    "AGR2000": "#4ade80",
    "BEP": "#60a5fa",
    "VERD": "#a7f3d0",
    "JAR": "#6ee7b7",
    "PARC": "#34d399",
    "REC": "#2dd4bf",
    "ECO_c1": "#c084fc",
    "ECO_c2": "#a855f7",
    "ECO_c3": "#7c3aed",
    "ECO_n": "#6d28d9",
    "ECO_r": "#8b5cf6",
    "ECO_r1": "#7c3aed",
    "ECO_r2": "#6d28d9",
    "COM": "#e879f9",
    "SPEC": "#94a3b8",
    "GARE": "#475569",
    "VIT": "#a16207",
    "HOR": "#65a30d",
    "AERO": "#334155",
    "PORT_m": "#0369a1",
    "SP_n": "#0891b2",
    "MIL": "#1e293b",
    "RUR": "#d9f99d",
}


def process_layer(name: str, simplify_tolerance: float = 0.00005):
    in_path = IN_DIR / f"{name}.geojson"
    out_path = OUT_DIR / f"{name}.geojson"

    print(f"Processing {name}...")
    with open(in_path) as f:
        data = json.load(f)

    transformer = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)
    project = functools.partial(transformer.transform)

    features = []
    for feat in data["features"]:
        props = feat["properties"]
        categorie = props.get("categorie") or ""

        geom_3035 = shape(feat["geometry"])
        geom_wgs84 = shapely_transform(lambda x, y: transformer.transform(x, y), geom_3035)
        geom_simple = geom_wgs84.simplify(simplify_tolerance, preserve_topology=True)

        if geom_simple.is_empty:
            continue

        raw_geom = mapping(geom_simple)
        # Round coordinates to 6 decimal places
        def round_coords(coords):
            if isinstance(coords[0], (int, float)):
                return [round(coords[0], 6), round(coords[1], 6)]
            return [round_coords(c) for c in coords]
        raw_geom = dict(raw_geom)
        raw_geom["coordinates"] = round_coords(raw_geom["coordinates"])

        features.append(
            {
                "type": "Feature",
                "geometry": raw_geom,
                "properties": {
                    "id": props.get("inspireid_identifier_localid", ""),
                    "categorie": categorie,
                    "label": ZONE_LABELS.get(categorie, categorie),
                    "color": CATEGORY_COLORS.get(categorie, "#94a3b8"),
                    "nom_fichier": props.get("nom_fichier", ""),
                    "denomination": props.get("denomination"),
                    "lib": props.get("lib"),
                    "cos_max": props.get("cos_max"),
                    "cus_max": props.get("cus_max"),
                    "dl_max": props.get("dl_max"),
                    "dl_min": props.get("dl_min"),
                },
            }
        )

    out = {"type": "FeatureCollection", "features": features}
    out_path.write_text(json.dumps(out, separators=(",", ":")))
    size_kb = out_path.stat().st_size // 1024
    print(f"  → {len(features)} features, {size_kb} KB → {out_path}")


if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)
    process_layer("pag_zonage", simplify_tolerance=0.0002)
    process_layer("pag_nq_pap", simplify_tolerance=0.00005)
    print("Done.")
