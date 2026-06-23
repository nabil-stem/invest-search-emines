"""Import manually curated CSV files from data/manual/."""

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MANUAL_DIR = DATA_DIR / "manual"

EXPECTED_FILES = {
    "official_health_baseline.csv": "Official health metrics (hospitals, beds, doctors)",
    "population_by_zone.csv": "Population per zone/district",
    "purchasing_power_proxy.csv": "Purchasing power proxy per zone",
    "rent_proxy_by_zone.csv": "Rent cost proxy per zone",
    "traffic_or_accessibility_proxy.csv": "Traffic/accessibility proxy per zone",
    "manual_verified_facilities.csv": "Manually verified medical facilities",
}


def list_available() -> dict[str, bool]:
    """Return {filename: exists_bool} for all expected manual files."""
    return {f: (MANUAL_DIR / f).exists() for f in EXPECTED_FILES}


def load_manual_facilities() -> pd.DataFrame:
    path = MANUAL_DIR / "manual_verified_facilities.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8-sig")
    if "source" not in df.columns:
        df["source"] = "manual"
    if "source_type" not in df.columns:
        df["source_type"] = "manual_verified"
    if "confidence_score" not in df.columns:
        df["confidence_score"] = 0.90
    if "is_verified" not in df.columns:
        df["is_verified"] = True
    log.info("Loaded %d manually verified facilities", len(df))
    return df


def load_purchasing_power() -> pd.DataFrame:
    path = MANUAL_DIR / "purchasing_power_proxy.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def load_population() -> pd.DataFrame:
    path = MANUAL_DIR / "population_by_zone.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def load_rent_proxy() -> pd.DataFrame:
    path = MANUAL_DIR / "rent_proxy_by_zone.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")
