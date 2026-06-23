"""Build the Casablanca territorial baseline from versioned official data."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MANUAL_DIR = DATA_DIR / "manual"
RAW_DIR = DATA_DIR / "raw"
EXPORTS_DIR = DATA_DIR / "exports"
MANUAL_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

HCP_CSV = MANUAL_DIR / "hcp_rgph_2024_casablanca.csv"
MSPS_CSV = MANUAL_DIR / "msps_public_facilities_2024.csv"
BOUNDARIES_GEOJSON = EXPORTS_DIR / "casablanca_zone_boundaries.geojson"
BASELINE_CSV = MANUAL_DIR / "official_baseline.csv"
OUTPUT_CSV = RAW_DIR / "official_indicators.csv"
DISTRICTS_CSV = RAW_DIR / "casablanca_districts.csv"

HCP_SOURCE_URL = "https://www.hcp.ma/file/242341/"
MSPS_PRIMARY_SOURCE_URL = (
    "https://data.gov.ma/data/fr/dataset/2932e8a4-272c-4101-80ef-85519de47e7c"
)
MSPS_HOSPITAL_SOURCE_URL = (
    "https://data.gov.ma/data/fr/dataset/0977885b-7596-4499-9880-bf9f375e3c72"
)

# This is deliberately labelled as a heuristic. It is not an HCP income series.
PURCHASING_POWER_PROXY = {
    "Anfa": 80,
    "Maarif": 75,
    "Sidi Belyout": 70,
    "Al Fida": 40,
    "Mers Sultan": 50,
    "Hay Mohammadi": 35,
    "Roches Noires": 50,
    "Ain Sebaa": 45,
    "Hay Hassani": 50,
    "Ain Chock": 55,
    "Sidi Bernoussi": 40,
    "Sidi Moumen": 30,
    "Ben M'Sick": 35,
    "Sbata": 40,
    "Moulay Rachid": 35,
    "Sidi Othmane": 35,
}


def _iter_rings(geometry: dict):
    if geometry.get("type") == "Polygon":
        yield from geometry.get("coordinates", [])
    elif geometry.get("type") == "MultiPolygon":
        for polygon in geometry.get("coordinates", []):
            yield from polygon


def _ring_area_km2(ring: list[list[float]]) -> float:
    if len(ring) < 3:
        return 0.0
    mean_lat = math.radians(sum(point[1] for point in ring) / len(ring))
    radius = 6_371_008.8
    projected = [
        (radius * math.radians(lon) * math.cos(mean_lat), radius * math.radians(lat))
        for lon, lat in ring
    ]
    area_m2 = abs(
        sum(
            projected[i][0] * projected[(i + 1) % len(projected)][1]
            - projected[(i + 1) % len(projected)][0] * projected[i][1]
            for i in range(len(projected))
        )
    ) / 2
    return area_m2 / 1_000_000


def _geometry_stats(geometry: dict) -> dict:
    rings = list(_iter_rings(geometry))
    if not rings:
        raise ValueError("Boundary geometry has no polygon rings")

    area_km2 = 0.0
    if geometry.get("type") == "Polygon":
        polygons = [geometry.get("coordinates", [])]
    else:
        polygons = geometry.get("coordinates", [])
    for polygon in polygons:
        if polygon:
            area_km2 += _ring_area_km2(polygon[0])
            area_km2 -= sum(_ring_area_km2(hole) for hole in polygon[1:])

    points = [point for ring in rings for point in ring]
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    return {
        "area_km2": round(max(area_km2, 0.01), 3),
        "lat_min": min(lats),
        "lat_max": max(lats),
        "lon_min": min(lons),
        "lon_max": max(lons),
    }


def _load_boundary_stats() -> dict[str, dict]:
    if not BOUNDARIES_GEOJSON.exists():
        raise FileNotFoundError(
            f"Missing {BOUNDARIES_GEOJSON}. Run scripts/07_collect_zone_boundaries.py first."
        )
    collection = json.loads(BOUNDARIES_GEOJSON.read_text(encoding="utf-8"))
    return {
        feature["properties"]["zone"]: _geometry_stats(feature["geometry"])
        for feature in collection.get("features", [])
        if not feature.get("properties", {}).get("is_alias")
    }


def create_baseline() -> pd.DataFrame:
    hcp = pd.read_csv(HCP_CSV, encoding="utf-8-sig")
    msps = pd.read_csv(MSPS_CSV, encoding="utf-8-sig")
    baseline = pd.DataFrame(
        [
            {
                "metric": "population_16_arrondissements",
                "geography": "Casablanca",
                "value": int(hcp["population_total"].sum()),
                "year": 2024,
                "source": "HCP RGPH 2024",
                "source_url": HCP_SOURCE_URL,
                "notes": "Somme des 16 arrondissements; Mechouar exclu",
            },
            {
                "metric": "public_primary_care_facilities",
                "geography": "16 arrondissements de Casablanca",
                "value": int(msps["public_primary_care_count"].sum()),
                "year": 2024,
                "source": "MSPS",
                "source_url": MSPS_PRIMARY_SOURCE_URL,
                "notes": "117 etablissements affectes; 1 centre du Mechouar hors perimetre",
            },
            {
                "metric": "public_hospitals",
                "geography": "16 arrondissements de Casablanca",
                "value": int(msps["public_hospital_count"].sum()),
                "year": 2024,
                "source": "MSPS",
                "source_url": MSPS_HOSPITAL_SOURCE_URL,
                "notes": "Liste nominative agregee par arrondissement",
            },
        ]
    )
    baseline.to_csv(BASELINE_CSV, index=False, encoding="utf-8-sig")
    baseline.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    return baseline


def create_districts() -> pd.DataFrame:
    hcp = pd.read_csv(HCP_CSV, encoding="utf-8-sig")
    msps = pd.read_csv(MSPS_CSV, encoding="utf-8-sig")
    boundary_stats = _load_boundary_stats()

    if len(hcp) != 16 or hcp["area_name"].nunique() != 16:
        raise ValueError("The HCP Casablanca baseline must contain exactly 16 arrondissements")
    missing = sorted(set(hcp["area_name"]) - set(boundary_stats))
    if missing:
        raise ValueError(f"Missing administrative boundaries for: {', '.join(missing)}")

    rows = []
    for _, source_row in hcp.iterrows():
        area_name = str(source_row["area_name"])
        population = int(source_row["population_total"])
        stats = boundary_stats[area_name]
        rows.append(
            {
                "area_id": source_row["area_id"],
                "area_name": area_name,
                "prefecture": source_row["prefecture"],
                "hcp_code": str(source_row["hcp_code"]),
                "population_est": population,
                "population_year": int(source_row["population_year"]),
                "households": int(source_row["households"]),
                "area_km2": stats["area_km2"],
                "population_density": round(population / stats["area_km2"], 1),
                "purchasing_power_proxy": PURCHASING_POWER_PROXY[area_name],
                "purchasing_power_confidence": 0.35,
                "population_source": "HCP RGPH 2024",
                "population_source_url": source_row["source_url"],
                "boundary_source": "OpenStreetMap / Nominatim",
                **{key: stats[key] for key in ("lat_min", "lat_max", "lon_min", "lon_max")},
            }
        )

    districts = pd.DataFrame(rows).merge(
        msps[["area_name", "public_primary_care_count", "public_hospital_count"]],
        on="area_name",
        how="left",
    )
    districts.to_csv(DISTRICTS_CSV, index=False, encoding="utf-8-sig")
    log.info("Written %d official Casablanca arrondissements to %s", len(districts), DISTRICTS_CSV)
    return districts


def main():
    log.info("=== Step 2: Prepare official HCP and MSPS data ===")
    create_baseline()
    create_districts()
    log.info("Official 2024 data ready for scoring")


if __name__ == "__main__":
    main()
