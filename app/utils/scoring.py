"""Scoring engine: investment readiness, risk, competition, and opportunity models.

Investment Readiness Score:
  0.30 * DemandIndex + 0.25 * SupplyGapIndex + 0.15 * PurchasingPowerProxy
  + 0.10 * AccessibilityIndex + 0.10 * LowCompetitionIndex + 0.10 * DataConfidence

Risk Score:
  0.35 * CompetitionRisk + 0.25 * DataUncertaintyRisk
  + 0.20 * LowDemandRisk + 0.20 * AccessibilityRisk

Competition pressure: 0-50 Low, 51-100 Medium, 101-150 High, >150 Saturated
"""

import numpy as np
import pandas as pd

INVESTMENT_CATEGORIES = {
    "Pharmacy": {
        "data_category": "pharmacy",
        "competition_radius_km": 0.5,
        "demand_population_weight": 0.45,
        # Pharmacy: population density, nearest pharmacy distance, nearby doctors, walkability
        "weights": {"demand": 0.25, "supply_gap": 0.30, "purchasing_power": 0.10,
                    "accessibility": 0.10, "low_competition": 0.15, "data_confidence": 0.10},
    },
    "Medical Analysis Laboratory": {
        "data_category": "laboratory",
        "competition_radius_km": 3.0,
        "demand_population_weight": 0.65,
        # Lab: nearby doctors/clinics, low lab competition, accessibility
        "weights": {"demand": 0.30, "supply_gap": 0.25, "purchasing_power": 0.15,
                    "accessibility": 0.10, "low_competition": 0.10, "data_confidence": 0.10},
    },
    "Radiology Center": {
        "data_category": "radiology",
        "competition_radius_km": 3.0,
        "demand_population_weight": 0.70,
        # Radiology: nearby specialists/clinics, purchasing power, low competition
        "weights": {"demand": 0.20, "supply_gap": 0.30, "purchasing_power": 0.20,
                    "accessibility": 0.10, "low_competition": 0.10, "data_confidence": 0.10},
    },
    "Dental Clinic": {
        "data_category": "dentist",
        "competition_radius_km": 1.0,
        "demand_population_weight": 0.55,
        "weights": {"demand": 0.25, "supply_gap": 0.20, "purchasing_power": 0.15,
                    "accessibility": 0.10, "low_competition": 0.15, "data_confidence": 0.15},
    },
    "Veterinary Clinic": {
        "data_category": "veterinary",
        "competition_radius_km": 2.0,
        "demand_population_weight": 0.65,
        "weights": {"demand": 0.20, "supply_gap": 0.30, "purchasing_power": 0.20,
                    "accessibility": 0.10, "low_competition": 0.10, "data_confidence": 0.10},
    },
    "General Doctor Cabinet": {
        "data_category": "doctor",
        "competition_radius_km": 1.0,
        "demand_population_weight": 0.55,
        "weights": {"demand": 0.30, "supply_gap": 0.25, "purchasing_power": 0.10,
                    "accessibility": 0.15, "low_competition": 0.10, "data_confidence": 0.10},
    },
    "Pediatric Cabinet": {
        "data_category": "doctor",
        "competition_radius_km": 2.0,
        "demand_population_weight": 0.65,
        "weights": {"demand": 0.35, "supply_gap": 0.20, "purchasing_power": 0.15,
                    "accessibility": 0.10, "low_competition": 0.10, "data_confidence": 0.10},
    },
    "Dermatology Cabinet": {
        "data_category": "doctor",
        "competition_radius_km": 3.0,
        "demand_population_weight": 0.55,
        "weights": {"demand": 0.20, "supply_gap": 0.25, "purchasing_power": 0.25,
                    "accessibility": 0.10, "low_competition": 0.10, "data_confidence": 0.10},
    },
    "Physiotherapy Center": {
        "data_category": "health_center",
        "competition_radius_km": 2.0,
        "demand_population_weight": 0.60,
        "weights": {"demand": 0.30, "supply_gap": 0.25, "purchasing_power": 0.15,
                    "accessibility": 0.10, "low_competition": 0.10, "data_confidence": 0.10},
    },
    "Small Private Clinic": {
        "data_category": "clinic",
        "competition_radius_km": 5.0,
        "demand_population_weight": 0.75,
        "weights": {"demand": 0.25, "supply_gap": 0.20, "purchasing_power": 0.25,
                    "accessibility": 0.10, "low_competition": 0.10, "data_confidence": 0.10},
    },
    "Emergency Care Center": {
        "data_category": "hospital",
        "competition_radius_km": 5.0,
        "demand_population_weight": 0.75,
        "weights": {"demand": 0.35, "supply_gap": 0.25, "purchasing_power": 0.05,
                    "accessibility": 0.15, "low_competition": 0.10, "data_confidence": 0.10},
    },
}

# Confidence score ranges by source type
SOURCE_CONFIDENCE = {
    "official": (0.90, 1.00),
    "institutional": (0.80, 0.90),
    "osm": (0.65, 0.80),
    "google_places": (0.70, 0.85),
    "manual_verified": (0.85, 1.00),
    "unknown": (0.30, 0.60),
}

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

# Demand is not interchangeable across medical activities. These profiles use
# only signals available in the versioned HCP, MSPS and OSM datasets.
DEMAND_PROFILES = {
    "Pharmacy": {"population": 0.30, "density": 0.35, "referrals": 0.20, "public_primary": 0.15},
    "Medical Analysis Laboratory": {
        "population": 0.25, "referrals": 0.45, "public_primary": 0.15, "public_hospitals": 0.15,
    },
    "Radiology Center": {
        "population": 0.20, "clinical_ecosystem": 0.45, "public_hospitals": 0.25,
        "purchasing_fit": 0.10,
    },
    "Dental Clinic": {"population": 0.35, "density": 0.20, "purchasing_fit": 0.45},
    "Veterinary Clinic": {
        "population": 0.15, "area": 0.25, "purchasing_fit": 0.50, "low_density": 0.10,
    },
    "General Doctor Cabinet": {
        "population": 0.45, "density": 0.25, "public_primary_gap": 0.30,
    },
    "Pediatric Cabinet": {
        "population": 0.45, "density": 0.20, "public_primary": 0.25,
        "public_primary_gap": 0.10,
    },
    "Dermatology Cabinet": {
        "purchasing_fit": 0.60, "referrals": 0.20, "population": 0.10, "density": 0.10,
    },
    "Physiotherapy Center": {
        "population": 0.25, "public_hospitals": 0.30, "clinical_ecosystem": 0.20,
        "purchasing_fit": 0.15, "public_primary": 0.10,
    },
    "Small Private Clinic": {
        "population": 0.35, "referrals": 0.25, "purchasing_fit": 0.20,
        "public_primary": 0.10, "public_hospital_gap": 0.10,
    },
    "Emergency Care Center": {
        "population": 0.35, "density": 0.20, "public_hospital_gap": 0.30,
        "public_primary": 0.15,
    },
}


def _normalize_series(s: pd.Series) -> pd.Series:
    mn, mx = s.min(), s.max()
    if mx == mn:
        return pd.Series(50.0, index=s.index)
    return ((s - mn) / (mx - mn)) * 100


def _numeric_column(areas: pd.DataFrame, name: str) -> pd.Series:
    source = areas.get(name, pd.Series(0.0, index=areas.index))
    return pd.to_numeric(source, errors="coerce").fillna(0.0)


def _demand_index(areas: pd.DataFrame, investment_type: str, cfg: dict) -> pd.Series:
    population = _numeric_column(areas, "population_est")
    density = _numeric_column(areas, "population_density")
    purchasing_raw = _normalize_series(_numeric_column(areas, "purchasing_power_proxy"))
    purchasing_reliability = _numeric_column(areas, "purchasing_power_confidence").clip(0, 1)
    purchasing_fit = 50 + (purchasing_raw - 50) * purchasing_reliability
    public_primary = _numeric_column(areas, "public_primary_care_count")
    public_hospitals = _numeric_column(areas, "public_hospital_count")
    doctors = _numeric_column(areas, "doctor_count")
    clinics = _numeric_column(areas, "clinic_count")
    hospitals = _numeric_column(areas, "hospital_count")
    safe_population = population.replace(0, np.nan)

    signals = {
        "population": _normalize_series(population),
        "density": _normalize_series(density),
        "low_density": 100 - _normalize_series(density),
        "area": _normalize_series(_numeric_column(areas, "area_km2")),
        "purchasing_fit": purchasing_fit,
        "public_primary": _normalize_series(public_primary),
        "public_hospitals": _normalize_series(public_hospitals),
        "public_primary_gap": 100 - _normalize_series(public_primary / safe_population * 100_000),
        "public_hospital_gap": 100 - _normalize_series(public_hospitals / safe_population * 100_000),
        "referrals": _normalize_series(doctors + clinics + public_primary),
        "clinical_ecosystem": _normalize_series(doctors + clinics + hospitals),
    }
    profile = DEMAND_PROFILES.get(investment_type)
    if not profile:
        population_weight = float(cfg.get("demand_population_weight", 0.55))
        return (
            population_weight * signals["population"]
            + (1 - population_weight) * signals["density"]
        ).round(1)
    demand = pd.Series(0.0, index=areas.index)
    for signal_name, weight in profile.items():
        demand += signals[signal_name] * weight
    return demand.round(1)


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))


def competition_level_label(score: float) -> str:
    if score <= 50:
        return "Low"
    if score <= 100:
        return "Medium"
    if score <= 150:
        return "High"
    return "Saturated"


def compute_opportunity_scores(areas: pd.DataFrame, spec: pd.DataFrame,
                                investment_type: str) -> pd.DataFrame:
    cfg = INVESTMENT_CATEGORIES.get(investment_type)
    if cfg is None or areas.empty:
        return pd.DataFrame()

    w = cfg["weights"]
    data_cat = cfg["data_category"]
    cat_count_col = f"{data_cat}_count"

    result = areas[["area_name", "population_est", "population_density",
                     "medical_facilities_count"]].copy()

    cat_spec = pd.DataFrame()
    if not spec.empty and data_cat in spec.get("specialty", pd.Series(dtype=str)).values:
        wanted = [
            column for column in (
                "area_name", "providers_count", "providers_per_100k",
                "data_confidence_score", "official_public_count",
            )
            if column in spec.columns
        ]
        cat_spec = spec[spec["specialty"] == data_cat][wanted]
        result = result.merge(cat_spec, on="area_name", how="left")

    pop = result["population_est"].replace(0, np.nan)
    if "providers_count" not in result:
        result["providers_count"] = areas.get(cat_count_col, pd.Series(0, index=areas.index)).values
    result["providers_count"] = result["providers_count"].fillna(0).astype(int)
    if "providers_per_100k" not in result:
        result["providers_per_100k"] = result["providers_count"] / pop * 100_000
    result["providers_per_100k"] = result["providers_per_100k"].fillna(0.0)

    result["demand"] = _demand_index(areas, investment_type, cfg).values

    benchmark = COMPETITION_BENCHMARKS_PER_100K[data_cat]
    result["competition_pressure"] = (
        result["providers_per_100k"] / benchmark * 100
    ).clip(0, 200).round(1)
    result["supply_gap"] = (100 - result["competition_pressure"]).clip(0, 100).round(1)

    # Use real purchasing power proxy if available
    if "purchasing_power_proxy" in areas.columns:
        raw_purchasing_power = _normalize_series(areas["purchasing_power_proxy"].fillna(50))
        reliability = areas.get(
            "purchasing_power_confidence", pd.Series(0.35, index=areas.index)
        ).fillna(0.35).clip(0, 1)
        result["purchasing_power"] = 50 + (raw_purchasing_power - 50) * reliability
    else:
        result["purchasing_power"] = 50.0

    if "nearest_hospital_km" in areas.columns:
        result["accessibility"] = _normalize_series(
            100 - areas["nearest_hospital_km"].clip(0, 20).fillna(10)
        )
    else:
        result["accessibility"] = 50.0

    result["low_competition"] = 100 - _normalize_series(result["providers_count"].fillna(0))

    if "data_confidence_score" in result:
        result["data_confidence"] = result["data_confidence_score"].fillna(45).clip(0, 100)
    else:
        result["data_confidence"] = areas.get(
            "data_confidence_score", pd.Series(45.0, index=areas.index)
        ).fillna(45).clip(0, 100)

    if "official_public_count" not in result:
        result["official_public_count"] = 0
    evidence_count = result[["providers_count", "official_public_count"]].max(axis=1)
    local_evidence_factor = 0.60 + 0.40 * (evidence_count / 3).clip(0, 1)
    result["data_confidence"] = (result["data_confidence"] * local_evidence_factor).round(1)

    # A sparse inventory cannot prove that competition is absent. Positive
    # opportunity signals are shrunk toward neutral according to local evidence;
    # observed saturation (scores below 50) is retained as a credible lower bound.
    reliability = result["data_confidence"] / 100
    result["supply_gap"] = result["supply_gap"].where(
        result["supply_gap"] <= 50,
        50 + (result["supply_gap"] - 50) * reliability,
    ).round(1)
    result["low_competition"] = result["low_competition"].where(
        result["low_competition"] <= 50,
        50 + (result["low_competition"] - 50) * reliability,
    ).round(1)

    result["investment_readiness_score"] = (
        w["demand"] * result["demand"]
        + w["supply_gap"] * result["supply_gap"]
        + w["purchasing_power"] * result["purchasing_power"]
        + w["accessibility"] * result["accessibility"]
        + w["low_competition"] * result["low_competition"]
        + w["data_confidence"] * result["data_confidence"]
    ).round(1)

    result["risk_score"] = _compute_risk(result)
    result["competition_level"] = result["competition_pressure"].apply(competition_level_label)
    result = result.sort_values("investment_readiness_score", ascending=False)
    return result


def _compute_risk(result: pd.DataFrame) -> pd.Series:
    competition_risk = (100 - result["low_competition"]).clip(0, 100)
    data_uncertainty = (100 - result["data_confidence"]).clip(0, 100)
    low_demand_risk = (100 - result["demand"]).clip(0, 100)
    accessibility_risk = (100 - result["accessibility"]).clip(0, 100)
    weighted = (
        0.25 * competition_risk
        + 0.40 * data_uncertainty
        + 0.15 * low_demand_risk
        + 0.20 * accessibility_risk
    )
    # Sparse inventories must not look low-risk merely because few competitors
    # were observed. Uncertainty therefore creates a category-specific floor.
    return pd.concat([weighted, data_uncertainty * 0.75], axis=1).max(axis=1).round(1)


def compute_competition_radius(facilities: pd.DataFrame, center_lat: float,
                                center_lon: float, category: str | None = None
                                ) -> dict[str, dict]:
    radii = {"500m": 0.5, "1 km": 1.0, "3 km": 3.0, "5 km": 5.0}
    geo = facilities.dropna(subset=["lat", "lon"])
    if geo.empty:
        return {r: {"same_category": 0, "all_facilities": 0} for r in radii}

    dists = geo.apply(
        lambda row: haversine_km(center_lat, center_lon, row["lat"], row["lon"]),
        axis=1,
    )
    result = {}
    for label, r_km in radii.items():
        within = geo[dists <= r_km]
        same = within[within["category"] == category] if category else within
        result[label] = {"same_category": len(same), "all_facilities": len(within)}
    return result


def compute_saturation_score(comp_data: dict, category: str | None = None) -> float:
    thresholds = {
        "pharmacy": 15, "doctor": 8, "dentist": 6, "laboratory": 5,
        "radiology": 4, "clinic": 6, "hospital": 3, "health_center": 4,
        "veterinary": 4,
    }
    threshold = thresholds.get(category, 8)
    count_1km = comp_data.get("1 km", {}).get("same_category", 0)
    return min(100.0, round(count_1km / threshold * 100, 1))


def get_nearest_competitors(facilities: pd.DataFrame, center_lat: float,
                             center_lon: float, category: str,
                             n: int = 10) -> pd.DataFrame:
    """Return the nearest N competitors of the same category."""
    geo = facilities[
        (facilities["category"] == category) &
        facilities["lat"].notna() & facilities["lon"].notna()
    ].copy()
    if geo.empty:
        return pd.DataFrame()

    geo["distance_km"] = geo.apply(
        lambda r: haversine_km(center_lat, center_lon, r["lat"], r["lon"]), axis=1
    )
    return geo.nsmallest(n, "distance_km")[
        ["name", "category", "district", "distance_km", "confidence_score", "source"]
    ]


def best_categories_for_zone(zone_name: str, areas: pd.DataFrame,
                              spec: pd.DataFrame) -> list[dict]:
    results = []
    for inv_name in INVESTMENT_CATEGORIES:
        scores = compute_opportunity_scores(areas, spec, inv_name)
        row = scores[scores["area_name"] == zone_name]
        if row.empty:
            continue
        r = row.iloc[0]
        results.append({
            "category": inv_name,
            "investment_readiness_score": r["investment_readiness_score"],
            "risk_score": r["risk_score"],
            "competition_level": r["competition_level"],
            "supply_gap": round(r["supply_gap"], 1),
            "recommended": r["investment_readiness_score"] >= 50 and r["risk_score"] < 65,
        })
    results.sort(key=lambda x: x["investment_readiness_score"], reverse=True)
    return results
