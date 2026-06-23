"""Responsible web-scraping helpers for enriching the Invest Search database.

Design principles (this matters — scraping carelessly gets you blocked and can
breach ToS):
  * Descriptive User-Agent identifying the project.
  * On-disk HTML cache so re-runs never re-hit the server.
  * Polite delay between live requests.
  * Targets an openly-licensed source (Wikipedia, CC BY-SA) for demographic data.

The first enrichment target is per-arrondissement population / area for
Casablanca, used to cross-validate and fill `data/raw/casablanca_districts.csv`
(which drives population_density -> DemandIndex for *every* sector, so it helps
medical and the new multi-sector data alike).
"""

from __future__ import annotations

import logging
import time
import unicodedata
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = RAW_DIR / "cache"

USER_AGENT = (
    "InvestSearch-Casablanca/2.0 (educational research project; "
    "contact: project maintainer) requests"
)
DEFAULT_DELAY_S = 2.0

# French Wikipedia article that tabulates Casablanca's arrondissements.
WIKI_DISTRICTS_URL = "https://fr.wikipedia.org/wiki/Pr%C3%A9fecture_de_Casablanca"
OUTPUT_CSV = RAW_DIR / "wikipedia_casablanca_districts.csv"


def _slug(url: str) -> str:
    keep = "".join(c if c.isalnum() else "_" for c in url)
    return keep[-120:]


def polite_get(url: str, use_cache: bool = True, delay_s: float = DEFAULT_DELAY_S) -> str:
    """Fetch a URL politely: cached, descriptive UA, rate-limited."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{_slug(url)}.html"
    if use_cache and cache.exists():
        log.info("cache hit: %s", url)
        return cache.read_text(encoding="utf-8")

    log.info("fetching: %s", url)
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    cache.write_text(resp.text, encoding="utf-8")
    time.sleep(delay_s)  # be polite to the server
    return resp.text


def _norm(text: str) -> str:
    text = "".join(c for c in unicodedata.normalize("NFKD", str(text).lower()) if not unicodedata.combining(c))
    return text.strip()


def _find_population_table(tables: list[pd.DataFrame]) -> pd.DataFrame | None:
    """Pick the table that looks like an arrondissement/population breakdown."""
    best, best_score = None, 0
    for df in tables:
        cols = [_norm(c) for c in df.columns.astype(str)]
        joined = " ".join(cols)
        score = 0
        if any("arrondissement" in c or "commune" in c or "nom" in c for c in cols):
            score += 2
        if "population" in joined or "habitant" in joined:
            score += 2
        if "superficie" in joined or "km" in joined:
            score += 1
        if score > best_score and len(df) >= 3:
            best, best_score = df, score
    return best if best_score >= 2 else None


def scrape_casablanca_districts(use_cache: bool = True) -> pd.DataFrame:
    """Scrape per-arrondissement demographics from Wikipedia. Saves a tidy CSV."""
    html = polite_get(WIKI_DISTRICTS_URL, use_cache=use_cache)
    tables = pd.read_html(StringIO(html))
    log.info("parsed %d tables", len(tables))

    table = _find_population_table(tables)
    if table is None:
        log.warning("no population table matched; saving raw tables for inspection")
        raw = RAW_DIR / "wikipedia_casablanca_raw_tables.txt"
        raw.write_text(
            "\n\n".join(f"TABLE {i} cols={list(t.columns)}\n{t.head().to_string()}" for i, t in enumerate(tables)),
            encoding="utf-8",
        )
        return pd.DataFrame()

    # Normalise to a tidy schema: name / population / area_km2 where detectable.
    table = table.copy()
    table.columns = [str(c) for c in table.columns]
    rename = {}
    for c in table.columns:
        n = _norm(c)
        # Order matters: a "prefecture d'arrondissement" column contains the word
        # "arrondissement" too, so test prefecture first.
        if "prefecture" in n:
            rename[c] = "prefecture"
        elif "population" in n or "habitant" in n:
            rename[c] = "population"
        elif "superficie" in n or "km" in n:
            rename[c] = "area_km2"
        elif "arrondissement" in n or n in ("nom", "commune") or "nom" in n:
            rename[c] = "name"
    table = table.rename(columns=rename)

    keep = [c for c in ("name", "prefecture", "population", "area_km2") if c in table.columns]
    tidy = table[keep].copy() if keep else table
    if "name" in tidy.columns:
        # Accent-stripped key so the scrape joins to our zone convention
        # ("Aïn Chock" -> "Ain Chock", "Maârif" -> "Maarif").
        tidy["name_ascii"] = tidy["name"].map(
            lambda s: "".join(
                c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c)
            ).strip()
        )
    tidy["source"] = "wikipedia"
    tidy["source_url"] = WIKI_DISTRICTS_URL

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    tidy.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    log.info("saved %d rows to %s", len(tidy), OUTPUT_CSV)
    return tidy


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    df = scrape_casablanca_districts()
    if df.empty:
        print("No structured population table found; see wikipedia_casablanca_raw_tables.txt")
    else:
        print(df.to_string(index=False))
