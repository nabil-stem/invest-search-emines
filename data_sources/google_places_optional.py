"""Optional Google Places API enrichment. Only runs if GOOGLE_PLACES_API_KEY is set."""

import logging
import os
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


def is_available() -> bool:
    return bool(os.environ.get("GOOGLE_PLACES_API_KEY", "").strip())


def get_status_message() -> str:
    if is_available():
        return "Google Places API: enabled."
    return "Google Places enrichment disabled: no API key found. Set GOOGLE_PLACES_API_KEY in .env to enable."


def enrich_facility(name: str, lat: float, lon: float) -> dict:
    """Enrich a single facility using Google Places Nearby Search.
    Returns dict with enriched fields or empty dict if unavailable."""
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    if not api_key:
        return {}

    import requests
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
            params={
                "location": f"{lat},{lon}",
                "radius": 50,
                "keyword": name,
                "key": api_key,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return {}
        results = resp.json().get("results", [])
        if not results:
            return {}

        place = results[0]
        return {
            "gp_name": place.get("name", ""),
            "gp_rating": place.get("rating"),
            "gp_review_count": place.get("user_ratings_total", 0),
            "gp_address": place.get("vicinity", ""),
            "gp_place_id": place.get("place_id", ""),
            "gp_types": ",".join(place.get("types", [])),
        }
    except Exception as e:
        log.warning("Google Places error for %s: %s", name, e)
        return {}


def enrich_dataframe(df: pd.DataFrame, max_rows: int = 100) -> pd.DataFrame:
    """Enrich up to max_rows facilities. Adds gp_ prefixed columns."""
    if not is_available() or df.empty:
        return df

    df = df.copy()
    geo = df.dropna(subset=["lat", "lon"]).head(max_rows)
    log.info("Enriching %d facilities via Google Places API", len(geo))

    for idx in geo.index:
        row = df.loc[idx]
        result = enrich_facility(str(row.get("name", "")), row["lat"], row["lon"])
        for k, v in result.items():
            df.at[idx, k] = v
        if result.get("gp_rating"):
            df.at[idx, "rating"] = result["gp_rating"]
        if result.get("gp_review_count"):
            df.at[idx, "review_count"] = result["gp_review_count"]
        if result:
            df.at[idx, "confidence_score"] = min(1.0, df.at[idx, "confidence_score"] + 0.1)

    return df
