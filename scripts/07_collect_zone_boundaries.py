"""Collect real administrative boundaries for Invest Search zones from OSM."""

from __future__ import annotations

import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "exports" / "casablanca_zone_boundaries.geojson"
NOMINATIM_LOOKUP = "https://nominatim.openstreetmap.org/lookup"

# OSM relation IDs verified against Nominatim administrative results.
ZONE_RELATIONS = {
    "Anfa": 2801287,
    "Maarif": 2801474,
    "Sidi Belyout": 4743250,
    "Al Fida": 2801452,
    "Mers Sultan": 2801453,
    "Ben M'Sick": 2801410,
    "Sbata": 2801415,
    "Sidi Bernoussi": 2801461,
    "Sidi Moumen": 2801372,
    "Moulay Rachid": 2801402,
    "Sidi Othmane": 2801406,
    "Hay Hassani": 2801343,
    "Ain Chock": 2801442,
    "Ain Sebaa": 2801460,
    "Hay Mohammadi": 2801458,
    "Roches Noires": 2801457,
}


def collect() -> dict:
    relation_to_zone = {relation: zone for zone, relation in ZONE_RELATIONS.items()}
    response = requests.get(
        NOMINATIM_LOOKUP,
        params={
            "osm_ids": ",".join(f"R{relation}" for relation in relation_to_zone),
            "format": "jsonv2",
            "polygon_geojson": 1,
            "addressdetails": 1,
        },
        headers={"User-Agent": "InvestSearch/0.1 educational project"},
        timeout=120,
    )
    response.raise_for_status()

    features = []
    for item in response.json():
        relation = int(item["osm_id"])
        zone = relation_to_zone.get(relation)
        geometry = item.get("geojson")
        if not zone or not geometry or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            continue
        feature = {
            "type": "Feature",
            "properties": {
                "zone": zone,
                "osm_relation_id": relation,
                "display_name": item.get("display_name", zone),
                "geometry_source": "OpenStreetMap / Nominatim",
                "is_alias": False,
            },
            "geometry": geometry,
        }
        features.append(feature)

    collection = {
        "type": "FeatureCollection",
        "features": sorted(features, key=lambda feature: feature["properties"]["zone"]),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    return collection


if __name__ == "__main__":
    result = collect()
    print(f"Wrote {len(result['features'])} boundaries to {OUTPUT}")
