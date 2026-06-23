"""Clean, normalize, and deduplicate medical facility data."""

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_sources.zone_boundaries import assign_zone, load_zone_boundaries

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

INPUT_CSV = RAW_DIR / "osm_casablanca_medical.csv"
OUTPUT_CSV = PROCESSED_DIR / "medical_facilities_clean.csv"

CATEGORY_NORMALIZE = {
    "hospital": ["hospital", "hôpital", "hopital", "chu"],
    "clinic": ["clinic", "clinique", "polyclinique"],
    "pharmacy": ["pharmacy", "pharmacie"],
    "doctor": ["doctors", "doctor", "cabinet médical", "medecin", "médecin"],
    "dentist": ["dentist", "dentiste"],
    "laboratory": ["laboratory", "lab", "laboratoire", "analyses"],
    "radiology": ["radiology", "radiologie", "imagerie", "scanner", "irm"],
    "health_center": ["centre de santé", "dispensaire", "essb", "health_centre"],
    "veterinary": ["veterinary", "vétérinaire"],
}


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))


def normalize_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    name = name.strip()
    while "  " in name:
        name = name.replace("  ", " ")
    return name


def re_classify(row: pd.Series) -> str:
    name_lower = str(row.get("name", "")).lower()
    amenity = str(row.get("osm_amenity", "")).lower()
    healthcare = str(row.get("osm_healthcare", "")).lower()
    combined = f"{amenity} {healthcare} {name_lower}"

    for cat, keywords in CATEGORY_NORMALIZE.items():
        for kw in keywords:
            if kw in combined:
                return cat
    return row.get("category", "unknown")


def assign_district(lat, lon, districts_df, boundaries):
    return assign_zone(lat, lon, boundaries, districts_df)


def deduplicate(df: pd.DataFrame, distance_threshold_m=50, similarity_threshold=85) -> pd.DataFrame:
    if df.empty:
        return df

    keep = [True] * len(df)
    indices = df.index.tolist()

    for i in range(len(indices)):
        if not keep[i]:
            continue
        for j in range(i + 1, len(indices)):
            if not keep[j]:
                continue

            ri = df.loc[indices[i]]
            rj = df.loc[indices[j]]

            if ri["category"] != rj["category"]:
                continue

            dist = haversine_m(ri["lat"], ri["lon"], rj["lat"], rj["lon"])
            if dist > distance_threshold_m:
                continue

            name_i = str(ri.get("name", ""))
            name_j = str(rj.get("name", ""))
            if name_i and name_j:
                sim = fuzz.token_sort_ratio(name_i.lower(), name_j.lower())
                if sim < similarity_threshold:
                    continue

            keep[j] = False

    removed = sum(1 for k in keep if not k)
    log.info("Deduplication: removed %d duplicates out of %d", removed, len(df))
    return df.loc[[indices[i] for i, k in enumerate(keep) if k]].reset_index(drop=True)


def main():
    log.info("=== Step 3: Clean and normalize medical facilities ===")

    if not INPUT_CSV.exists():
        log.error("Input file not found: %s. Run 01_collect_osm.py first.", INPUT_CSV)
        return

    df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")
    log.info("Loaded %d raw facilities", len(df))

    df["original_name"] = df["name"]
    df["name"] = df["name"].apply(normalize_name)

    df["category"] = df.apply(re_classify, axis=1)

    df = df.dropna(subset=["lat", "lon"])
    df = df[(df["lat"] >= 33.0) & (df["lat"] <= 34.0)]
    df = df[(df["lon"] >= -8.0) & (df["lon"] <= -7.0)]

    districts_path = RAW_DIR / "casablanca_districts.csv"
    if districts_path.exists():
        districts_df = pd.read_csv(districts_path, encoding="utf-8-sig")
        boundaries = load_zone_boundaries()
        df["district"] = df.apply(
            lambda r: assign_district(r["lat"], r["lon"], districts_df, boundaries),
            axis=1,
        )
    else:
        df["district"] = "Unknown"

    df = deduplicate(df)

    cols = [
        "id", "name", "original_name", "name_fr", "name_ar",
        "category", "sub_category", "sector", "district",
        "address", "lat", "lon",
        "phone", "website", "opening_hours", "operator", "beds",
        "source", "source_url", "confidence_score",
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = ""

    df = df[cols]
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    log.info("Saved %d clean facilities to %s", len(df), OUTPUT_CSV)

    log.info("\nCategory breakdown after cleaning:")
    for cat, count in df["category"].value_counts().items():
        log.info("  %-15s %d", cat, count)

    log.info("\nDistrict breakdown:")
    for dist, count in df["district"].value_counts().head(10).items():
        log.info("  %-25s %d", dist, count)


if __name__ == "__main__":
    main()
