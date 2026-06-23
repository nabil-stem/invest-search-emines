"""Generalized OpenStreetMap (Overpass) collector, parameterized by sector.

This is the multi-sector successor to `osm_overpass.py` (which is hard-wired to
medical tags). It builds an Overpass query from a `Sector`'s `osm_filters`,
fetches POIs in the Casablanca bounding box, classifies each into a sub-category,
and returns a DataFrame with the same schema the cleaning pipeline already
expects — plus a `sector` column.

Usage (programmatic):
    from data_sources.osm_multisector import collect_sector
    df = collect_sector("food")

Caching: one JSON cache + CSV per sector under data/raw/, so re-runs don't hammer
the public Overpass endpoint.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import pandas as pd
import requests

from data_sources.sectors import Sector, get_sector

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"

OVERPASS_URL = os.environ.get("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
CASABLANCA_BBOX = "(33.45,-7.75,33.70,-7.45)"
USER_AGENT = "InvestSearch-Casablanca/2.0 (educational project)"


def cache_file(sector_key: str) -> Path:
    return RAW_DIR / f"osm_casablanca_{sector_key}.json"


def csv_file(sector_key: str) -> Path:
    return RAW_DIR / f"osm_casablanca_{sector_key}.csv"


def build_query(sector: Sector, bbox: str = CASABLANCA_BBOX) -> str:
    """Build an Overpass QL query for all of a sector's tag filters."""
    lines = []
    for key, value_regex in sector.osm_filters:
        if value_regex == ".+":
            selector = f'["{key}"]'
        else:
            # Anchor the alternation so a value only matches *exactly*. Without
            # ^(...)$ the regex is a substring match, so e.g. "pub" matched
            # "public_bath" (hammams leaked into the food sector) and "school"
            # matched "driving_school"/"language_school".
            selector = f'["{key}"~"^({value_regex})$"]'
        for element in ("node", "way", "relation"):
            lines.append(f"  {element}{selector}{bbox};")
    body = "\n".join(lines)
    return f"[out:json][timeout:120];\n(\n{body}\n);\nout center tags;\n"


def fetch_overpass(sector: Sector, use_cache: bool = True) -> dict:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache = cache_file(sector.key)
    if use_cache and cache.exists():
        log.info("[%s] loading cached Overpass response", sector.key)
        return json.loads(cache.read_text(encoding="utf-8"))

    query = build_query(sector)
    log.info("[%s] querying Overpass (%d filters)...", sector.key, len(sector.osm_filters))
    resp = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": USER_AGENT},
        timeout=180,
    )
    if resp.status_code != 200:
        log.error("[%s] Overpass returned %d: %s", sector.key, resp.status_code, resp.text[:300])
    resp.raise_for_status()
    data = resp.json()
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("[%s] cached %d elements", sector.key, len(data.get("elements", [])))
    return data


def classify(sector: Sector, tags: dict) -> str:
    """Classify a POI into a sub-category within the sector."""
    combined = " ".join(
        [
            tags.get("amenity", ""),
            tags.get("shop", ""),
            tags.get("healthcare", ""),
            tags.get("leisure", ""),
            tags.get("cuisine", ""),
            tags.get("name", ""),
        ]
    ).lower()
    for category, keywords in sector.categories.items():
        for kw in keywords:
            if kw in combined:
                return category
    # Fall back to the raw primary tag value so nothing is lost.
    for key in ("amenity", "shop", "leisure", "healthcare"):
        if tags.get(key):
            return tags[key]
    return "unknown"


def parse_elements(sector: Sector, data: dict) -> pd.DataFrame:
    rows = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        osm_type = el.get("type", "node")
        osm_id = el.get("id", "")

        if osm_type == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            center = el.get("center", {})
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue

        rows.append(
            {
                "id": f"osm_{osm_type}_{osm_id}",
                "name": tags.get("name", tags.get("name:fr", tags.get("name:ar", ""))),
                "name_fr": tags.get("name:fr", ""),
                "name_ar": tags.get("name:ar", ""),
                "sector": sector.key,
                "category": classify(sector, tags),
                "sub_category": tags.get("cuisine", tags.get("healthcare:speciality", "")),
                "address": tags.get("addr:full", tags.get("addr:street", "")),
                "lat": lat,
                "lon": lon,
                "phone": tags.get("phone", tags.get("contact:phone", "")),
                "website": tags.get("website", tags.get("contact:website", "")),
                "opening_hours": tags.get("opening_hours", ""),
                "operator": tags.get("operator", ""),
                "brand": tags.get("brand", ""),
                "source": "OSM",
                "source_type": "osm",
                "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
                "confidence_score": sector.confidence,
                "is_verified": False,
                "osm_amenity": tags.get("amenity", ""),
                "osm_shop": tags.get("shop", ""),
            }
        )
    return pd.DataFrame(rows)


def collect_sector(sector_key: str, use_cache: bool = True) -> pd.DataFrame:
    """Fetch + parse + save POIs for one sector. Returns the DataFrame."""
    sector = get_sector(sector_key)
    data = fetch_overpass(sector, use_cache=use_cache)
    df = parse_elements(sector, data)
    if not df.empty:
        out = csv_file(sector.key)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False, encoding="utf-8-sig")
        log.info("[%s] saved %d POIs to %s", sector.key, len(df), out)
    return df


def collect_many(sector_keys: list[str], use_cache: bool = True, pause_s: float = 3.0) -> dict[str, pd.DataFrame]:
    """Collect several sectors, pausing between live calls to respect Overpass."""
    out: dict[str, pd.DataFrame] = {}
    for i, key in enumerate(sector_keys):
        cached = cache_file(key).exists() and use_cache
        out[key] = collect_sector(key, use_cache=use_cache)
        if not cached and i < len(sector_keys) - 1:
            time.sleep(pause_s)
    return out
