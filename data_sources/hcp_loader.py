"""Connector for HCP (Haut-Commissariat au Plan) data.
Currently loads from manual CSV if available; API connector for future use."""

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load() -> pd.DataFrame:
    """Load HCP population/demographic data from manual CSV."""
    path = DATA_DIR / "manual" / "population_by_zone.csv"
    if path.exists():
        df = pd.read_csv(path, encoding="utf-8-sig")
        log.info("Loaded HCP data: %d rows", len(df))
        return df
    log.info("No HCP data found at %s", path)
    return pd.DataFrame()


def get_source_info() -> dict:
    return {
        "name": "HCP (Haut-Commissariat au Plan)",
        "url": "https://www.hcp.ma/",
        "type": "official",
        "status": "manual_import",
        "description": "Population, demographics, household consumption by region.",
    }
