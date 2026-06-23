"""Geocoding and reverse geocoding with Nominatim, with local JSON cache."""

import json
import logging
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE_FILE = CACHE_DIR / "geocoding_cache.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
HEADERS = {"User-Agent": "InvestSearch-Casablanca/2.0 (educational project)"}
RATE_LIMIT_S = 1.1

_cache: dict | None = None


def _load_cache() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if CACHE_FILE.exists():
        _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    else:
        _cache = {}
    return _cache


def _save_cache():
    if _cache is not None:
        CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8")


def reverse_geocode(lat: float, lon: float) -> dict:
    """Return {suburb, city_district, road, postcode} for a lat/lon pair."""
    cache = _load_cache()
    key = f"{lat:.6f},{lon:.6f}"
    if key in cache:
        return cache[key]

    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"lat": lat, "lon": lon, "format": "json", "addressdetails": 1, "zoom": 16},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            addr = resp.json().get("address", {})
            result = {
                "suburb": addr.get("suburb", addr.get("neighbourhood", "")),
                "city_district": addr.get("city_district", ""),
                "road": addr.get("road", ""),
                "postcode": addr.get("postcode", ""),
            }
            cache[key] = result
            _save_cache()
            time.sleep(RATE_LIMIT_S)
            return result
    except requests.RequestException as e:
        log.warning("Geocoding failed for (%s, %s): %s", lat, lon, e)
    return {}
