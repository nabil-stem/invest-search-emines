"""Data loading, column enforcement, and normalization utilities."""

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
EXPORTS_DIR = DATA_DIR / "exports"
RAW_DIR = DATA_DIR / "raw"

REQUIRED_FACILITY_COLS = {
    "id": "", "name": "", "original_name": "", "category": "unknown",
    "sub_category": "", "sector": "unknown", "district": "Unknown",
    "zone": "", "prefecture": "", "address": "",
    "lat": np.nan, "lon": np.nan,
    "phone": "", "website": "", "opening_hours": "",
    "operator": "", "beds": "",
    "rating": np.nan, "review_count": 0,
    "source": "unknown", "source_url": "", "source_type": "unknown",
    "confidence_score": 0.5, "last_verified_at": "2026-05-18",
    "is_verified": False, "is_duplicate_suspect": False,
}

VALID_CATEGORIES = [
    "hospital", "clinic", "pharmacy", "doctor", "dentist",
    "laboratory", "radiology", "health_center", "veterinary", "unknown",
]


def ensure_required_columns(df: pd.DataFrame, defaults: dict) -> pd.DataFrame:
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default
    return df


def normalize_categories(df: pd.DataFrame) -> pd.DataFrame:
    if "category" in df.columns:
        df["category"] = df["category"].fillna("unknown").str.lower().str.strip()
        df.loc[~df["category"].isin(VALID_CATEGORIES), "category"] = "unknown"
    return df


@st.cache_data(ttl=300)
def load_facilities() -> pd.DataFrame:
    path = PROCESSED_DIR / "medical_facilities_clean.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = ensure_required_columns(df, REQUIRED_FACILITY_COLS)
    df = normalize_categories(df)
    df["confidence_score"] = pd.to_numeric(df["confidence_score"], errors="coerce").fillna(0.5)
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    if "zone" not in df.columns or df["zone"].isna().all():
        df["zone"] = df["district"]
    return df


@st.cache_data(ttl=300)
def load_area_indicators() -> pd.DataFrame:
    path = PROCESSED_DIR / "area_indicators.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8-sig")
    for col in ["investment_score", "undersupply_index", "demand_index",
                 "accessibility_index", "low_competition_index"]:
        if col not in df.columns:
            df[col] = 50.0
    # Merge purchasing power proxy from district data if available
    if "purchasing_power_proxy" not in df.columns:
        dist_path = RAW_DIR / "casablanca_districts.csv"
        if dist_path.exists():
            dist = pd.read_csv(dist_path, encoding="utf-8-sig")
            if "purchasing_power_proxy" in dist.columns:
                pp = dist[["area_name", "purchasing_power_proxy"]].drop_duplicates()
                df = df.merge(pp, on="area_name", how="left")
        if "purchasing_power_proxy" not in df.columns:
            df["purchasing_power_proxy"] = 50.0
    df["purchasing_power_proxy"] = pd.to_numeric(
        df["purchasing_power_proxy"], errors="coerce"
    ).fillna(50.0)
    return df


@st.cache_data(ttl=300)
def load_specialty_supply() -> pd.DataFrame:
    path = PROCESSED_DIR / "specialty_supply.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


@st.cache_data(ttl=300)
def load_opportunities() -> pd.DataFrame:
    path = EXPORTS_DIR / "investment_opportunities.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def get_zone_names(areas: pd.DataFrame) -> list[str]:
    if areas.empty or "area_name" not in areas.columns:
        return []
    return sorted(areas["area_name"].dropna().unique().tolist())
