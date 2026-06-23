"""Collect OpenStreetMap POIs for one or more sectors (multi-sector pipeline).

Examples:
  python scripts/collect_multisector_osm.py --sector food
  python scripts/collect_multisector_osm.py --sector food retail wellness
  python scripts/collect_multisector_osm.py --all
  python scripts/collect_multisector_osm.py --sector food --refresh   # ignore cache

Outputs data/raw/osm_casablanca_<sector>.csv (+ .json cache) per sector and a
combined data/raw/osm_casablanca_multisector.csv.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_sources.osm_multisector import RAW_DIR, collect_many  # noqa: E402
from data_sources.sectors import SECTORS, sector_keys  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

COMBINED = RAW_DIR / "osm_casablanca_multisector.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sector", nargs="+", help="sector keys to collect")
    parser.add_argument("--all", action="store_true", help="collect every sector")
    parser.add_argument("--refresh", action="store_true", help="ignore cache, hit Overpass live")
    args = parser.parse_args()

    if args.all:
        # 'medical' has its own established pipeline (scripts/01 + osm_overpass.py)
        # and shares its raw filenames, so we don't re-collect it here.
        keys = [k for k in sector_keys() if k != "medical"]
    elif args.sector:
        keys = args.sector
    else:
        parser.error("pass --sector <keys> or --all")

    unknown = [k for k in keys if k not in SECTORS]
    if unknown:
        parser.error(f"unknown sectors {unknown}; available: {', '.join(SECTORS)}")

    print(f"Collecting sectors: {keys}  (cache={'off' if args.refresh else 'on'})\n")
    results = collect_many(keys, use_cache=not args.refresh)

    frames = []
    print(f"\n{'sector':<12} {'POIs':>6}  top categories")
    print("-" * 60)
    for key, df in results.items():
        if df.empty:
            print(f"{key:<12} {0:>6}  (none)")
            continue
        frames.append(df)
        top = df["category"].value_counts().head(4)
        top_str = ", ".join(f"{c}={n}" for c, n in top.items())
        print(f"{key:<12} {len(df):>6}  {top_str}")

    if frames:
        combined = pd.concat(frames, ignore_index=True)
        combined.to_csv(COMBINED, index=False, encoding="utf-8-sig")
        print(f"\nCombined {len(combined)} POIs across {len(frames)} sectors -> {COMBINED}")
        named = combined["name"].astype(str).str.strip().ne("").mean()
        geo = combined[["lat", "lon"]].notna().all(axis=1).mean()
        print(f"Quality: {named:.0%} named, {geo:.0%} geolocated")


if __name__ == "__main__":
    main()
