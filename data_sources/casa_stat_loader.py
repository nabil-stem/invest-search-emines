"""Connector for Casa-Stat / E-Data CRI Casablanca-Settat.
Currently loads from manual CSV if available; API connector for future use."""

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load() -> pd.DataFrame:
    """Load Casa-Stat economic indicators from manual CSV."""
    path = DATA_DIR / "manual" / "purchasing_power_proxy.csv"
    if path.exists():
        df = pd.read_csv(path, encoding="utf-8-sig")
        log.info("Loaded Casa-Stat data: %d rows", len(df))
        return df
    log.info("No Casa-Stat data found at %s — using embedded proxy values", path)
    return pd.DataFrame()


def get_source_info() -> dict:
    return {
        "name": "Casa-Stat / E-Data CRI",
        "url": "https://edata.casainvest.ma/",
        "type": "institutional",
        "status": "manual_import",
        "description": "Socio-economic indicators for Casablanca-Settat region.",
    }
