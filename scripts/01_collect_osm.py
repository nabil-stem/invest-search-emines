"""Collect medical facilities from OpenStreetMap via Overpass API for Casablanca."""

import json
import logging
import time
from pathlib import Path

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

CACHE_FILE = RAW_DIR / "osm_casablanca_medical.json"
CSV_OUTPUT = RAW_DIR / "osm_casablanca_medical.csv"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

CASABLANCA_BBOX = "(33.45,-7.75,33.70,-7.45)"

OVERPASS_QUERY = """[out:json][timeout:120];
(
  node["amenity"~"hospital|clinic|doctors|pharmacy|dentist|veterinary"]BBOX;
  way["amenity"~"hospital|clinic|doctors|pharmacy|dentist|veterinary"]BBOX;
  relation["amenity"~"hospital|clinic|doctors|pharmacy|dentist|veterinary"]BBOX;
  node["healthcare"]BBOX;
  way["healthcare"]BBOX;
  relation["healthcare"]BBOX;
);
out center tags;
""".replace("BBOX", CASABLANCA_BBOX)

CATEGORY_MAP = {
    "hospital": ["hospital", "hôpital", "hopital", "chu"],
    "clinic": ["clinic", "clinique", "polyclinique"],
    "pharmacy": ["pharmacy", "pharmacie"],
    "doctor": ["doctors", "doctor", "cabinet médical", "medecin", "médecin"],
    "dentist": ["dentist", "dentiste"],
    "laboratory": ["laboratory", "lab", "laboratoire", "analyses"],
    "radiology": ["radiology", "radiologie", "imagerie", "scanner", "irm"],
    "health_center": ["centre de santé", "dispensaire", "essb", "health_centre"],
    "veterinary": ["veterinary", "vétérinaire"],
}


def fetch_overpass(use_cache: bool = True) -> dict:
    if use_cache and CACHE_FILE.exists():
        log.info("Loading cached Overpass response from %s", CACHE_FILE)
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))

    log.info("Querying Overpass API ...")
    log.debug("Query:\n%s", OVERPASS_QUERY)
    resp = requests.post(
        OVERPASS_URL,
        data={"data": OVERPASS_QUERY},
        headers={"User-Agent": "InvestSearch-Casablanca/1.0 (educational project)"},
        timeout=180,
    )
    if resp.status_code != 200:
        log.error("Overpass returned %d: %s", resp.status_code, resp.text[:500])
    resp.raise_for_status()
    data = resp.json()

    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved raw response to %s (%d elements)", CACHE_FILE, len(data.get("elements", [])))
    return data


def classify_category(tags: dict) -> str:
    amenity = tags.get("amenity", "").lower()
    healthcare = tags.get("healthcare", "").lower()
    name = tags.get("name", "").lower()

    combined = f"{amenity} {healthcare} {name}"

    for cat, keywords in CATEGORY_MAP.items():
        for kw in keywords:
            if kw in combined:
                return cat
    return "unknown"


def extract_subcategory(tags: dict) -> str:
    for key in ["healthcare:speciality", "healthcare:specialty", "medical_system:speciality"]:
        if key in tags:
            return tags[key]
    return ""


def parse_elements(data: dict) -> pd.DataFrame:
    rows = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        osm_type = el.get("type", "node")
        osm_id = el.get("id", "")

        if osm_type == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        else:
            center = el.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")

        if lat is None or lon is None:
            continue

        category = classify_category(tags)

        rows.append({
            "id": f"osm_{osm_type}_{osm_id}",
            "name": tags.get("name", tags.get("name:fr", tags.get("name:ar", ""))),
            "name_fr": tags.get("name:fr", ""),
            "name_ar": tags.get("name:ar", ""),
            "category": category,
            "sub_category": extract_subcategory(tags),
            "sector": "public" if "public" in tags.get("operator:type", "").lower() else
                      "private" if "private" in tags.get("operator:type", "").lower() else "unknown",
            "address": tags.get("addr:full", tags.get("addr:street", "")),
            "lat": lat,
            "lon": lon,
            "phone": tags.get("phone", tags.get("contact:phone", "")),
            "website": tags.get("website", tags.get("contact:website", "")),
            "opening_hours": tags.get("opening_hours", ""),
            "operator": tags.get("operator", ""),
            "beds": tags.get("beds", ""),
            "source": "OSM",
            "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
            "confidence_score": 0.70,
            "osm_amenity": tags.get("amenity", ""),
            "osm_healthcare": tags.get("healthcare", ""),
        })

    df = pd.DataFrame(rows)
    log.info("Parsed %d facilities", len(df))
    return df


def main():
    log.info("=== Step 1: Collect OSM data for Casablanca medical facilities ===")
    start = time.time()

    data = fetch_overpass(use_cache=True)
    df = parse_elements(data)

    if df.empty:
        log.warning("No facilities found. Check the Overpass query or network.")
        return

    df.to_csv(CSV_OUTPUT, index=False, encoding="utf-8-sig")
    log.info("Saved %d facilities to %s", len(df), CSV_OUTPUT)

    log.info("\nCategory breakdown:")
    for cat, count in df["category"].value_counts().items():
        log.info("  %-15s %d", cat, count)

    elapsed = time.time() - start
    log.info("Done in %.1f seconds.", elapsed)


if __name__ == "__main__":
    main()
