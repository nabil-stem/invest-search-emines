"""Enrich facility data: ensure all required columns, normalize, assign districts."""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from data_sources.zone_boundaries import assign_zone, load_zone_boundaries

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

REQUIRED_COLS = {
    "id": "", "name": "", "original_name": "", "category": "unknown",
    "sub_category": "", "sector": "unknown", "address": "",
    "zone": "", "district": "Unknown", "prefecture": "",
    "lat": np.nan, "lon": np.nan,
    "phone": "", "website": "", "opening_hours": "",
    "rating": np.nan, "review_count": 0,
    "source": "unknown", "source_url": "", "source_type": "unknown",
    "confidence_score": 0.5, "last_verified_at": "",
    "is_verified": False, "is_duplicate_suspect": False,
}

VALID_CATEGORIES = [
    "hospital", "clinic", "pharmacy", "doctor", "dentist",
    "laboratory", "radiology", "health_center", "veterinary", "unknown",
]


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col, default in REQUIRED_COLS.items():
        if col not in df.columns:
            df[col] = default
    return df


def normalize_categories(df: pd.DataFrame) -> pd.DataFrame:
    if "category" in df.columns:
        df["category"] = df["category"].fillna("unknown").str.lower().str.strip()
        df.loc[~df["category"].isin(VALID_CATEGORIES), "category"] = "unknown"
    return df


def assign_districts(df: pd.DataFrame) -> pd.DataFrame:
    """Assign records to the 16 Casablanca arrondissements using OSM polygons."""
    districts_path = RAW_DIR / "casablanca_districts.csv"
    if not districts_path.exists():
        return df

    districts = pd.read_csv(districts_path, encoding="utf-8-sig")
    boundaries = load_zone_boundaries()

    df["district"] = df.apply(
        lambda r: assign_zone(r["lat"], r["lon"], boundaries, districts),
        axis=1,
    )
    df["zone"] = df["district"]
    return df


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Full enrichment pipeline for a facility DataFrame."""
    df = df.copy()
    if "original_name" not in df.columns:
        df["original_name"] = df.get("name", "")

    df = ensure_columns(df)
    df = normalize_categories(df)

    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["confidence_score"] = pd.to_numeric(df["confidence_score"], errors="coerce").fillna(0.5).clip(0, 1)

    # Clean names
    if "name" in df.columns:
        df["name"] = df["name"].fillna("").str.strip()

    # Filter to Casablanca bounding box
    df = df[
        (df["lat"].between(33.0, 34.0) | df["lat"].isna()) &
        (df["lon"].between(-8.0, -7.0) | df["lon"].isna())
    ]

    df = assign_districts(df)
    return df
