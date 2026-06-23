"""Compute investment opportunity scores per district and specialty."""

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.scoring import INVESTMENT_CATEGORIES, compute_opportunity_scores

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MANUAL_DIR = DATA_DIR / "manual"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

FACILITIES_CSV = PROCESSED_DIR / "medical_facilities_clean.csv"
DISTRICTS_CSV = RAW_DIR / "casablanca_districts.csv"
OFFICIAL_PUBLIC_CSV = MANUAL_DIR / "msps_public_facilities_2024.csv"

AREA_INDICATORS_CSV = PROCESSED_DIR / "area_indicators.csv"
SPECIALTY_SUPPLY_CSV = PROCESSED_DIR / "specialty_supply.csv"
OPPORTUNITIES_CSV = DATA_DIR / "exports" / "investment_opportunities.csv"

COMPETITION_RADII_KM = {
    "pharmacy": 0.5,
    "doctor": 1.0,
    "dentist": 1.0,
    "veterinary": 2.0,
    "laboratory": 3.0,
    "radiology": 3.0,
    "clinic": 5.0,
    "hospital": 5.0,
    "health_center": 2.0,
}

CATEGORIES = [
    "pharmacy", "doctor", "dentist", "veterinary", "laboratory",
    "radiology", "clinic", "hospital", "health_center",
]

# Analytical saturation references, not regulatory quotas. They make competition
# comparable between categories while the UI clearly exposes data confidence.
COMPETITION_BENCHMARKS_PER_100K = {
    "pharmacy": 20.0,
    "doctor": 15.0,
    "dentist": 8.0,
    "veterinary": 2.0,
    "laboratory": 3.0,
    "radiology": 1.5,
    "clinic": 4.0,
    "hospital": 1.5,
    "health_center": 4.0,
}

# Estimated completeness of the currently available local inventory by category.
# Low values prevent a zero OSM count from being interpreted as proven absence.
CATEGORY_COMPLETENESS = {
    "pharmacy": 78.0,
    "doctor": 45.0,
    "dentist": 55.0,
    "veterinary": 35.0,
    "laboratory": 50.0,
    "radiology": 35.0,
    "clinic": 62.0,
    "hospital": 82.0,
    "health_center": 82.0,
}


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))


def normalize_0_100(series: pd.Series) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(50.0, index=series.index)
    return ((series - mn) / (mx - mn)) * 100


def compute_area_indicators(
    facilities: pd.DataFrame,
    districts: pd.DataFrame,
    official_public: pd.DataFrame | None = None,
) -> pd.DataFrame:
    official_public = official_public if official_public is not None else pd.DataFrame()
    official_lookup = (
        official_public.set_index("area_name").to_dict("index")
        if not official_public.empty
        else {}
    )
    confidence = pd.to_numeric(facilities.get("confidence_score"), errors="coerce")
    global_osm_confidence = float(confidence.mean()) if confidence.notna().any() else 0.65
    rows = []
    for _, dist in districts.iterrows():
        area_name = dist["area_name"]
        pop = dist.get("population_est", 0)
        area_km2 = dist.get("area_km2", 1)
        pop_density = pop / area_km2 if area_km2 > 0 else 0

        local = facilities[facilities["district"] == area_name]
        total = len(local)

        cats = {}
        for cat in CATEGORIES:
            cats[f"{cat}_count"] = len(local[local["category"] == cat])

        per_100k = (total / pop * 100_000) if pop > 0 else 0

        hospital_lats = facilities[facilities["category"] == "hospital"]["lat"].values
        hospital_lons = facilities[facilities["category"] == "hospital"]["lon"].values
        dist_center_lat = dist.get("lat_min", 33.55)
        dist_center_lon = dist.get("lon_min", -7.60)
        if len(dist.dropna()) >= 6:
            dist_center_lat = (dist.get("lat_min", 33.55) + dist.get("lat_max", 33.60)) / 2
            dist_center_lon = (dist.get("lon_min", -7.60) + dist.get("lon_max", -7.55)) / 2

        if len(hospital_lats) > 0:
            distances = [
                haversine_km(dist_center_lat, dist_center_lon, hlat, hlon)
                for hlat, hlon in zip(hospital_lats, hospital_lons)
            ]
            nearest_hospital_km = min(distances)
        else:
            nearest_hospital_km = 99.0

        public = official_lookup.get(area_name, {})
        local_confidence = pd.to_numeric(local.get("confidence_score"), errors="coerce").mean()
        if pd.isna(local_confidence):
            local_confidence = global_osm_confidence

        rows.append({
            "area_id": dist["area_id"],
            "area_name": area_name,
            "prefecture": dist.get("prefecture", ""),
            "population_est": pop,
            "area_km2": area_km2,
            "population_density": round(pop_density, 1),
            "purchasing_power_proxy": dist.get("purchasing_power_proxy", 50),
            "purchasing_power_confidence": dist.get("purchasing_power_confidence", 0.35),
            "population_year": dist.get("population_year", 2024),
            "population_source": dist.get("population_source", "HCP RGPH 2024"),
            "medical_facilities_count": total,
            "facilities_per_100k": round(per_100k, 1),
            **cats,
            "public_primary_care_count": int(public.get("public_primary_care_count", 0)),
            "public_hospital_count": int(public.get("public_hospital_count", 0)),
            "average_osm_confidence": round(float(local_confidence), 3),
            "nearest_hospital_km": round(nearest_hospital_km, 2),
        })

    df = pd.DataFrame(rows)

    df["undersupply_index"] = round(normalize_0_100(100 - df["facilities_per_100k"]), 1)

    demand = (
        0.55 * normalize_0_100(df["population_est"])
        + 0.45 * normalize_0_100(df["population_density"])
    )
    undersupply = df["undersupply_index"]
    purchasing_raw = normalize_0_100(df["purchasing_power_proxy"].fillna(50))
    purchasing_reliability = df["purchasing_power_confidence"].fillna(0.35).clip(0, 1)
    purchasing_power = 50 + (purchasing_raw - 50) * purchasing_reliability
    accessibility = normalize_0_100(100 - df["nearest_hospital_km"].clip(0, 20))
    low_competition = normalize_0_100(100 - df["medical_facilities_count"])
    data_confidence = (
        35
        + df["average_osm_confidence"].clip(0, 1) * 30
        + 15
    ).clip(0, 100)

    df["demand_index"] = round(demand, 1)
    df["accessibility_index"] = round(accessibility, 1)
    df["low_competition_index"] = round(low_competition, 1)
    df["data_confidence_score"] = round(data_confidence, 1)

    df["investment_score"] = round(
        0.25 * demand +
        0.25 * undersupply +
        0.10 * purchasing_power +
        0.10 * accessibility +
        0.10 * low_competition +
        0.20 * data_confidence,
        1,
    )

    return df


def compute_specialty_supply(
    facilities: pd.DataFrame,
    districts: pd.DataFrame,
    official_public: pd.DataFrame | None = None,
) -> pd.DataFrame:
    official_public = official_public if official_public is not None else pd.DataFrame()
    official_lookup = (
        official_public.set_index("area_name").to_dict("index")
        if not official_public.empty
        else {}
    )
    confidence = pd.to_numeric(facilities.get("confidence_score"), errors="coerce")
    global_osm_confidence = float(confidence.mean()) if confidence.notna().any() else 0.65
    rows = []

    for _, dist in districts.iterrows():
        area_name = dist["area_name"]
        pop = dist.get("population_est", 0)
        local = facilities[facilities["district"] == area_name]

        for cat in CATEGORIES:
            local_category = local[local["category"] == cat]
            count = len(local_category)
            per_100k = (count / pop * 100_000) if pop > 0 else 0
            pressure = per_100k / COMPETITION_BENCHMARKS_PER_100K[cat] * 100
            if pressure <= 50:
                comp, opp = "low", "high"
            elif pressure <= 100:
                comp, opp = "medium", "medium"
            elif pressure <= 150:
                comp, opp = "high", "low"
            else:
                comp, opp = "saturated", "low"

            local_confidence = pd.to_numeric(
                local_category.get("confidence_score"), errors="coerce"
            ).mean()
            if pd.isna(local_confidence):
                local_confidence = global_osm_confidence
            official_bonus = 15 if cat in {"hospital", "health_center"} else 0
            data_confidence = min(
                95.0,
                max(
                    25.0,
                    float(local_confidence) * 100 * 0.45
                    + CATEGORY_COMPLETENESS[cat] * 0.40
                    + official_bonus,
                ),
            )
            public = official_lookup.get(area_name, {})
            official_count = (
                int(public.get("public_hospital_count", 0))
                if cat == "hospital"
                else int(public.get("public_primary_care_count", 0))
                if cat == "health_center"
                else 0
            )

            rows.append({
                "area_name": area_name,
                "specialty": cat,
                "providers_count": count,
                "providers_per_100k": round(per_100k, 1),
                "competition_pressure": round(min(200.0, pressure), 1),
                "competition_level": comp,
                "opportunity_level": opp,
                "data_confidence_score": round(data_confidence, 1),
                "official_public_count": official_count,
                "notes": "OSM non exhaustif; population HCP 2024; offre publique MSPS 2024",
            })

    return pd.DataFrame(rows)


def generate_opportunities(area_df: pd.DataFrame, specialty_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for category_name, config in INVESTMENT_CATEGORIES.items():
        scores = compute_opportunity_scores(area_df, specialty_df, category_name)
        for _, row in scores.iterrows():
            rows.append(
                {
                    "area_name": row["area_name"],
                    "category": category_name,
                    "specialty": config["data_category"],
                    "providers_count": int(row["providers_count"]),
                    "providers_per_100k": round(float(row["providers_per_100k"]), 1),
                    "investment_score": round(float(row["investment_readiness_score"]), 1),
                    "risk_score": round(float(row["risk_score"]), 1),
                    "supply_gap": round(float(row["supply_gap"]), 1),
                    "competition_level": row["competition_level"],
                    "data_confidence_score": round(float(row["data_confidence"]), 1),
                    "reason": (
                        f"HCP 2024 population {int(row['population_est']):,}; "
                        f"OSM providers {int(row['providers_count'])}; "
                        f"confidence {float(row['data_confidence']):.1f}/100"
                    ),
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["category", "investment_score"], ascending=[True, False]
    )


def main():
    log.info("=== Step 5: Compute investment scores ===")

    if not FACILITIES_CSV.exists():
        log.error("Facilities file not found: %s. Run previous steps first.", FACILITIES_CSV)
        return
    if not DISTRICTS_CSV.exists():
        log.error("Districts file not found: %s. Run 02_collect_official_sources.py first.", DISTRICTS_CSV)
        return

    facilities = pd.read_csv(FACILITIES_CSV, encoding="utf-8-sig")
    districts = pd.read_csv(DISTRICTS_CSV, encoding="utf-8-sig")
    official_public = (
        pd.read_csv(OFFICIAL_PUBLIC_CSV, encoding="utf-8-sig")
        if OFFICIAL_PUBLIC_CSV.exists()
        else pd.DataFrame()
    )

    log.info("Computing area indicators ...")
    area_df = compute_area_indicators(facilities, districts, official_public)
    area_df.to_csv(AREA_INDICATORS_CSV, index=False, encoding="utf-8-sig")
    log.info("Saved area indicators to %s", AREA_INDICATORS_CSV)

    log.info("Computing specialty supply ...")
    spec_df = compute_specialty_supply(facilities, districts, official_public)
    spec_df.to_csv(SPECIALTY_SUPPLY_CSV, index=False, encoding="utf-8-sig")
    log.info("Saved specialty supply to %s", SPECIALTY_SUPPLY_CSV)

    log.info("Generating investment opportunities ...")
    OPPORTUNITIES_CSV.parent.mkdir(parents=True, exist_ok=True)
    opp_df = generate_opportunities(area_df, spec_df)
    opp_df.to_csv(OPPORTUNITIES_CSV, index=False, encoding="utf-8-sig")
    log.info("Saved %d opportunities to %s", len(opp_df), OPPORTUNITIES_CSV)

    log.info("\nTop 10 investment opportunities:")
    for _, row in opp_df.head(10).iterrows():
        log.info("  %-20s %-15s Score: %.1f", row["area_name"], row["specialty"], row["investment_score"])


if __name__ == "__main__":
    main()
