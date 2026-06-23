"""Compatibility accessors for the generated official Casablanca baseline.

The authoritative generation step is ``scripts/02_collect_official_sources.py``.
This module intentionally contains no duplicate demographic constants.
"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BASELINE_CSV = DATA_DIR / "manual" / "official_baseline.csv"
DISTRICTS_CSV = DATA_DIR / "raw" / "casablanca_districts.csv"


def create_baseline() -> pd.DataFrame:
    if not BASELINE_CSV.exists():
        raise FileNotFoundError("Run scripts/02_collect_official_sources.py first")
    return pd.read_csv(BASELINE_CSV, encoding="utf-8-sig")


def create_districts() -> pd.DataFrame:
    if not DISTRICTS_CSV.exists():
        raise FileNotFoundError("Run scripts/02_collect_official_sources.py first")
    return pd.read_csv(DISTRICTS_CSV, encoding="utf-8-sig")


def collect_all() -> tuple[pd.DataFrame, pd.DataFrame]:
    return create_baseline(), create_districts()
