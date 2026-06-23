"""Export facilities and area indicators to GeoJSON for map visualization."""

import json
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
EXPORTS_DIR = DATA_DIR / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

FACILITIES_CSV = PROCESSED_DIR / "medical_facilities_clean.csv"
GEOJSON_OUTPUT = EXPORTS_DIR / "medical_facilities.geojson"


def facilities_to_geojson(df: pd.DataFrame) -> dict:
    features = []
    for _, row in df.iterrows():
        lat = row.get("lat")
        lon = row.get("lon")
        if pd.isna(lat) or pd.isna(lon):
            continue

        props = {}
        for col in df.columns:
            if col in ("lat", "lon"):
                continue
            val = row[col]
            if pd.isna(val):
                props[col] = None
            else:
                props[col] = val

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(lon), float(lat)],
            },
            "properties": props,
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def main():
    log.info("=== Step 6: Export to GeoJSON ===")

    if not FACILITIES_CSV.exists():
        log.error("Facilities not found: %s. Run previous steps.", FACILITIES_CSV)
        return

    df = pd.read_csv(FACILITIES_CSV, encoding="utf-8-sig")
    log.info("Loaded %d facilities", len(df))

    geojson = facilities_to_geojson(df)
    GEOJSON_OUTPUT.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Exported GeoJSON with %d features to %s", len(geojson["features"]), GEOJSON_OUTPUT)


if __name__ == "__main__":
    main()
