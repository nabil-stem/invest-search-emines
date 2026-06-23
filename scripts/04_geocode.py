"""Reverse-geocode facilities to enrich district/address info using Nominatim."""

import logging
import time
from pathlib import Path

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"

INPUT_CSV = PROCESSED_DIR / "medical_facilities_clean.csv"
OUTPUT_CSV = PROCESSED_DIR / "medical_facilities_geocoded.csv"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
HEADERS = {"User-Agent": "InvestSearch-Casablanca/1.0 (educational project)"}

RATE_LIMIT_S = 1.1


def reverse_geocode(lat: float, lon: float) -> dict:
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"lat": lat, "lon": lon, "format": "json", "addressdetails": 1, "zoom": 16},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            addr = data.get("address", {})
            return {
                "geo_suburb": addr.get("suburb", addr.get("neighbourhood", "")),
                "geo_city_district": addr.get("city_district", ""),
                "geo_road": addr.get("road", ""),
                "geo_postcode": addr.get("postcode", ""),
            }
    except requests.RequestException as e:
        log.warning("Geocoding failed for (%s, %s): %s", lat, lon, e)
    return {}


def main():
    log.info("=== Step 4: Reverse geocode facilities ===")

    if not INPUT_CSV.exists():
        log.error("Input not found: %s. Run 03_clean_normalize.py first.", INPUT_CSV)
        return

    df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")
    log.info("Loaded %d facilities", len(df))

    needs_geocoding = df[df["district"] == "Unknown"]
    log.info("%d facilities need reverse geocoding", len(needs_geocoding))

    if len(needs_geocoding) == 0:
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        log.info("No geocoding needed. Copied to %s", OUTPUT_CSV)
        return

    max_geocode = min(len(needs_geocoding), 200)
    log.info("Will geocode up to %d facilities (respecting Nominatim rate limits)", max_geocode)

    count = 0
    for idx in needs_geocoding.index[:max_geocode]:
        row = df.loc[idx]
        result = reverse_geocode(row["lat"], row["lon"])
        if result:
            for k, v in result.items():
                df.at[idx, k] = v
            if result.get("geo_suburb"):
                df.at[idx, "district"] = result["geo_suburb"]
            elif result.get("geo_city_district"):
                df.at[idx, "district"] = result["geo_city_district"]
        count += 1
        if count % 20 == 0:
            log.info("  Geocoded %d / %d", count, max_geocode)
        time.sleep(RATE_LIMIT_S)

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    log.info("Saved geocoded data to %s", OUTPUT_CSV)


if __name__ == "__main__":
    main()
