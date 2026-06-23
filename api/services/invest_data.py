"""Data and scoring service used by the web API."""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "app"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
MANUAL_DIR = DATA_DIR / "manual"
PROCESSED_DIR = DATA_DIR / "processed"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from utils.scoring import INVESTMENT_CATEGORIES, compute_opportunity_scores  # noqa: E402
from api.services.rag import hybrid_search, source_cards_from_contexts  # noqa: E402
from api.services.llm import generate_answer, selected_model  # noqa: E402
from api.services.llm.prompts import GREETING_RESPONSE  # noqa: E402
from data_sources.sectors import SECTORS  # noqa: E402
from data_sources.zone_boundaries import assign_zone, load_zone_boundaries  # noqa: E402

import logging  # noqa: E402

log = logging.getLogger("invest_search")


SOURCE_CARDS = [
    {
        "title": "HCP RGPH 2024",
        "subtitle": "Population officielle et ménages des 16 arrondissements",
        "kind": "demographics",
        "confidence": 0.98,
        "url": "https://www.hcp.ma/file/242341/",
    },
    {
        "title": "OpenStreetMap",
        "subtitle": "Infrastructure urbaine et points sectoriels locaux",
        "kind": "poi",
        "confidence": 0.7,
        "url": "https://www.openstreetmap.org/",
    },
    {
        "title": "MSPS 2024",
        "subtitle": "Centres de soins primaires et hôpitaux publics par arrondissement",
        "kind": "official",
        "confidence": 0.95,
        "url": "https://data.gov.ma/data/fr/organization/ministere-de-la-sante-et-de-la-protection-sociale",
    },
]

CATEGORY_DISPLAY_FR = {
    "Pharmacy": "pharmacie",
    "Medical Analysis Laboratory": "laboratoire d'analyses médicales",
    "Radiology Center": "centre de radiologie",
    "Dental Clinic": "clinique dentaire",
    "Veterinary Clinic": "clinique vétérinaire",
    "General Doctor Cabinet": "cabinet de médecine générale",
    "Pediatric Cabinet": "cabinet pédiatrique",
    "Dermatology Cabinet": "cabinet de dermatologie",
    "Physiotherapy Center": "centre de physiothérapie",
    "Small Private Clinic": "clinique privée",
    "Emergency Care Center": "centre de soins d'urgence",
}

SECTOR_INTENT_ALIASES = {
    "restaurant": "food",
    "restaurants": "food",
    "cafe": "food",
    "cafes": "food",
    "coffee": "food",
    "fast food": "food",
    "snack": "food",
    "restauration": "food",
    "food": "food",
    "magasin": "retail",
    "magasins": "retail",
    "commerce": "retail",
    "retail": "retail",
    "boutique": "retail",
    "boutiques": "retail",
    "supermarche": "retail",
    "supermarket": "retail",
    "shop": "retail",
    "ecole": "education",
    "ecoles": "education",
    "school": "education",
    "education": "education",
    "creche": "education",
    "universite": "education",
    "university": "education",
    "college": "education",
    "coiffure": "wellness",
    "coiffeur": "wellness",
    "beaute": "wellness",
    "bien etre": "wellness",
    "fitness": "wellness",
    "gym": "wellness",
    "salle de sport": "wellness",
    "spa": "wellness",
    "hammam": "wellness",
    "wellness": "wellness",
}


def _read_csv(name: str) -> pd.DataFrame:
    path = PROCESSED_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def _facilities() -> pd.DataFrame:
    return _read_csv("medical_facilities_clean.csv")


def _areas() -> pd.DataFrame:
    return _read_csv("area_indicators.csv")


def _specialty() -> pd.DataFrame:
    return _read_csv("specialty_supply.csv")


def _sector_supply() -> pd.DataFrame:
    return _read_csv("sector_supply.csv")


def _subcategory_supply() -> pd.DataFrame:
    return _read_csv("subcategory_supply.csv")


def _raw_csv(name: str) -> pd.DataFrame:
    path = RAW_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def _manual_csv(name: str) -> pd.DataFrame:
    path = MANUAL_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def _normalize_series_0_100(series: pd.Series, invert: bool = False) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0)
    if numeric.empty:
        return numeric
    min_value = numeric.min()
    max_value = numeric.max()
    if max_value == min_value:
        score = pd.Series(50.0, index=numeric.index)
    else:
        score = (numeric - min_value) / (max_value - min_value) * 100
    if invert:
        score = 100 - score
    return score.round(1)


def _multisector_facilities() -> pd.DataFrame:
    df = _raw_csv("osm_casablanca_multisector.csv")
    if df.empty:
        frames = [
            _raw_csv(f"osm_casablanca_{sector_key}.csv")
            for sector_key in SECTORS
            if sector_key != "medical"
        ]
        frames = [frame for frame in frames if not frame.empty]
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if df.empty:
        return df

    df = df.copy()
    for col in ("sector", "category", "name", "sub_category", "source_url"):
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    df["lat"] = pd.to_numeric(df.get("lat"), errors="coerce")
    df["lon"] = pd.to_numeric(df.get("lon"), errors="coerce")
    df["confidence_score"] = pd.to_numeric(df.get("confidence_score"), errors="coerce").fillna(0.55).clip(0, 1)
    df = df.dropna(subset=["lat", "lon"])

    if "district" not in df.columns or df["district"].fillna("").eq("").all():
        districts = _raw_csv("casablanca_districts.csv")
        boundaries = load_zone_boundaries()
        df["district"] = df.apply(
            lambda row: assign_zone(row["lat"], row["lon"], boundaries, districts),
            axis=1,
        )
    else:
        df["district"] = df["district"].fillna("Unknown").replace("", "Unknown")
    return df


def _official_arrondissements() -> pd.DataFrame:
    df = _manual_csv("hcp_rgph_2024_casablanca.csv")
    if df.empty:
        return pd.DataFrame(columns=["name", "name_ascii", "prefecture", "source_url"])
    return pd.DataFrame(
        {
            "name": df["official_name"],
            "name_ascii": df["area_name"],
            "prefecture": df["prefecture"],
            "source": df["source"],
            "source_url": df["source_url"],
        }
    )


def _official_arrondissement_gaps() -> list[dict]:
    official = _official_arrondissements()
    districts = _raw_csv("casablanca_districts.csv")
    if official.empty or districts.empty:
        return []
    known = {_normalize_text(name) for name in districts.get("area_name", pd.Series(dtype=str)).dropna().astype(str)}
    gaps = []
    for _, row in official.iterrows():
        ascii_name = str(row.get("name_ascii") or row.get("name") or "").strip()
        if not ascii_name:
            continue
        if _normalize_text(ascii_name) not in known:
            gaps.append(
                {
                    "name": str(row.get("name") or ascii_name),
                    "name_ascii": ascii_name,
                    "prefecture": str(row.get("prefecture", "")),
                    "source": str(row.get("source", "wikipedia")),
                    "source_url": str(row.get("source_url", "")),
                }
            )
    return gaps


def _coverage_gap_from_question(question: str) -> dict | None:
    normalized = f" {_normalize_text(question)} "
    for gap in _official_arrondissement_gaps():
        aliases = {
            _normalize_text(str(gap.get("name", ""))).strip(),
            _normalize_text(str(gap.get("name_ascii", ""))).strip(),
        }
        for alias in aliases:
            if alias and f" {alias} " in normalized:
                return gap
    return None


def get_sector_summary() -> dict:
    df = _multisector_facilities()
    gaps = _official_arrondissement_gaps()
    sectors = []
    for sector_key, sector in SECTORS.items():
        if sector_key == "medical":
            continue
        sector_df = df[df["sector"] == sector_key] if not df.empty else pd.DataFrame()
        top_categories = []
        if not sector_df.empty:
            top_categories = [
                {"category": str(category), "count": int(count)}
                for category, count in sector_df["category"].value_counts().head(5).items()
            ]
        unknown_count = int((sector_df.get("district", pd.Series(dtype=str)) == "Unknown").sum()) if not sector_df.empty else 0
        sectors.append(
            {
                "key": sector_key,
                "label_fr": sector.label_fr,
                "poi_count": int(len(sector_df)),
                "assigned_count": int(len(sector_df) - unknown_count),
                "unknown_count": unknown_count,
                "confidence": sector.confidence,
                "top_categories": top_categories,
            }
        )
    return {
        "total_pois": int(len(df)),
        "geolocated_pois": int(df.dropna(subset=["lat", "lon"]).shape[0]) if not df.empty else 0,
        "sectors": sectors,
        "official_arrondissement_count": int(len(_official_arrondissements())),
        "coverage_gaps": gaps,
    }


def _sector_source_cards(sector_key: str) -> list[dict]:
    summary = get_sector_summary()
    sector_info = next((item for item in summary["sectors"] if item["key"] == sector_key), {})
    return [
        {
            "title": "OpenStreetMap multi-sector",
            "subtitle": "POIs food, retail, education et wellness collectés par Overpass",
            "kind": "poi",
            "metric": f"{sector_info.get('poi_count', 0):,} pts",
            "confidence": SECTORS[sector_key].confidence,
        },
        {
            "title": "sector_supply.csv",
            "subtitle": "Table persistée par secteur, zone, concurrence et supply gap",
            "kind": "scoring",
            "metric": "sector_weights_v1",
            "confidence": 0.76,
        },
        {
            "title": "Zones Casablanca",
            "subtitle": "Assignation par polygones OSM + fallback districts",
            "kind": "geography",
            "metric": f"{sector_info.get('assigned_count', 0):,} assignés",
            "confidence": 0.72,
        },
        {
            "title": "Taxonomie HCP RGPH 2024",
            "subtitle": "Contrôle officiel des 16 arrondissements couverts",
            "kind": "official",
            "metric": f"{len(summary['coverage_gaps'])} gaps",
            "confidence": 0.78,
        },
    ]


def get_sector_opportunities(sector: str = "food", subcategory: str | None = None, limit: int = 12) -> list[dict]:
    if sector not in SECTORS or sector == "medical":
        return []
    supply = _subcategory_supply() if subcategory else _sector_supply()
    if supply.empty:
        return []

    ranked = supply[supply["sector"] == sector].copy()
    if subcategory:
        ranked = ranked[ranked["subcategory"] == subcategory]
    if ranked.empty:
        return []
    ranked["sector_opportunity_score"] = pd.to_numeric(
        ranked["sector_opportunity_score"], errors="coerce"
    ).fillna(0)
    ranked = ranked.sort_values("sector_opportunity_score", ascending=False)

    rows = []
    for _, row in ranked.head(limit).iterrows():
        rows.append(
            {
                "zone": row.get("area_name", ""),
                "category": subcategory or sector,
                "sector": sector,
                "subcategory": subcategory,
                "subcategory_label": row.get("subcategory_label_fr", "") if subcategory else "",
                "score": _safe_float(row.get("sector_opportunity_score")),
                "risk": _safe_float(row.get("risk_score")),
                "supply_gap": _safe_float(row.get("supply_gap")),
                "competition_level": row.get("competition_level", "Non disponible"),
                "providers": _safe_int(row.get("providers_count")),
                "providers_per_100k": _safe_float(row.get("providers_per_100k")),
                "population": _safe_int(row.get("population_est")),
                "density": _safe_float(row.get("population_density")),
                "confidence": _safe_float(row.get("average_confidence")),
                "scoring_status": row.get("scoring_status", "scored"),
                "weights_version": row.get("weights_version", "sector_weights_v1"),
                "assigned_pois_subcategory": _safe_int(row.get("assigned_pois_subcategory")),
                "total_pois_subcategory": _safe_int(row.get("total_pois_subcategory")),
            }
        )
    return rows


def get_sector_facility_points(
    sector: str = "food",
    subcategory: str | None = None,
    limit: int = 300,
) -> list[dict]:
    if sector not in SECTORS or sector == "medical":
        return []
    df = _multisector_facilities()
    if df.empty:
        return []
    clean = df[df["sector"] == sector]
    if subcategory:
        clean = clean[clean["category"] == subcategory]
    clean = clean.dropna(subset=["lat", "lon"]).head(limit)
    points = []
    for _, row in clean.iterrows():
        points.append(
            {
                "name": row.get("name") or "Sans nom",
                "sector": row.get("sector", sector),
                "category": row.get("category", "unknown"),
                "district": row.get("district", "Unknown"),
                "lat": float(row.get("lat")),
                "lon": float(row.get("lon")),
                "confidence": _safe_float(row.get("confidence_score"), SECTORS[sector].confidence),
                "source_url": row.get("source_url", ""),
            }
        )
    return points


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return round(float(value), 1)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _category_or_default(category: str) -> str:
    if category in INVESTMENT_CATEGORIES:
        return category
    aliases = {
        "clinic": "Small Private Clinic",
        "clinique": "Small Private Clinic",
        "clinique de jour": "Small Private Clinic",
        "pharmacy": "Pharmacy",
        "pharmacie": "Pharmacy",
        "laboratory": "Medical Analysis Laboratory",
        "laboratoire": "Medical Analysis Laboratory",
        "radiology": "Radiology Center",
        "radiologie": "Radiology Center",
        "dentist": "Dental Clinic",
        "dentiste": "Dental Clinic",
        "dentaire": "Dental Clinic",
        "veterinary": "Veterinary Clinic",
        "veterinaire": "Veterinary Clinic",
        "vétérinaire": "Veterinary Clinic",
    }
    return aliases.get(category.lower().strip(), "Small Private Clinic")


# Ordered longest/most-specific first so multi-word phrases win over short typo stems.
# NOTE: bare "analyse" is intentionally absent — it must not force a laboratory.
_CATEGORY_INTENT_ALIASES = {
    "clinique de jour": "Small Private Clinic",
    "analyses medicales": "Medical Analysis Laboratory",
    "analyse medicale": "Medical Analysis Laboratory",
    "analyses biologiques": "Medical Analysis Laboratory",
    "analyse biologique": "Medical Analysis Laboratory",
    "laboratoire": "Medical Analysis Laboratory",
    "laboratory": "Medical Analysis Laboratory",
    "biologie": "Medical Analysis Laboratory",
    "labo": "Medical Analysis Laboratory",
    "pharmacie": "Pharmacy",
    "pharmacy": "Pharmacy",
    "pharmaci": "Pharmacy",
    "pharma": "Pharmacy",
    "radiologie": "Radiology Center",
    "radiology": "Radiology Center",
    "imagerie": "Radiology Center",
    "radio": "Radiology Center",
    "dentaire": "Dental Clinic",
    "dentiste": "Dental Clinic",
    "dentist": "Dental Clinic",
    "dental": "Dental Clinic",
    "veterinaire": "Veterinary Clinic",
    "veterinary": "Veterinary Clinic",
    "veto": "Veterinary Clinic",
    "pediat": "Pediatric Cabinet",
    "dermato": "Dermatology Cabinet",
    "physio": "Physiotherapy Center",
    "urgence": "Emergency Care Center",
    "emergency": "Emergency Care Center",
    "clinique": "Small Private Clinic",
    "clinic": "Small Private Clinic",
}


def _detected_category(question: str) -> str | None:
    """Return the investment category implied by the question, or None if undetectable."""
    text = _normalize_text(question)
    for keyword, inferred_category in _CATEGORY_INTENT_ALIASES.items():
        if keyword in text:
            return inferred_category
    return None


def _category_from_question(question: str, fallback: str) -> str:
    return _detected_category(question) or fallback


def _sector_category_from_question(question: str) -> tuple[str, str] | None:
    """Detect a supported non-medical business type using longest alias match."""
    text = _normalize_text(question)
    padded = f" {text} "
    candidates: list[tuple[str, str, str]] = []
    for sector_key, sector in SECTORS.items():
        if sector_key == "medical":
            continue
        for subcategory, aliases in sector.category_intent_aliases.items():
            for alias in aliases:
                normalized_alias = _normalize_text(alias).strip()
                if normalized_alias:
                    candidates.append((normalized_alias, sector_key, subcategory))
    for alias, sector_key, subcategory in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
        if f" {alias} " in padded:
            return sector_key, subcategory
    return None


def _sector_from_question(question: str) -> str | None:
    detected = _sector_category_from_question(question)
    if detected:
        return detected[0]
    text = _normalize_text(question)
    padded = f" {text} "
    for keyword, sector_key in sorted(SECTOR_INTENT_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        normalized_keyword = _normalize_text(keyword).strip()
        if normalized_keyword and f" {normalized_keyword} " in padded:
            return sector_key
    return None


def _sector_category_label(sector: str, subcategory: str | None) -> str:
    if subcategory and sector in SECTORS:
        return SECTORS[sector].category_labels_fr.get(subcategory, subcategory.replace("_", " "))
    return SECTORS[sector].label_fr if sector in SECTORS else sector


def get_market_snapshot() -> dict:
    facilities = _facilities()
    areas = _areas()
    specialty = _specialty()
    opportunities = get_opportunities("Small Private Clinic")
    top = opportunities[0] if opportunities else {}
    sector_summary = get_sector_summary()
    medical_points = len(facilities)
    multisector_points = sector_summary["total_pois"]
    total_osm_points = medical_points + multisector_points
    public_primary = _safe_int(areas.get("public_primary_care_count", pd.Series(dtype=float)).sum())
    public_hospitals = _safe_int(areas.get("public_hospital_count", pd.Series(dtype=float)).sum())

    return {
        "facility_count": medical_points,
        "district_count": areas["area_name"].nunique() if "area_name" in areas else 0,
        "unknown_district_count": int((facilities.get("district", "") == "Unknown").sum())
        if not facilities.empty
        else 0,
        "average_confidence": _safe_float(facilities.get("confidence_score", pd.Series(dtype=float)).mean(), 0.0),
        "specialty_rows": len(specialty),
        "top_recommendation": top,
        "multisector_total": multisector_points,
        "osm_total_points": total_osm_points,
        "multisector": sector_summary,
        "official_arrondissement_gaps": sector_summary["coverage_gaps"],
        "sources": [
            {
                **SOURCE_CARDS[0],
                "metric": f"{areas['area_name'].nunique()} zones" if not areas.empty else "zones",
            },
            {
                **SOURCE_CARDS[1],
                "metric": (
                    f"{_format_int(total_osm_points)} pts "
                    f"({_format_int(medical_points)} santé + {_format_int(multisector_points)} multi)"
                ),
            },
            {
                **SOURCE_CARDS[2],
                "metric": f"{public_primary} centres · {public_hospitals} hôpitaux",
            },
        ],
    }


def get_zones() -> list[dict]:
    areas = _areas()
    if areas.empty:
        return []

    rows = []
    for _, row in areas.sort_values("investment_score", ascending=False).iterrows():
        rows.append(
            {
                "name": row.get("area_name", ""),
                "population": _safe_int(row.get("population_est")),
                "density": _safe_float(row.get("population_density")),
                "facilities": _safe_int(row.get("medical_facilities_count")),
                "score": _safe_float(row.get("investment_score")),
                "supply_gap": _safe_float(row.get("undersupply_index")),
                "competition": _safe_float(row.get("low_competition_index")),
            }
        )
    return rows


def _format_int(value: float | int | None) -> str:
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def _area_row(zone: str) -> dict:
    areas = _areas()
    if areas.empty or "area_name" not in areas:
        return {}
    match = areas[areas["area_name"] == zone]
    if match.empty:
        return {}
    return match.iloc[0].to_dict()


def _zone_opex_multiplier(zone: str) -> tuple[float, str]:
    areas = _areas()
    if areas.empty or "area_name" not in areas:
        return 1.0, "multiplicateur neutre faute de donnees de zone"
    match = areas[areas["area_name"] == zone]
    if match.empty:
        return 1.0, "multiplicateur neutre faute de zone identifiee"
    row = match.iloc[0]

    rent_value = row.get("rent_commercial_med")
    if rent_value is not None and not pd.isna(rent_value):
        rent_series = pd.to_numeric(areas.get("rent_commercial_med"), errors="coerce")
        rent_score = _normalize_series_0_100(rent_series).reindex(areas.index).loc[row.name]
        multiplier = 0.85 + (float(rent_score) / 100) * 0.45
        return round(max(0.80, min(1.35, multiplier)), 2), "loyer commercial median"

    power = _safe_float(row.get("purchasing_power_proxy"), 50)
    density_series = _normalize_series_0_100(areas.get("population_density", pd.Series(dtype=float)))
    density_score = _safe_float(density_series.reindex(areas.index).loc[row.name], 50)
    multiplier = 0.82 + (power / 100) * 0.28 + (density_score / 100) * 0.14
    return round(max(0.82, min(1.30, multiplier)), 2), "proxy pouvoir d'achat + densite"


def _zone_focus(zone: str) -> dict:
    districts = _read_csv("../raw/casablanca_districts.csv")
    if districts.empty or "area_name" not in districts:
        return {"label": zone, "lat": 33.57, "lon": -7.59, "zoom": 12}
    match = districts[districts["area_name"] == zone]
    if match.empty:
        return {"label": zone, "lat": 33.57, "lon": -7.59, "zoom": 12}
    row = match.iloc[0]
    lat_min = float(row.get("lat_min", 33.54))
    lat_max = float(row.get("lat_max", 33.60))
    lon_min = float(row.get("lon_min", -7.65))
    lon_max = float(row.get("lon_max", -7.55))
    lat = (lat_min + lat_max) / 2
    lon = (lon_min + lon_max) / 2
    return {
        "label": zone,
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "zoom": 12,
        "bounds": {
            "south": lat_min,
            "north": lat_max,
            "west": lon_min,
            "east": lon_max,
        },
    }


def _population_distribution(areas: pd.DataFrame, zone: str) -> dict:
    if areas.empty:
        return {
            "total_population": 0,
            "zone_share": 0,
            "density_rank": 0,
            "population_rank": 0,
            "top_population": [],
            "top_density": [],
            "top_undersupply": [],
        }

    total_population = _safe_int(areas.get("population_est", pd.Series(dtype=float)).sum())
    areas_ranked_population = areas.sort_values("population_est", ascending=False).reset_index(drop=True)
    areas_ranked_density = areas.sort_values("population_density", ascending=False).reset_index(drop=True)
    areas_ranked_undersupply = areas.sort_values("undersupply_index", ascending=False).reset_index(drop=True)

    zone_row = areas[areas["area_name"] == zone]
    zone_population = _safe_int(zone_row.iloc[0].get("population_est")) if not zone_row.empty else 0
    zone_share = round((zone_population / total_population * 100), 1) if total_population else 0

    def rank_of(df: pd.DataFrame) -> int:
        matches = df.index[df["area_name"] == zone].tolist()
        return matches[0] + 1 if matches else 0

    def compact_rows(df: pd.DataFrame, cols: list[str]) -> list[dict]:
        rows = []
        for _, row in df.head(3).iterrows():
            item = {"area_name": row.get("area_name", "")}
            for col in cols:
                item[col] = _safe_float(row.get(col)) if "index" in col or "density" in col else _safe_int(row.get(col))
            rows.append(item)
        return rows

    return {
        "total_population": total_population,
        "zone_share": zone_share,
        "density_rank": rank_of(areas_ranked_density),
        "population_rank": rank_of(areas_ranked_population),
        "top_population": compact_rows(areas_ranked_population, ["population_est"]),
        "top_density": compact_rows(areas_ranked_density, ["population_density"]),
        "top_undersupply": compact_rows(areas_ranked_undersupply, ["undersupply_index"]),
    }


def get_opportunities(category: str = "Small Private Clinic", limit: int = 12) -> list[dict]:
    areas = _areas()
    specialty = _specialty()
    category = _category_or_default(category)
    scores = compute_opportunity_scores(areas, specialty, category)
    if scores.empty:
        return []

    rows = []
    for _, row in scores.head(limit).iterrows():
        rows.append(
            {
                "zone": row.get("area_name", ""),
                "category": category,
                "score": _safe_float(row.get("investment_readiness_score")),
                "risk": _safe_float(row.get("risk_score")),
                "supply_gap": _safe_float(row.get("supply_gap")),
                "competition_level": row.get("competition_level", "N/A"),
                "providers": _safe_int(row.get("providers_count")),
                "providers_per_100k": _safe_float(row.get("providers_per_100k")),
                "competition_pressure": _safe_float(row.get("competition_pressure")),
                "confidence": _safe_float(row.get("data_confidence")),
                "official_public_count": _safe_int(row.get("official_public_count")),
                "population": _safe_int(row.get("population_est")),
                "density": _safe_float(row.get("population_density")),
            }
        )
    return rows


def get_facility_points(limit: int = 300) -> list[dict]:
    facilities = _facilities()
    if facilities.empty:
        return []

    cols = ["name", "category", "district", "lat", "lon", "confidence_score"]
    clean = facilities.dropna(subset=["lat", "lon"]).head(limit)
    points = []
    for _, row in clean.iterrows():
        points.append(
            {
                "name": row.get("name") or "Sans nom",
                "category": row.get("category", "unknown"),
                "district": row.get("district", "Unknown"),
                "lat": float(row.get("lat")),
                "lon": float(row.get("lon")),
                "confidence": _safe_float(row.get("confidence_score"), 0.5),
            }
        )
    return points


def _competition_label_fr(level: str) -> str:
    return {"Low": "faible", "Medium": "modérée", "High": "élevée", "Saturated": "saturée"}.get(level, level)


def _risk_severity(risk_score: float) -> str:
    if risk_score < 25:
        return "faible"
    if risk_score < 50:
        return "modéré"
    if risk_score < 75:
        return "élevé"
    return "critique"


def _alternatives_markdown(opportunities: list[dict]) -> str:
    alternatives = opportunities[1:3]
    if not alternatives:
        return ""
    rows = "\n".join(
        f"| {item['zone']} | {item['score']:.1f}/100 | {item['risk']:.1f}/100 | "
        f"{_safe_float(item.get('confidence')):.1f}/100 |"
        for item in alternatives
    )
    return (
        "\n\n## Alternatives à comparer\n\n"
        "| Zone | Opportunité | Risque | Confiance données |\n"
        "|---|---:|---:|---:|\n"
        f"{rows}"
    )


def build_answer(question: str, category: str = "Small Private Clinic", locale: str = "fr") -> dict:
    category = _category_from_question(question, _category_or_default(category))
    opportunities = get_opportunities(category)
    snapshot = get_market_snapshot()
    top = opportunities[0] if opportunities else {
        "zone": "Casablanca", "score": 0, "risk": 0, "supply_gap": 0,
        "competition_level": "N/A", "providers": 0, "population": 0, "density": 0,
        "category": category, "confidence": 0,
    }

    score = top["score"]
    zone = top["zone"]
    cat_fr = CATEGORY_DISPLAY_FR.get(top.get("category", category), category).lower()
    comp_fr = _competition_label_fr(top["competition_level"])
    risk_sev = _risk_severity(top["risk"])
    data_confidence = _safe_float(top.get("confidence"))

    runner_text = _alternatives_markdown(opportunities)

    answer = (
        f"## Recommandation\n\n"
        f"**{zone}** est la zone prioritaire pour une **{cat_fr}** "
        f"à Casablanca, avec un score d'opportunité de **{score:.1f}/100** "
        f"et un risque évalué à **{top['risk']:.1f}/100** ({risk_sev}) [1].\n\n"
        f"## Indicateurs clés\n\n"
        f"| Indicateur | Valeur | Source |\n"
        f"|---|---|---|\n"
        f"| Population | **{top['population']:,} hab.** | HCP RGPH 2024 [2] |\n"
        f"| Densité | **{top['density']:,.0f}/km2** | Données zonales [2] |\n"
        f"| Concurrence | **{comp_fr}** ({top['providers']} prestataires) | Cartographie OSM [3] |\n"
        f"| Supply gap | **{top['supply_gap']:.1f}/100** | Modèle de scoring [1] |\n"
        f"| Confiance des données | **{data_confidence:.1f}/100** | Qualité et complétude par catégorie [1] |\n"
        f"| Score global | **{score:.1f}/100** | Moteur Invest Search [1] |\n\n"
        f"## Analyse des risques\n\n"
        f"- **Fiabilité des données** ({risk_sev}) : les comptages s'appuient sur OpenStreetMap, "
        f"qui peut sous-estimer les établissements non cartographiés [3].\n"
        f"- **Concurrence réelle** : {top['providers']} prestataires identifiés ; "
        f"des acteurs informels ou récemment ouverts peuvent ne pas figurer dans les données.\n"
        f"- **Assignation de zone** : {snapshot['unknown_district_count']} etablissements sont en district « Unknown » — "
        f"les comptages par zone doivent être validés sur le terrain [2].\n\n"
        f"## Prochaines étapes\n\n"
        f"1. **Visite terrain** à {zone} : vérifier la présence réelle de concurrents et l'état des locaux disponibles.\n"
        f"2. **Étude de flux** : mesurer le trafic piéton et la proximité des transports en commun.\n"
        f"3. **Vérification réglementaire** : confirmer les autorisations sanitaires auprès de la délégation de santé.\n"
        f"{runner_text}\n\n"
        f"---\n"
        f"*Sources : [1] Moteur de scoring Invest Search, [2] Données HCP / zones Casablanca, [3] OpenStreetMap.*"
    )
    answer = (
        answer
        .replace("etablissements", "établissements")
        .replace("Â«", "«")
        .replace("Â»", "»")
        .replace("â€”", "-")
        .replace("—", "-")
    )

    return {
        "question": question,
        "answer_markdown": answer,
        "top_zone": zone,
        "score": score,
        "risk": top["risk"],
        "category": top.get("category", category),
        "sources": snapshot["sources"],
        "kpis": [
            {"label": "Population", "value": f"{top['population']:,} hab."},
            {"label": "Concurrence", "value": f"{comp_fr} ({top['providers']})"},
            {"label": "Supply gap", "value": f"{top['supply_gap']:.1f}/100"},
            {"label": "Confiance données", "value": f"{data_confidence:.1f}/100"},
            {"label": "Risque", "value": f"{top['risk']:.1f}/100 ({risk_sev})"},
        ],
        "map_focus": {"label": zone, "lat": 33.57, "lon": -7.59, "zoom": 12},
        "related_opportunities": opportunities[:5],
    }


def build_answer_enriched(question: str, category: str = "Small Private Clinic", locale: str = "fr") -> dict:
    category = _category_from_question(question, _category_or_default(category))
    opportunities = get_opportunities(category)
    areas = _areas()
    snapshot = get_market_snapshot()
    top = opportunities[0] if opportunities else {
        "zone": "Casablanca", "score": 0, "risk": 0, "supply_gap": 0,
        "competition_level": "N/A", "providers": 0, "population": 0, "density": 0,
        "category": category, "confidence": 0,
    }

    score = top["score"]
    zone = top["zone"]
    cat_fr = CATEGORY_DISPLAY_FR.get(top.get("category", category), category).lower()
    comp_fr = _competition_label_fr(top["competition_level"])
    risk_sev = _risk_severity(top["risk"])
    data_confidence = _safe_float(top.get("confidence"))
    area = _area_row(zone)
    distribution = _population_distribution(areas, zone)

    facilities_total = _safe_int(area.get("medical_facilities_count", top.get("providers", 0)))
    facilities_per_100k = _safe_float(area.get("facilities_per_100k", top.get("providers_per_100k", 0)))
    demand_index = _safe_float(area.get("demand_index", 0))
    access_index = _safe_float(area.get("accessibility_index", 0))
    competition_index = _safe_float(area.get("low_competition_index", 0))
    nearest_hospital = _safe_float(area.get("nearest_hospital_km", 0))
    pharmacy_count = _safe_int(area.get("pharmacy_count", 0))
    clinic_count = _safe_int(area.get("clinic_count", 0))
    doctor_count = _safe_int(area.get("doctor_count", 0))
    lab_count = _safe_int(area.get("laboratory_count", 0))
    public_primary_count = _safe_int(area.get("public_primary_care_count", 0))
    public_hospital_count = _safe_int(area.get("public_hospital_count", 0))
    density_rank = distribution["density_rank"] or "n/a"
    population_rank = distribution["population_rank"] or "n/a"

    top_population_text = ", ".join(
        f"{row['area_name']} ({_format_int(row['population_est'])} hab.)"
        for row in distribution["top_population"]
    )
    top_density_text = ", ".join(
        f"{row['area_name']} ({_format_int(row['population_density'])}/km²)"
        for row in distribution["top_density"]
    )
    top_undersupply_text = ", ".join(
        f"{row['area_name']} ({row['undersupply_index']}/100)"
        for row in distribution["top_undersupply"]
    )

    runner_text = _alternatives_markdown(opportunities)

    answer = (
        f"## Recommandation\n\n"
        f"**{zone}** est la zone prioritaire pour une **{cat_fr}** à Casablanca, avec un score "
        f"d'opportunité de **{score:.1f}/100** et un risque évalué à **{top['risk']:.1f}/100** "
        f"({risk_sev}) [1]. La recommandation combine la distribution de population, la densité, "
        f"l'offre médicale existante, l'accessibilité aux hôpitaux, le supply gap et la concurrence "
        f"observée dans OpenStreetMap, avec contrôle de l'offre publique MSPS [2][3][4].\n\n"
        f"## Lecture de la population\n\n"
        f"- **Population officielle HCP 2024 :** {_format_int(top['population'])} habitants, soit "
        f"**{distribution['zone_share']}%** de la population couverte par les zones analysées.\n"
        f"- **Rang population :** {population_rank}/{len(areas) if not areas.empty else 0}. "
        f"Les zones les plus peuplées sont : {top_population_text or 'non disponible'}.\n"
        f"- **Densité :** {_format_int(top['density'])} hab./km², rang densité {density_rank}. "
        f"Les plus fortes densités observées sont : {top_density_text or 'non disponible'}.\n\n"
        f"## Offre médicale et saturation\n\n"
        f"La zone compte **{facilities_total} équipements médicaux cartographiés**, soit "
        f"**{facilities_per_100k}/100k habitants**. Pour la catégorie ciblée, le moteur identifie "
        f"**{top['providers']} prestataires comparables** et une concurrence **{comp_fr}** [3]. "
        f"Le mix local comprend notamment {pharmacy_count} pharmacies, {clinic_count} cliniques, "
        f"{doctor_count} cabinets médicaux et {lab_count} laboratoires dans OSM. Le MSPS recense "
        f"**{public_primary_count} structures de soins primaires** et **{public_hospital_count} hôpitaux publics** [4].\n\n"
        f"## Indicateurs clés\n\n"
        f"| Indicateur | Valeur | Source |\n"
        f"|---|---|---|\n"
        f"| Population | **{top['population']:,} hab.** | HCP RGPH 2024 [2] |\n"
        f"| Part population | **{distribution['zone_share']}%** | Distribution zonale [2] |\n"
        f"| Densité | **{top['density']:,.0f}/km²** | Données zonales [2] |\n"
        f"| Équipements / 100k | **{facilities_per_100k}** | OSM + population [2][3] |\n"
        f"| Demande | **{demand_index}/100** | Densité + population [1] |\n"
        f"| Accessibilité | **{access_index}/100** | Distance hôpital / axes [1] |\n"
        f"| Hôpital le plus proche | **{nearest_hospital} km** | OSM [3] |\n"
        f"| Concurrence | **{comp_fr}** ({top['providers']} prestataires) | Cartographie OSM [3] |\n"
        f"| Supply gap | **{top['supply_gap']:.1f}/100** | Modèle de scoring [1] |\n"
        f"| Confiance des données | **{data_confidence}/100** | Complétude par catégorie [1] |\n"
        f"| Offre publique | **{public_primary_count} centres · {public_hospital_count} hôpitaux** | MSPS 2024 [4] |\n"
        f"| Score global | **{score:.1f}/100** | Moteur Invest Search [1] |\n\n"
        f"## Paramètres de décision\n\n"
        f"- **Demande potentielle :** privilégier les micro-emplacements proches des zones résidentielles denses, "
        f"des axes de transport et des poches à forte population active.\n"
        f"- **Distribution géographique :** comparer {zone} avec les zones à forte population et forte densité avant le choix final.\n"
        f"- **Sous-offre relative :** les zones avec le plus fort undersupply index sont : "
        f"{top_undersupply_text or 'non disponible'}.\n"
        f"- **Données à compléter :** loyers commerciaux, niveau de revenu, flux piéton, stationnement, accessibilité PMR, "
        f"autorisations sanitaires et présence de concurrents non cartographiés.\n\n"
        f"## Analyse des risques\n\n"
        f"- **Fiabilité des données** ({risk_sev}) : les comptages s'appuient sur OpenStreetMap, "
        f"qui peut sous-estimer les établissements non cartographiés [3].\n"
        f"- **Concurrence réelle** : {top['providers']} prestataires identifiés ; "
        f"des acteurs informels ou récemment ouverts peuvent ne pas figurer dans les données.\n"
        f"- **Granularité** : la population HCP 2024 est officielle à l'arrondissement, mais ne décrit pas les micro-quartiers.\n"
        f"- **Assignation de zone** : {snapshot['unknown_district_count']} établissements sont en district « Unknown » ; "
        f"les comptages par zone doivent être validés sur le terrain [2].\n\n"
        f"## Prochaines étapes\n\n"
        f"1. **Visite terrain** à {zone} : vérifier la présence réelle de concurrents et l'état des locaux disponibles.\n"
        f"2. **Étude de flux** : mesurer le trafic piéton, la proximité des transports et la pression de stationnement.\n"
        f"3. **Enrichissement données** : mettre à jour OpenStreetMap, relancer le scoring, puis réindexer le RAG depuis l'outil admin.\n"
        f"4. **Vérification réglementaire** : confirmer les autorisations sanitaires auprès de la délégation de santé.\n"
        f"{runner_text}\n\n"
        f"---\n"
        f"*Sources : [1] Moteur de scoring Invest Search, [2] HCP RGPH 2024, [3] OpenStreetMap, [4] MSPS 2024.*"
    )

    return {
        "question": question,
        "answer_markdown": answer,
        "top_zone": zone,
        "score": score,
        "risk": top["risk"],
        "category": top.get("category", category),
        "sources": snapshot["sources"],
        "kpis": [
            {"label": "Population", "value": f"{top['population']:,} hab."},
            {"label": "Part population", "value": f"{distribution['zone_share']}%"},
            {"label": "Densité", "value": f"{top['density']:,.0f}/km²"},
            {"label": "Équipements / 100k", "value": f"{facilities_per_100k}"},
            {"label": "Concurrence", "value": f"{comp_fr} ({top['providers']})"},
            {"label": "Supply gap", "value": f"{top['supply_gap']:.1f}/100"},
            {"label": "Confiance données", "value": f"{data_confidence:.1f}/100"},
            {"label": "Accessibilité", "value": f"{access_index}/100"},
            {"label": "Risque", "value": f"{top['risk']:.1f}/100 ({risk_sev})"},
        ],
        "map_focus": _zone_focus(zone),
        "related_opportunities": opportunities[:5],
    }


_GREETING_TOKENS = {
    "hi", "hello", "hey", "bonjour", "salut", "bonsoir", "coucou",
    "salam", "yo", "allo", "bsr", "bjr", "wesh",
}

_THANKS_TOKENS = {
    "merci", "thanks", "thank", "thx", "chokran", "shukran", "baraka", "ok", "okay",
    "parfait", "super", "top", "bien", "cool",
}

_HELP_TOKENS = {
    "aide", "help", "guide", "utiliser", "usage", "fonction", "fonctionnalites",
    "fonctionnalite", "quoi", "peux", "faire", "assistant",
}

_SOURCE_TOKENS = {
    "source", "sources", "donnees", "data", "dataset", "datasets", "origine",
    "preuve", "preuves", "citation", "citations", "fiabilite",
}

_MAP_TOKENS = {
    "carte", "map", "maps", "localisation", "localiser", "geographie", "geo",
    "geolocalisation",
}

_REPORT_TOKENS = {
    "rapport", "rapports", "memo", "note", "investisseur", "export", "pdf",
    "document", "synthese", "brief", "checklist",
}

_CATEGORY_TOKENS = {
    "categorie", "categories", "type", "types", "specialite", "specialites",
    "services", "metier", "metiers",
}

_INVESTMENT_INTENT_TOKENS = {
    "acheter", "analyse", "analyser", "cabinet", "centre", "clinique", "comparer",
    "concurrence", "couverture", "dentiste", "implanter", "investir", "laboratoire",
    "localiser", "marche", "medical", "medicale", "medicaux", "opportunite",
    "ouvrir", "pharmacie", "population", "rapport", "radiologie", "risque",
    "sante", "score", "sous", "supply", "zone",
}

_DOMAIN_CONTEXT_TOKENS = (
    _INVESTMENT_INTENT_TOKENS
    | _SOURCE_TOKENS
    | _MAP_TOKENS
    | _REPORT_TOKENS
    | _CATEGORY_TOKENS
    | {
        "accessibilite", "arrondissement", "besoin", "casablanca", "cabinet",
        "commercial", "concurrent", "demande", "densite", "docteur", "dentaire",
        "données", "donnees", "etablissement", "etablissements", "hopital",
        "investissement", "kpi", "local", "loyer", "patient", "patients",
        "quartier", "quartiers", "sanitaire", "soins", "terrain", "veterinaire",
        # Analytics / methodology vocabulary so explanatory questions
        # ("comment fonctionne le scoring", "explique l'indice de demande")
        # reach the RAG instead of being refused as out-of-scope.
        "scoring", "methodologie", "methode", "methodes", "indice", "indices",
        "indicateur", "indicateurs", "calcul", "calcule", "calculer", "ponderation",
        "formule", "critere", "criteres", "gap", "saturation", "opportunite",
        "secteur", "secteurs", "restauration", "restaurant", "commerce", "education",
        "wellness", "implantation",
    }
)

_WEAK_DOMAIN_CONTEXT_TOKENS = {
    "ouvrir", "open", "acheter", "analyse", "analyser", "localiser",
}

_EXTERNAL_COMMAND_VERBS = {
    "ouvrir", "ouvre", "open", "launch", "lancer", "lance", "navigate",
    "visiter", "visite", "aller", "va", "go", "browse",
}

_EXTERNAL_SERVICE_TOKENS = {
    "youtube", "youtu", "facebook", "instagram", "tiktok", "netflix", "spotify",
    "gmail", "google", "maps", "twitter", "linkedin", "whatsapp", "telegram",
    "discord", "reddit", "amazon", "shein", "chatgpt", "claude", "perplexity",
}

_EXTERNAL_COMMAND_PHRASES = (
    "go to", "goto", "va sur", "aller sur", "ouvre le site", "ouvrir le site",
    "open site", "open website", "launch site",
)

_URL_OR_DOMAIN_RE = re.compile(
    r"(?:https?://|www\.|\b[a-z0-9][a-z0-9-]{1,62}\.(?:com|ma|org|net|io|ai|fr|app|dev|gov|edu|co)\b)",
    re.IGNORECASE,
)

_ABUSIVE_TOKENS = {
    "fuck", "shit", "bitch", "asshole", "stupid", "idiot", "merde",
    "connard", "con", "salope", "gueule",
}

_ABUSIVE_FILLER_TOKENS = {"you", "u", "toi", "tu", "te", "t", "your", "ta", "tes", "la"}

_LOCATION_FACTS = {
    "marrakech": {
        "label": "Marrakech",
        "aliases": {"marrakech", "marrakesh", "marrakech", "kech"},
        "summary": (
            "Marrakech est une ville du centre-ouest du Maroc, dans la région "
            "Marrakech-Safi. Elle se situe à l'intérieur du pays, au pied du Haut Atlas, "
            "à environ 240 km au sud de Casablanca."
        ),
        "lat": 31.6295,
        "lon": -7.9811,
    },
    "rabat": {
        "label": "Rabat",
        "aliases": {"rabat"},
        "summary": "Rabat est la capitale administrative du Maroc, située sur la côte atlantique au nord de Casablanca.",
        "lat": 34.0209,
        "lon": -6.8416,
    },
    "tanger": {
        "label": "Tanger",
        "aliases": {"tanger", "tangier"},
        "summary": "Tanger est une ville du nord du Maroc, près du détroit de Gibraltar.",
        "lat": 35.7595,
        "lon": -5.8340,
    },
    "fes": {
        "label": "Fès",
        "aliases": {"fes", "fès", "fez"},
        "summary": "Fès est une ville historique du nord-est du Maroc, connue pour sa médina et son rôle culturel.",
        "lat": 34.0181,
        "lon": -5.0078,
    },
    "agadir": {
        "label": "Agadir",
        "aliases": {"agadir"},
        "summary": "Agadir est une ville côtière du sud-ouest du Maroc, dans la région Souss-Massa.",
        "lat": 30.4278,
        "lon": -9.5981,
    },
    "bouskoura": {
        "label": "Bouskoura",
        "aliases": {"bouskoura", "bouskora"},
        "summary": (
            "Bouskoura est une commune périurbaine au sud de Casablanca. Elle fait partie du Grand Casablanca, "
            "mais elle n'est pas encore couverte comme zone autonome dans le dataset Invest Search actuel."
        ),
        "lat": 33.4495,
        "lon": -7.6480,
    },
    "mohammedia": {
        "label": "Mohammedia",
        "aliases": {"mohammedia", "mohamadia", "mohammediaa"},
        "summary": (
            "Mohammedia est une ville côtière située au nord-est de Casablanca. Elle nécessite un périmètre "
            "de collecte dédié avant de produire un scoring Invest Search fiable."
        ),
        "lat": 33.6835,
        "lon": -7.3849,
    },
}


def _normalize_text(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9\s]", " ", without_accents)


def _tokenize(text: str) -> set[str]:
    return set(_normalize_text(text).split())


def _preferred_view_from_question(question: str, default: str = "intelligence") -> str:
    """Route explicit UI intents without changing the analytical answer."""
    words = _tokenize(question)
    normalized = _normalize_text(question)
    if words & _REPORT_TOKENS or any(
        phrase in normalized
        for phrase in (
            "rapport investisseur",
            "preparer un rapport",
            "generer un rapport",
            "memo investisseur",
            "export pdf",
        )
    ):
        return "reports"
    if words & _MAP_TOKENS or any(
        phrase in normalized
        for phrase in (
            "afficher la carte",
            "montre la carte",
            "voir la carte",
            "sur la carte",
            "carte interactive",
        )
    ):
        return "map"
    if words & _SOURCE_TOKENS and len(words) <= 8:
        return "sources"
    return default


def _is_greeting(text: str) -> bool:
    words = _tokenize(text)
    return bool(words & _GREETING_TOKENS) and len(words) <= 5


def _location_fact_from_question(question: str) -> dict | None:
    words = _tokenize(question)
    normalized = _normalize_text(question)
    for fact in _LOCATION_FACTS.values():
        aliases = {_normalize_text(alias).strip() for alias in fact["aliases"]}
        if words & aliases or any(f" {alias} " in f" {normalized} " for alias in aliases):
            return fact
    return None


def _has_investment_intent(words: set[str], normalized: str) -> bool:
    if words & _INVESTMENT_INTENT_TOKENS:
        return True
    intent_phrases = (
        "clinique de jour",
        "faible couverture",
        "sous equipe",
        "sous equipes",
        "supply gap",
        "ouvrir une",
        "ouvrir un",
        "ou implanter",
        "meilleure zone",
        "prochaine clinique",
    )
    return any(phrase in normalized for phrase in intent_phrases)


def _is_external_navigation_command(question: str, words: set[str], normalized: str) -> bool:
    raw = question.lower()
    has_url_or_domain = bool(_URL_OR_DOMAIN_RE.search(raw))
    has_external_service = bool(words & _EXTERNAL_SERVICE_TOKENS)
    has_command_verb = bool(words & _EXTERNAL_COMMAND_VERBS) or any(
        phrase in normalized for phrase in _EXTERNAL_COMMAND_PHRASES
    )
    has_healthcare_anchor = bool(
        words & (
            _CATEGORY_TOKENS
            | {
                "clinique", "cliniques", "pharmacie", "pharmacies", "dentiste",
                "dentaire", "veterinaire", "laboratoire", "radiologie", "sante",
                "medical", "medicale", "medicaux", "hopital", "hopitaux",
            }
        )
    )
    if has_healthcare_anchor:
        return False
    return has_command_verb and (has_url_or_domain or has_external_service)


def _is_abusive_message(words: set[str]) -> bool:
    if not (words & _ABUSIVE_TOKENS):
        return False
    non_abusive_words = words - _ABUSIVE_TOKENS - _ABUSIVE_FILLER_TOKENS
    return len(non_abusive_words) <= 2


def _has_domain_context(question: str, words: set[str], normalized: str) -> bool:
    strong_words = words - _WEAK_DOMAIN_CONTEXT_TOKENS
    if strong_words & _DOMAIN_CONTEXT_TOKENS:
        return True
    if _zones_from_question(question):
        return True
    # Any covered non-medical sector noun (café, école, salle de sport, ...) is
    # in-scope too, so multi-sector questions are not refused as out-of-scope.
    if _sector_from_question(question):
        return True
    if _sector_category_from_question is not None and _sector_category_from_question(question):
        return True
    domain_phrases = (
        "clinique de jour",
        "centre de sante",
        "carte sanitaire",
        "faible couverture",
        "marche medical",
        "offre de soins",
        "openstreetmap",
        "supply gap",
    )
    return any(phrase in normalized for phrase in domain_phrases)


def build_external_command_answer(question: str) -> dict:
    markdown = (
        "## Commande hors périmètre Invest Search\n\n"
        "Je ne peux pas ouvrir un site web, lancer une application externe ou piloter le navigateur. "
        "Invest Search est limité à l'analyse d'implantation à Casablanca (santé, restauration, "
        "commerce, éducation, bien-être), aux cartes, sources, rapports et recommandations.\n\n"
        "Demandes valides :\n\n"
        "- **Où ouvrir une pharmacie à faible concurrence ?**\n"
        "- **Où ouvrir un restaurant à Casablanca ?**\n"
        "- **Afficher la carte des pharmacies à Anfa.**\n"
        "- **J'ai un budget de 800 000 dh, que puis-je ouvrir ?**"
    )
    response = _quick_response(
        question=question,
        markdown=markdown,
        status="out_of_scope_command",
        category="Hors périmètre",
        top_zone="Casablanca",
        kpis=[
            {"label": "Périmètre", "value": "Invest Search"},
            {"label": "Commande externe", "value": "Refusée"},
            {"label": "Action", "value": "Reformuler"},
        ],
    )
    response["suggested_questions"] = [
        "Où ouvrir une pharmacie à faible concurrence ?",
        "Afficher la carte des cliniques à Casablanca",
        "Comparer Anfa et Maarif pour une clinique",
    ]
    return response


def build_abusive_message_answer(question: str) -> dict:
    markdown = (
        "## Reformulation nécessaire\n\n"
        "Je peux aider sur Invest Search, mais je ne traite pas les messages insultants ou non exploitables. "
        "Reformulez votre demande avec un type d'établissement, une zone ou un indicateur à analyser.\n\n"
        "Exemples utiles :\n\n"
        "- **Supply gap pharmacie à Maarif**\n"
        "- **Risque à Sidi Moumen**\n"
        "- **Quels quartiers sont sous-couverts médicalement ?**"
    )
    response = _quick_response(
        question=question,
        markdown=markdown,
        status="out_of_scope_message",
        category="Hors périmètre",
        top_zone="Casablanca",
        kpis=[
            {"label": "Statut", "value": "À reformuler"},
            {"label": "Périmètre", "value": "Implantation à Casablanca"},
            {"label": "Action", "value": "Question métier"},
        ],
    )
    response["suggested_questions"] = [
        "Où ouvrir une pharmacie à faible concurrence ?",
        "Supply gap dentaire à Maarif",
        "Quels quartiers ont une faible couverture médicale ?",
    ]
    return response


def build_out_of_scope_answer(question: str) -> dict:
    markdown = (
        "## Hors périmètre Invest Search\n\n"
        "Cette question ne semble pas liée à l'analyse d'implantation à Casablanca (santé, restauration, "
        "commerce, éducation, bien-être), aux quartiers, aux sources de données, à la carte ou à un rapport.\n\n"
        "Je peux aider sur des demandes comme :\n\n"
        "- **Où ouvrir une pharmacie à faible concurrence ?**\n"
        "- **Où ouvrir un restaurant ou un commerce à Casablanca ?**\n"
        "- **Quels quartiers ont une faible couverture médicale ?**\n"
        "- **J'ai un budget de 800 000 dh, que puis-je ouvrir ?**\n\n"
        "Reformulez la question avec un type d'établissement, une zone ou un indicateur à analyser."
    )
    return _quick_response(
        question=question,
        markdown=markdown,
        status="out_of_scope_question",
        category="Hors périmètre",
        top_zone="Casablanca",
        kpis=[
            {"label": "Périmètre", "value": "Implantation à Casablanca"},
            {"label": "Action", "value": "Reformuler"},
            {"label": "Exemples", "value": "Pharmacie, clinique, carte, rapport"},
        ],
    )


def build_location_scope_answer(question: str, fact: dict, has_investment_intent: bool) -> dict:
    place = fact["label"]
    if has_investment_intent:
        markdown = (
            f"## Couverture géographique\n\n"
            f"{fact['summary']}\n\n"
            "Pour l'instant, **Invest Search dispose d'un pipeline complet seulement pour Casablanca** : "
            "points OpenStreetMap santé, restauration, commerce, éducation et bien-être, zones, "
            "indicateurs de population, scoring et index RAG.\n\n"
            f"Je ne dois donc pas inventer un score d'opportunité pour **{place}** avec les données de Casablanca. "
            f"Pour analyser {place}, il faut lancer une mise à jour dédiée : collecte OSM sur {place}, "
            "normalisation, découpage territorial, indicateurs démographiques, recalcul des scores et réindexation RAG.\n\n"
            "Vous pouvez utiliser l'outil admin de mise à jour des données comme base, mais il faudra ajouter "
            f"un périmètre **{place}** au pipeline avant de produire une recommandation fiable."
        )
        status = "out_of_scope_region"
        kpis = [
            {"label": "Ville demandée", "value": place},
            {"label": "Dataset actif", "value": "Casablanca"},
            {"label": "Analyse investissement", "value": "À collecter"},
            {"label": "Action", "value": "Créer un pipeline ville"},
        ]
    else:
        markdown = (
            f"## {place}\n\n"
            f"{fact['summary']}\n\n"
            "Note : la plateforme **Invest Search** est actuellement spécialisée sur l'analyse du marché "
            "médical de **Casablanca**. Si vous voulez une analyse d'investissement pour Marrakech ou une autre ville, "
            "il faut d'abord collecter et indexer les données locales correspondantes."
        )
        status = "easy_location"
        kpis = [
            {"label": "Ville", "value": place},
            {"label": "Pays", "value": "Maroc"},
            {"label": "Latitude", "value": f"{fact['lat']:.4f}"},
            {"label": "Longitude", "value": f"{fact['lon']:.4f}"},
        ]

    response = _quick_response(
        question=question,
        markdown=markdown,
        status=status,
        category="Information géographique",
        top_zone=place,
        kpis=kpis,
    )
    response["map_focus"] = {"label": place, "lat": fact["lat"], "lon": fact["lon"], "zoom": 11}
    return response


def _is_short_client_request(words: set[str], max_words: int = 8) -> bool:
    return 0 < len(words) <= max_words


def _snapshot_kpis(snapshot: dict) -> list[dict]:
    medical_points = int(snapshot.get("facility_count") or 0)
    multisector_points = int(snapshot.get("multisector_total") or 0)
    total_osm_points = int(snapshot.get("osm_total_points") or (medical_points + multisector_points))
    sector_count = len((snapshot.get("multisector") or {}).get("sectors") or [])
    return [
        {
            "label": "Points OSM",
            "value": (
                f"{_format_int(total_osm_points)} cartographiés "
                f"({_format_int(medical_points)} santé + {_format_int(multisector_points)} multi)"
            ),
        },
        {"label": "Zones analysées", "value": f"{snapshot['district_count']} districts"},
        {"label": "Domaines", "value": f"Santé + {sector_count} secteurs"},
        {"label": "Données", "value": "OSM + HCP + MSPS"},
    ]


def _is_low_coverage_question(normalized: str) -> bool:
    coverage_terms = (
        "faible couverture",
        "couverture medicale faible",
        "moins couverts",
        "moins couvert",
        "sous couverts",
        "sous couvert",
        "sous equipe",
        "sous equipes",
        "desert medical",
        "deserts medicaux",
        "manque de structures medicales",
        "manque d etablissements medicaux",
        "peu d etablissements medicaux",
        "offre medicale faible",
    )
    return any(term in normalized for term in coverage_terms)


def build_low_coverage_answer(question: str) -> dict:
    areas = _areas()
    snapshot = get_market_snapshot()
    required = {
        "area_name",
        "population_est",
        "medical_facilities_count",
        "facilities_per_100k",
        "undersupply_index",
        "public_primary_care_count",
    }
    if areas.empty or not required.issubset(areas.columns):
        return _quick_response(
            question=question,
            status="coverage_unavailable",
            markdown="Les indicateurs de couverture médicale par quartier ne sont pas disponibles.",
        )

    ranked = areas.copy()
    for column in required - {"area_name"}:
        ranked[column] = pd.to_numeric(ranked[column], errors="coerce").fillna(0)
    ranked["public_primary_per_100k"] = (
        ranked["public_primary_care_count"] / ranked["population_est"].replace(0, pd.NA) * 100_000
    ).fillna(0)
    ranked["coverage_signal"] = (
        0.65 * _normalize_series_0_100(ranked["facilities_per_100k"])
        + 0.35 * _normalize_series_0_100(ranked["public_primary_per_100k"])
    )
    ranked = ranked.sort_values(["coverage_signal", "population_est"], ascending=[True, False]).head(6)

    rows = []
    opportunities = []
    for _, row in ranked.iterrows():
        zone = str(row["area_name"])
        facilities = _safe_int(row["medical_facilities_count"])
        coverage = _safe_float(row["facilities_per_100k"])
        undersupply = _safe_float(row["undersupply_index"])
        population = _safe_int(row["population_est"])
        public_primary = _safe_int(row["public_primary_care_count"])
        rows.append(
            f"| {zone} | {_format_int(population)} | {facilities} | {public_primary} | "
            f"{coverage:.1f} | {undersupply:.1f}/100 |"
        )
        opportunities.append(
            {
                "zone": zone,
                "category": "Couverture médicale générale",
                "score": undersupply,
                "risk": 0,
                "supply_gap": undersupply,
                "competition_level": "N/A",
                "providers": facilities,
                "providers_per_100k": coverage,
                "population": population,
                "density": _safe_float(row.get("population_density")),
            }
        )

    top = opportunities[0]
    answer = (
        "## Quartiers les moins couverts\n\n"
        "Le classement croise la couverture OSM par habitant et l'offre publique MSPS 2024. "
        "Il décrit une sous-couverture observée, pas une recommandation d'investissement :\n\n"
        "| Arrondissement | Population HCP 2024 | Points OSM | Centres publics | Points OSM / 100k | Sous-offre |\n"
        "|---|---:|---:|---:|---:|---:|\n"
        + "\n".join(rows)
        + "\n\n"
        "## Lecture\n\n"
        f"- **{top['zone']}** présente la couverture observée la plus faible, avec "
        f"**{top['providers_per_100k']:.1f} établissement pour 100 000 habitants**.\n"
        f"- Les six zones affichées sont triées avec le même signal croisé; **{top['zone']}** arrive en tête.\n"
        "- Ce classement mesure la **couverture médicale générale**. Il ne désigne pas automatiquement "
        "le meilleur quartier pour une clinique, une pharmacie ou une autre spécialité.\n\n"
        "## Limite importante\n\n"
        "La couche privée reste principalement issue d'OpenStreetMap et peut être incomplète. "
        "La couche MSPS couvre l'offre publique, mais pas les cabinets et établissements privés exhaustifs. "
        "Une validation terrain reste nécessaire.\n\n"
        "---\n"
        "*Sources : HCP RGPH 2024, offre publique MSPS 2024, OpenStreetMap et indicateurs Invest Search.*"
    )

    return {
        "question": question,
        "answer_markdown": answer,
        "top_zone": top["zone"],
        "score": top["supply_gap"],
        "risk": 0,
        "category": "Couverture médicale générale",
        "sources": snapshot["sources"],
        "kpis": [
            {"label": "Zone la moins couverte", "value": top["zone"]},
            {"label": "Équipements / 100k", "value": f"{top['providers_per_100k']:.1f}"},
            {"label": "Établissements recensés", "value": str(top["providers"])},
            {"label": "Indice de sous-offre", "value": f"{top['supply_gap']:.1f}/100"},
        ],
        "map_focus": _zone_focus(top["zone"]),
        "related_opportunities": opportunities,
        "retrieved_contexts": [],
        "rag_status": "coverage_analysis",
        "suggested_view": _preferred_view_from_question(question),
    }


# Common spellings / typos -> canonical zone name (from area_indicators.csv).
_ZONE_ALIASES = {
    "maarif": "Maarif", "maariff": "Maarif", "maarrif": "Maarif", "maarriff": "Maarif", "marif": "Maarif",
    "maarif casablanca": "Maarif",
    "anfa": "Anfa", "anffa": "Anfa", "anfaa": "Anfa",
    "ain chock": "Ain Chock", "ain chok": "Ain Chock", "ainchock": "Ain Chock", "ain chouk": "Ain Chock",
    "sidi maarouf": "Ain Chock", "sidi maaruf": "Ain Chock", "sidi maaref": "Ain Chock",
    "ain sebaa": "Ain Sebaa", "ain sbaa": "Ain Sebaa", "sebaa": "Ain Sebaa",
    "ben m sick": "Ben M'Sick", "ben msik": "Ben M'Sick", "ben msick": "Ben M'Sick",
    "benmsick": "Ben M'Sick", "ben m sik": "Ben M'Sick", "ben mssik": "Ben M'Sick",
    "sidi bernoussi": "Sidi Bernoussi", "sidi bernousi": "Sidi Bernoussi",
    "bernoussi": "Sidi Bernoussi", "bernousi": "Sidi Bernoussi",
    "sidi moumen": "Sidi Moumen", "sidi moumene": "Sidi Moumen",
    "moumen": "Sidi Moumen", "moumene": "Sidi Moumen",
    "moulay rachid": "Moulay Rachid", "moulay rchid": "Moulay Rachid",
    "hay hassani": "Hay Hassani", "hassani": "Hay Hassani",
    "hay mohammadi": "Hay Mohammadi", "hay mohamadi": "Hay Mohammadi", "mohammadi": "Hay Mohammadi",
    "sidi belyout": "Sidi Belyout", "belyout": "Sidi Belyout",
    "casablanca medina": "Sidi Belyout", "medina": "Sidi Belyout",
    "ancienne medina": "Sidi Belyout",
    "al fida": "Al Fida", "alfida": "Al Fida", "fida": "Al Fida",
    "mers sultan": "Mers Sultan", "mers soltane": "Mers Sultan",
    "roches noires": "Roches Noires", "roche noire": "Roches Noires",
    "assoukhour assawda": "Roches Noires", "asoukhour assawda": "Roches Noires",
    "sidi othmane": "Sidi Othmane", "sidi otmane": "Sidi Othmane",
    "sbata": "Sbata",
}

# Generic words that must never trigger a fuzzy zone match.
_ZONE_FUZZY_BLOCKLIST = {
    "casablanca", "ville", "quartier", "quartiers", "zone", "zones", "centre", "centres",
    "clinique", "cliniques", "pharmacie", "pharmacies", "laboratoire", "laboratoires",
    "medical", "medicale", "medicaux", "analyse", "analyses", "concurrence", "concurrent",
    "supply", "investir", "investissement", "ouvrir", "rapport", "carte", "risque",
    "risques", "marche", "sante", "densite", "population", "opportunite", "comparaison",
    "comparer", "dentiste", "dentaire", "veterinaire", "radiologie", "imagerie", "hopital",
    "hopitaux", "cabinet", "medecin", "docteur", "urgence", "pediatrie", "couverture",
}
# Conservative: short zone names (e.g. "Anfa") score ~89 against edit-distance-1
# unrelated words, so keep the fuzzy backstop strict. All known typos are covered
# by the explicit alias map above; fuzzy only catches unseen variants.
_ZONE_FUZZY_THRESHOLD = 90


def _zone_candidates() -> list[str]:
    return [str(z) for z in _areas().get("area_name", pd.Series(dtype=str)).dropna().astype(str).unique()]


def _resolve_zone_mentions(question: str) -> list[dict]:
    """Resolve zone mentions (exact, alias, or fuzzy) to canonical names with metadata."""
    normalized = _normalize_text(question)
    candidates = _zone_candidates()
    norm_to_canon = {_normalize_text(z): z for z in candidates}
    found: dict[str, dict] = {}

    def add(canon: str, match_type: str, position: int) -> None:
        if canon not in found or position < found[canon]["position"]:
            found[canon] = {"canonical": canon, "match_type": match_type, "position": position}

    padded = f" {normalized} "

    # 1. Exact canonical names (word-boundary, so "anfa" does NOT match "anfal").
    for nz, canon in norm_to_canon.items():
        pos = padded.find(f" {nz} ")
        if pos != -1:
            add(canon, "exact", pos)

    # 2. Known aliases / typos (word-boundary, longest alias first).
    for alias in sorted(_ZONE_ALIASES, key=len, reverse=True):
        canon = _ZONE_ALIASES[alias]
        if canon not in candidates:
            continue
        if f" {alias} " in padded:
            add(canon, "alias", normalized.find(alias))

    # 3. Fuzzy backstop on token windows (catches unseen typos like "maarifa").
    tokens = [t for t in normalized.split() if len(t) >= 4 and t not in _ZONE_FUZZY_BLOCKLIST]
    norm_names = list(norm_to_canon.keys())
    for size in (1, 2, 3):
        for i in range(len(tokens) - size + 1):
            window = " ".join(tokens[i : i + size])
            if window in _ZONE_FUZZY_BLOCKLIST:
                continue
            best_name, best_score = None, 0.0
            for nz in norm_names:
                score = fuzz.token_sort_ratio(window, nz)
                if score > best_score:
                    best_name, best_score = nz, score
            if best_name and best_score >= _ZONE_FUZZY_THRESHOLD:
                add(norm_to_canon[best_name], "fuzzy", normalized.find(window))

    return sorted(found.values(), key=lambda item: item["position"])


def _zones_from_question(question: str) -> list[str]:
    return [match["canonical"] for match in _resolve_zone_mentions(question)]


def _is_comparison_question(normalized: str) -> bool:
    return any(term in normalized.split() for term in ("compare", "comparer", "comparaison", "versus"))


def build_zone_comparison_answer(question: str, zones: list[str]) -> dict:
    areas = _areas()
    selected = areas[areas["area_name"].isin(zones)].copy()
    selected = selected.set_index("area_name").loc[zones].reset_index()
    snapshot = get_market_snapshot()

    rows = []
    opportunities = []
    for _, row in selected.iterrows():
        zone = str(row["area_name"])
        population = _safe_int(row.get("population_est"))
        facilities = _safe_int(row.get("medical_facilities_count"))
        coverage = _safe_float(row.get("facilities_per_100k"))
        undersupply = _safe_float(row.get("undersupply_index"))
        access = _safe_float(row.get("accessibility_index"))
        rows.append(
            f"| {zone} | {_format_int(population)} | {facilities} | "
            f"{coverage:.1f} | {undersupply:.1f}/100 | {access:.1f}/100 |"
        )
        opportunities.append(
            {
                "zone": zone,
                "category": "Comparaison territoriale",
                "score": _safe_float(row.get("investment_score")),
                "risk": 0,
                "supply_gap": undersupply,
                "competition_level": "N/A",
                "providers": facilities,
                "providers_per_100k": coverage,
                "population": population,
                "density": _safe_float(row.get("population_density")),
            }
        )

    lowest_coverage = min(opportunities, key=lambda item: item["providers_per_100k"])
    answer = (
        f"## Comparaison : {' vs '.join(zones)}\n\n"
        "| Quartier | Population | Établissements | Établissements / 100k | Sous-offre | Accessibilité |\n"
        "|---|---:|---:|---:|---:|---:|\n"
        + "\n".join(rows)
        + "\n\n"
        "## Lecture comparative\n\n"
        f"- **{lowest_coverage['zone']}** a la couverture médicale observée la plus faible "
        f"({lowest_coverage['providers_per_100k']:.1f} équipements pour 100 000 habitants).\n"
        "- Le choix final dépend de la spécialité visée : une pharmacie, une clinique et un laboratoire "
        "n'utilisent pas les mêmes pondérations de demande et de concurrence.\n"
        "- Les comptages OSM doivent être validés sur le terrain avant une décision d'investissement."
    )
    return {
        "question": question,
        "answer_markdown": answer,
        "top_zone": lowest_coverage["zone"],
        "score": lowest_coverage["supply_gap"],
        "risk": 0,
        "category": "Comparaison territoriale",
        "sources": snapshot["sources"],
        "kpis": [
            {"label": "Zones comparées", "value": str(len(zones))},
            {"label": "Couverture la plus faible", "value": lowest_coverage["zone"]},
            {"label": "Équipements / 100k", "value": f"{lowest_coverage['providers_per_100k']:.1f}"},
            {"label": "Sous-offre", "value": f"{lowest_coverage['supply_gap']:.1f}/100"},
        ],
        "map_focus": _zone_focus(lowest_coverage["zone"]),
        "related_opportunities": opportunities,
        "retrieved_contexts": [],
        "rag_status": "zone_comparison",
        "suggested_view": _preferred_view_from_question(question),
    }


def _is_risk_question(words: set[str]) -> bool:
    return bool(words & {"risque", "risques", "danger", "dangers", "vigilance", "limites"})


def build_zone_risk_answer(question: str, zone: str) -> dict:
    area = _area_row(zone)
    snapshot = get_market_snapshot()
    coverage = _safe_float(area.get("facilities_per_100k"))
    undersupply = _safe_float(area.get("undersupply_index"))
    access = _safe_float(area.get("accessibility_index"))
    low_competition = _safe_float(area.get("low_competition_index"))
    facilities = _safe_int(area.get("medical_facilities_count"))
    population = _safe_int(area.get("population_est"))
    vigilance = round(
        0.45 * undersupply
        + 0.30 * (100 - access)
        + 0.25 * (100 - low_competition),
        1,
    )
    answer = (
        f"## Risques à {zone}\n\n"
        f"Le principal signal de vigilance est la **sous-offre médicale ({undersupply:.1f}/100)**. "
        f"La zone compte **{facilities} établissements cartographiés** pour {_format_int(population)} habitants, "
        f"soit **{coverage:.1f} pour 100 000 habitants**.\n\n"
        "## Points de vigilance\n\n"
        f"- **Couverture des données :** les établissements absents d'OpenStreetMap peuvent fausser le diagnostic.\n"
        f"- **Accessibilité :** indice de {access:.1f}/100 ; vérifier transport, stationnement et accès PMR.\n"
        f"- **Concurrence :** indice de faible concurrence de {low_competition:.1f}/100, à confirmer par une visite terrain.\n"
        "- **Viabilité commerciale :** les loyers, revenus, flux patients et prescriptions ne sont pas présents dans le jeu de données.\n"
        "- **Réglementation :** les autorisations dépendent du type d'établissement médical envisagé.\n\n"
        f"**Indice territorial de vigilance : {vigilance:.1f}/100.** Il s'agit d'un signal de présélection, "
        "pas d'une mesure financière ou réglementaire définitive."
    )
    return {
        "question": question,
        "answer_markdown": answer,
        "top_zone": zone,
        "score": undersupply,
        "risk": vigilance,
        "category": "Analyse territoriale des risques",
        "sources": snapshot["sources"],
        "kpis": [
            {"label": "Vigilance", "value": f"{vigilance:.1f}/100"},
            {"label": "Sous-offre", "value": f"{undersupply:.1f}/100"},
            {"label": "Équipements / 100k", "value": f"{coverage:.1f}"},
            {"label": "Accessibilité", "value": f"{access:.1f}/100"},
        ],
        "map_focus": _zone_focus(zone),
        "related_opportunities": [],
        "retrieved_contexts": [],
        "rag_status": "zone_risk_analysis",
        "suggested_view": _preferred_view_from_question(question),
    }


def _quick_response(
    *,
    question: str,
    markdown: str,
    status: str,
    suggested_view: str = "intelligence",
    category: str = "General",
    top_zone: str = "Casablanca",
    score: float = 0,
    risk: float = 0,
    kpis: list[dict] | None = None,
) -> dict:
    snapshot = get_market_snapshot()
    return {
        "question": question,
        "answer_markdown": markdown,
        "top_zone": top_zone,
        "score": score,
        "risk": risk,
        "category": category,
        "sources": snapshot["sources"],
        "kpis": kpis or _snapshot_kpis(snapshot),
        "map_focus": _zone_focus(top_zone),
        "related_opportunities": [],
        "retrieved_contexts": [],
        "rag_status": status,
        "suggested_view": suggested_view,
    }


def _top_opportunity_for(category: str) -> dict:
    opportunities = get_opportunities(category)
    return opportunities[0] if opportunities else {}


# --- Grounding guards (prevent fabricated answers on unknown zones / counts) ---

_COUNT_TOKENS = {"combien", "nombre"}

_ZONE_FACT_COLUMNS = [
    ("pharmacies", "pharmacy_count"),
    ("cliniques", "clinic_count"),
    ("hôpitaux", "hospital_count"),
    ("cabinets médicaux", "doctor_count"),
    ("dentistes", "dentist_count"),
    ("vétérinaires", "veterinary_count"),
    ("laboratoires", "laboratory_count"),
    ("radiologie", "radiology_count"),
    ("centres de santé", "health_center_count"),
]

_UNKNOWN_ZONE_RE = re.compile(
    r"(?:quartier|zone|arrondissement|district)\s+(?:de\s+|du\s+|des\s+|d['’]\s*)"
    r"([a-zA-Zà-ÿÀ-ß][a-zA-Zà-ÿÀ-ß'’\- ]{2,30})",
    re.IGNORECASE,
)
_ZONE_REF_DROP = {"a", "au", "aux", "dans", "pour", "sur", "casablanca", "ville", "the"}


def _explicit_unknown_zone(question: str) -> str | None:
    """Return a place name explicitly referenced as a quartier/zone but absent from the dataset."""
    if _zones_from_question(question) or _location_fact_from_question(question):
        return None
    match = _UNKNOWN_ZONE_RE.search(question)
    if not match:
        return None
    tokens = [w for w in _normalize_text(match.group(1)).split() if w not in _ZONE_REF_DROP]
    if not tokens:
        return None
    return " ".join(tokens[:2]).title()


def build_unknown_zone_answer(question: str, zone_name: str) -> dict:
    zones = sorted(_areas().get("area_name", pd.Series(dtype=str)).dropna().astype(str).unique())
    zone_list = ", ".join(zones) if zones else "non disponible"
    markdown = (
        f"## Zone non couverte : {zone_name}\n\n"
        f"Je ne trouve pas **{zone_name}** dans le périmètre de données actuel. "
        "Pour éviter une recommandation non fondée, je ne génère pas de score pour une "
        "zone inconnue.\n\n"
        f"**Zones actuellement analysées à Casablanca :** {zone_list}.\n\n"
        "Reformulez avec l'une de ces zones, ou demandez un classement global "
        "(*Où ouvrir une pharmacie à faible concurrence ?*)."
    )
    return _quick_response(
        question=question,
        markdown=markdown,
        status="unknown_zone",
        category="Information géographique",
        top_zone="Casablanca",
    )


def build_arrondissement_gap_answer(question: str, gap: dict) -> dict:
    name = gap.get("name_ascii") or gap.get("name") or "Arrondissement non couvert"
    markdown = (
        f"## Arrondissement officiel non encore scoré : {name}\n\n"
        f"**{name}** figure dans la taxonomie officielle de la Préfecture de Casablanca, "
        "mais il n'a pas encore de polygone, population, ni table de scoring dédiée dans le dataset actif.\n\n"
        "Je ne dois donc pas inventer de score d'opportunité ou de supply gap pour cette zone. "
        "Pour l'intégrer proprement, il faut ajouter ses frontières, estimer sa population, assigner les POIs "
        "par polygone, puis recalculer les indicateurs et réindexer le RAG.\n\n"
        f"**Préfecture source :** {gap.get('prefecture', 'non disponible')}.\n\n"
        "Zones actuellement scorées : "
        f"{', '.join(sorted(_zone_candidates()))}.\n\n"
        "---\n"
        "*Source : taxonomie des arrondissements de Casablanca + périmètre Invest Search actuel.*"
    )
    response = _quick_response(
        question=question,
        markdown=markdown,
        status="coverage_gap_arrondissement",
        category="Coverage Gap",
        top_zone=str(name),
        kpis=[
            {"label": "Arrondissement", "value": str(name)},
            {"label": "Statut", "value": "Officiel, non scoré"},
            {"label": "Action", "value": "Ajouter frontières + population"},
        ],
    )
    response["sources"] = [
        {
            "title": "Taxonomie arrondissements",
            "subtitle": gap.get("source_url", "Source officielle / Wikipedia"),
            "kind": "official",
            "metric": "coverage gap",
            "confidence": 0.78,
        }
    ]
    response["suggested_questions"] = [
        "Comparer Anfa et Maarif pour une clinique",
        "Où ouvrir une pharmacie à faible concurrence ?",
        "Afficher les gaps de couverture des arrondissements",
    ]
    return response


def build_coverage_gaps_answer(question: str) -> dict:
    gaps = _official_arrondissement_gaps()
    if gaps:
        gap_lines = "\n".join(
            f"- **{gap.get('name_ascii') or gap.get('name')}** — {gap.get('prefecture', 'préfecture non disponible')}"
            for gap in gaps
        )
        markdown = (
            "## Arrondissements officiels à intégrer\n\n"
            "Le contrôle compare la taxonomie officielle avec les zones actuellement scorées.\n\n"
            f"{gap_lines}\n\n"
            "Ces arrondissements doivent recevoir leurs frontières, population et indicateurs avant scoring.\n\n"
            "---\n*Source : taxonomie des arrondissements + périmètre Invest Search actuel.*"
        )
        action = "Ajouter au pipeline"
    else:
        markdown = (
            "## Couverture complète des arrondissements\n\n"
            "**Aucun gap n'est détecté.** Les 16 arrondissements officiels de Casablanca disposent "
            "d'une population HCP 2024, d'un polygone administratif et d'indicateurs recalculés.\n\n"
            "---\n*Sources : HCP RGPH 2024 et frontières administratives OpenStreetMap.*"
        )
        action = "Aucune"
    response = _quick_response(
        question=question,
        markdown=markdown,
        status="coverage_gaps",
        category="Coverage Gap",
        top_zone="Casablanca",
        kpis=[
            {"label": "Gaps détectés", "value": str(len(gaps))},
            {"label": "Zones scorées", "value": str(len(_zone_candidates()))},
            {"label": "Action", "value": action},
        ],
    )
    response["sources"] = [
        {
            "title": "Taxonomie arrondissements",
            "subtitle": "Liste officielle extraite et normalisée",
            "kind": "official",
            "metric": f"{len(gaps)} gaps",
            "confidence": 0.78,
        }
    ]
    return response


def _sector_category_counts(sector: str, zone: str | None = None) -> list[dict]:
    df = _multisector_facilities()
    if df.empty:
        return []
    sector_df = df[df["sector"] == sector]
    if zone:
        sector_df = sector_df[sector_df["district"] == zone]
    return [
        {"category": str(category), "count": int(count)}
        for category, count in sector_df["category"].value_counts().head(6).items()
    ]


def build_sector_opportunity_answer(
    question: str,
    sector: str,
    zone: str | None = None,
    subcategory: str | None = None,
) -> dict | None:
    if sector not in SECTORS or sector == "medical":
        return None
    opportunities = get_sector_opportunities(sector, subcategory=subcategory)
    if not opportunities:
        return None

    sector_label = SECTORS[sector].label_fr
    activity_label = _sector_category_label(sector, subcategory)
    summary = get_sector_summary()
    sector_info = next((item for item in summary["sectors"] if item["key"] == sector), {})
    if zone:
        selected = next((item for item in opportunities if item["zone"] == zone), None)
        if not selected:
            return None
        status = "sector_zone_analysis"
    else:
        selected = opportunities[0]
        zone = selected["zone"]
        status = "sector_opportunity"

    category_counts = _sector_category_counts(sector, zone if status == "sector_zone_analysis" else None)
    category_text = ", ".join(f"{item['category']} ({item['count']})" for item in category_counts[:4]) or "non disponible"
    unknown_count = sector_info.get("unknown_count", 0)
    poi_count = sector_info.get("poi_count", 0)
    assigned_count = sector_info.get("assigned_count", 0)
    score = _safe_float(selected.get("score"))
    risk = _safe_float(selected.get("risk"))
    supply_gap = _safe_float(selected.get("supply_gap"))
    providers = _safe_int(selected.get("providers"))
    per100k = _safe_float(selected.get("providers_per_100k"))
    competition_level = str(selected.get("competition_level") or "Non disponible")
    weights_version = str(selected.get("weights_version") or "sector_weights_v1")
    if subcategory:
        poi_count = _safe_int(selected.get("total_pois_subcategory"))
        assigned_count = _safe_int(selected.get("assigned_pois_subcategory"))
        unknown_count = max(0, poi_count - assigned_count)
        category_text = f"{activity_label} ({providers} dans la zone)"
        if poi_count == 0:
            response = _quick_response(
                question=question,
                status="sector_data_gap",
                category=sector,
                top_zone=zone if status == "sector_zone_analysis" else "Casablanca",
                markdown=(
                    f"## Données insuffisantes pour {activity_label}\n\n"
                    f"Aucun POI **{activity_label}** exploitable n'est actuellement classé dans le jeu "
                    "OpenStreetMap multi-sectoriel. Je ne recommande donc aucune zone sur cette base.\n\n"
                    "Une collecte ciblée et une validation terrain sont nécessaires avant de calculer "
                    "un score d'implantation fiable."
                ),
            )
            response.update({
                "sector": sector,
                "subcategory": subcategory,
                "subcategory_label": activity_label,
            })
            return response
    try:
        contexts, _ = hybrid_search(
            query=f"{question} {sector} {subcategory or ''} {activity_label} {zone} subcategory_supply zone profile",
            top_k=4,
        )
    except Exception:
        contexts = []
    source_cards = _sector_source_cards(sector)
    if contexts:
        source_cards = _build_source_cards(contexts[:2]) + source_cards

    if status == "sector_zone_analysis":
        title = f"{activity_label.capitalize()} à {zone}"
        recommendation = (
            f"**{zone}** compte **{providers} POIs cartographiés** pour l'activité **{activity_label}** "
            f"({per100k}/100k hab.). Le score d'activité calibré est **{score}/100** "
            f"avec une concurrence **{competition_level.lower()}**."
        )
    else:
        title = f"Opportunité {activity_label} à Casablanca"
        recommendation = (
            f"Pour l'activité **{activity_label}**, la zone prioritaire est **{zone}** "
            f"avec un score calibré de **{score}/100**, une concurrence "
            f"**{competition_level.lower()}** et un supply gap de **{supply_gap}/100**."
        )

    alternatives = [
        f"{item['zone']} ({item['score']}/100, {item['providers']} POIs)"
        for item in opportunities[1:4]
        if item["zone"] != zone
    ]
    alternatives_text = "; ".join(alternatives) or "non disponible"
    comparison_zone = next((item["zone"] for item in opportunities if item["zone"] != zone), None)
    if not comparison_zone:
        comparison_zone = "Anfa" if zone != "Anfa" else "Maarif"
    markdown = (
        f"## {title}\n\n"
        f"{recommendation}\n\n"
        "## Lecture des données\n\n"
        f"- **POIs comparables collectés :** {poi_count:,} au total, dont {assigned_count:,} assignés à une zone connue.\n"
        f"- **Points hors zone connue :** {unknown_count:,}. Ils peuvent sous-estimer certaines zones.\n"
        f"- **Catégories dominantes :** {category_text}.\n"
        f"- **Méthode :** score calibré via `data/processed/{'subcategory_supply.csv' if subcategory else 'sector_supply.csv'}` "
        f"({weights_version}) : demande, pouvoir d'achat proxy, faible concurrence relative et confiance OSM.\n"
        f"- **Niveau de concurrence :** {competition_level} selon les seuils propres au secteur.\n\n"
        "## KPIs\n\n"
        "| Indicateur | Valeur |\n|---|---:|\n"
        f"| Zone | {zone} |\n"
        f"| Secteur | {sector_label} |\n"
        f"| Activité | {activity_label} |\n"
        f"| POIs comparables | {providers} |\n"
        f"| POIs / 100k hab. | {per100k} |\n"
        f"| Concurrence | {competition_level} |\n"
        f"| Supply gap | {supply_gap}/100 |\n"
        f"| Score sectoriel calibré | {score}/100 |\n"
        f"| Risque data | {risk}/100 |\n\n"
        "## Alternatives à comparer\n\n"
        f"{alternatives_text}.\n\n"
        "## Limites\n\n"
        "Cette analyse multi-sectorielle est **indicative** : les POIs viennent d'OpenStreetMap, "
        "la concurrence informelle peut être sous-cartographiée, et certains arrondissements officiels "
        "ne sont pas encore scorés séparément. À valider avec terrain, loyers, flux piéton, ticket moyen "
        "et données commerciales.\n\n"
        "---\n"
        f"*Sources : OSM multi-sectoriel, `{'subcategory_supply.csv' if subcategory else 'sector_supply.csv'}`, "
        "profils zone-sectoriels RAG et taxonomie Casablanca.*"
    )
    return {
        "question": question,
        "answer_markdown": markdown,
        "top_zone": zone,
        "score": score,
        "risk": risk,
        "category": sector,
        "sector": sector,
        "subcategory": subcategory,
        "subcategory_label": activity_label if subcategory else None,
        "sources": source_cards,
        "kpis": [
            {"label": "Secteur", "value": sector_label},
            {"label": "Activité", "value": activity_label},
            {"label": "POIs comparables", "value": f"{poi_count:,}"},
            {"label": "Zone", "value": zone},
            {"label": "Score", "value": f"{score}/100"},
            {"label": "Concurrence", "value": competition_level},
            {"label": "Supply gap", "value": f"{supply_gap}/100"},
            {"label": "Risque data", "value": f"{risk}/100"},
        ],
        "map_focus": _zone_focus(zone),
        "related_opportunities": opportunities[:5],
        "retrieved_contexts": contexts,
        "rag_status": status,
        "suggested_view": _preferred_view_from_question(question),
        "suggested_questions": [
            f"Combien de {activity_label} à {zone} ?",
            f"Comparer {zone} et {comparison_zone} pour {activity_label}",
            "Quels arrondissements officiels ne sont pas encore scorés ?",
        ],
    }


def build_sector_comparison_answer(
    question: str,
    sector: str,
    zones: list[str],
    subcategory: str | None = None,
) -> dict | None:
    if sector not in SECTORS or sector == "medical" or len(zones) < 2:
        return None
    opportunities = get_sector_opportunities(sector, subcategory=subcategory)
    if not opportunities:
        return None
    selected = [item for item in opportunities if item["zone"] in zones]
    if len(selected) < 2:
        return None

    activity_label = _sector_category_label(sector, subcategory)
    sector_label = SECTORS[sector].label_fr
    selected = sorted(selected, key=lambda item: zones.index(item["zone"]))
    recommended = max(selected, key=lambda item: item.get("score", 0))
    rows = [
        f"| {item['zone']} | {item['providers']} | {item['providers_per_100k']} | "
        f"{item['competition_level']} | {item['supply_gap']}/100 | {item['score']}/100 | {item['risk']}/100 |"
        for item in selected
    ]
    try:
        contexts, _ = hybrid_search(
            query=f"{question} comparer {sector} {subcategory or ''} {activity_label} {' '.join(zones)} subcategory_supply zone profile",
            top_k=4,
        )
    except Exception:
        contexts = []
    source_cards = _sector_source_cards(sector)
    if contexts:
        source_cards = _build_source_cards(contexts[:2]) + source_cards

    markdown = (
        f"## Comparaison {activity_label} : {' vs '.join(zones)}\n\n"
        "| Zone | POIs comparables | POIs / 100k | Concurrence | Supply gap | Score | Risque data |\n"
        "|---|---:|---:|---|---:|---:|---:|\n"
        + "\n".join(rows)
        + "\n\n"
        "## Lecture comparative\n\n"
        f"- **{recommended['zone']}** ressort comme la meilleure option pour **{activity_label}** "
        f"avec un score de **{recommended['score']}/100**.\n"
        f"- Le diagnostic compare uniquement l'activité **{activity_label}** dans le secteur **{sector_label}**, "
        "pas l'ensemble du marché médical.\n"
        "- Le choix final doit être validé avec loyers, flux piéton, ticket moyen, visibilité et concurrents non cartographiés.\n\n"
        "---\n"
        "*Sources : `subcategory_supply.csv`, `sector_supply.csv`, profils zone-sectoriels RAG et OpenStreetMap.*"
    )
    return {
        "question": question,
        "answer_markdown": markdown,
        "top_zone": recommended["zone"],
        "score": recommended["score"],
        "risk": recommended["risk"],
        "category": sector,
        "sector": sector,
        "subcategory": subcategory,
        "subcategory_label": activity_label,
        "sources": source_cards,
        "kpis": [
            {"label": "Secteur", "value": sector_label},
            {"label": "Activité", "value": activity_label},
            {"label": "Zones comparées", "value": str(len(selected))},
            {"label": "Meilleure zone", "value": recommended["zone"]},
            {"label": "Score", "value": f"{recommended['score']}/100"},
            {"label": "Concurrence", "value": recommended["competition_level"]},
        ],
        "map_focus": _zone_focus(recommended["zone"]),
        "related_opportunities": selected,
        "retrieved_contexts": contexts,
        "rag_status": "sector_comparison",
        "suggested_view": _preferred_view_from_question(question),
        "suggested_questions": [
            f"Afficher la carte pour {activity_label}",
            f"Quel budget pour {activity_label} à {recommended['zone']} ?",
            f"Comparer {recommended['zone']} avec une autre zone",
        ],
    }


_TOP_ZONE_NOUNS = {
    "quartier", "quartiers", "zone", "zones", "secteur", "secteurs",
    "arrondissement", "arrondissements", "endroit", "endroits",
    "emplacement", "emplacements", "coin", "coins",
}
_ZONE_COUNT_WORDS = {"deux": 2, "trois": 3, "quatre": 4, "cinq": 5}


def _requested_zone_count(normalized: str) -> int | None:
    """Detect a request for the top-N best zones ("les deux meilleurs quartiers",
    "top 3 zones", "meilleures zones"). Returns N in 2..5, or None.

    Singular "le meilleur quartier" is intentionally NOT matched (it keeps the
    existing single-zone recommendation path).
    """
    tokens = normalized.split()
    token_set = set(tokens)
    if not (_TOP_ZONE_NOUNS & token_set):
        return None
    plural_best = bool(token_set & {"meilleurs", "meilleures"})
    has_top = bool(token_set & {"top", "classement", "classer", "classez"})
    num = None
    for tok in tokens:
        if tok in _ZONE_COUNT_WORDS:
            num = _ZONE_COUNT_WORDS[tok]
            break
        if tok.isdigit() and 2 <= int(tok) <= 5:
            num = int(tok)
            break
    has_best = any(t.startswith("meilleur") for t in tokens)
    if not (plural_best or has_top or (num and has_best)):
        return None
    return num or 3


def build_top_zones_answer(
    question: str,
    sector: str | None,
    subcategory: str | None,
    category: str,
    top_n: int,
) -> dict | None:
    """Ranked top-N zones for an activity (multi-sector OR medical)."""
    if sector and sector in SECTORS and sector != "medical":
        opportunities = get_sector_opportunities(sector, subcategory=subcategory, limit=99)
        activity_label = _sector_category_label(sector, subcategory)
        status = "sector_top_zones"
        base_sources = _sector_source_cards(sector)
        source_note = "`sector_supply.csv`, OSM multi-sectoriel"
    else:
        opportunities = get_opportunities(category, limit=99)
        activity_label = CATEGORY_DISPLAY_FR.get(category, "établissement")
        status = "top_zones"
        base_sources = []
        source_note = "indicateurs santé OSM nettoyés + offre publique MSPS"
        sector = None
    if len(opportunities) < 2:
        return None
    top_n = max(2, min(top_n, len(opportunities), 5))
    top = opportunities[:top_n]

    try:
        contexts, _ = hybrid_search(
            query=f"{question} {activity_label} {' '.join(o['zone'] for o in top)} meilleures zones classement",
            top_k=4,
        )
    except Exception:
        contexts = []
    source_cards = (_build_source_cards(contexts[:2]) if contexts else []) + base_sources

    rows = [
        f"| {i} | **{o['zone']}** | {o['score']}/100 | "
        f"{_competition_label_fr(str(o['competition_level']))} | {o['supply_gap']}/100 | {o['providers']} |"
        for i, o in enumerate(top, start=1)
    ]
    lead = "; ".join(f"**{o['zone']}** ({o['score']}/100)" for o in top)
    markdown = (
        f"## Top {top_n} quartiers pour {activity_label} à Casablanca\n\n"
        f"Classés par score d'opportunité : {lead}.\n\n"
        "| # | Quartier | Score | Concurrence | Supply gap | POIs comparables |\n"
        "|---|---|---:|---|---:|---:|\n"
        + "\n".join(rows)
        + "\n\n## Lecture\n\n"
        f"- **{top[0]['zone']}** arrive en tête (score {top[0]['score']}/100, concurrence "
        f"{_competition_label_fr(str(top[0]['competition_level']))}).\n"
        f"- **{top[1]['zone']}** suit (score {top[1]['score']}/100) — bon plan B ou 2ᵉ implantation.\n"
        "- Le score combine demande, pouvoir d'achat proxy, faible concurrence relative et confiance OSM.\n\n"
        "## Limites\n\n"
        "Classement **indicatif** : POIs OpenStreetMap (concurrence informelle possible sous-cartographiée), "
        "certains arrondissements pas encore scorés séparément. À valider avec terrain, loyers, flux piéton "
        "et ticket moyen.\n\n"
        "---\n"
        f"*Sources : {source_note}, profils zone-sectoriels RAG.*"
    )
    kpis = [
        {"label": "Activité", "value": activity_label},
        {"label": "Zones classées", "value": str(top_n)},
    ]
    for o in top:
        kpis.append({"label": o["zone"], "value": f"{o['score']}/100"})
    return {
        "question": question,
        "answer_markdown": markdown,
        "top_zone": top[0]["zone"],
        "score": top[0]["score"],
        "risk": top[0]["risk"],
        "category": sector or category,
        "sector": sector,
        "subcategory": subcategory,
        "subcategory_label": activity_label if (sector and subcategory) else None,
        "sources": source_cards,
        "kpis": kpis,
        "map_focus": _zone_focus(top[0]["zone"]),
        "related_opportunities": top,
        "retrieved_contexts": contexts,
        "rag_status": status,
        "suggested_view": _preferred_view_from_question(question),
        "suggested_questions": [
            f"Comparer {top[0]['zone']} et {top[1]['zone']} pour {activity_label}",
            f"Quel budget pour {activity_label} à {top[0]['zone']} ?",
            f"Combien de {activity_label} à {top[0]['zone']} ?",
        ],
    }


def _is_count_question(words: set[str], normalized: str) -> bool:
    return bool(words & _COUNT_TOKENS) or "combien de" in normalized or "nombre de" in normalized


def build_zone_facts_answer(question: str, zone: str) -> dict | None:
    area = _area_row(zone)
    if not area:
        return None
    snapshot = get_market_snapshot()
    total = _safe_int(area.get("medical_facilities_count"))
    population = _safe_int(area.get("population_est"))
    rows = [
        f"| {label.capitalize()} | {_safe_int(area.get(col))} |"
        for label, col in _ZONE_FACT_COLUMNS
        if col in area
    ]
    markdown = (
        f"## Établissements médicaux recensés à {zone}\n\n"
        f"D'après les données actuelles (OpenStreetMap nettoyé), **{zone}** compte "
        f"**{total} établissements médicaux cartographiés** pour {_format_int(population)} habitants.\n\n"
        "| Catégorie | Nombre recensé |\n|---|---:|\n" + "\n".join(rows) + "\n\n"
        "## Limite importante\n\n"
        "Ces comptages reposent sur OpenStreetMap et peuvent **sous-estimer** les établissements "
        "non cartographiés. Un résultat faible peut refléter une donnée incomplète plutôt qu'une "
        "absence réelle. À valider sur le terrain et à croiser avec le ministère de la Santé.\n\n"
        "---\n"
        "*Source : établissements OpenStreetMap nettoyés et indicateurs zonaux Invest Search.*"
    )
    return {
        "question": question,
        "answer_markdown": markdown,
        "top_zone": zone,
        "score": _safe_float(area.get("investment_score")),
        "risk": 0,
        "category": "Recensement par zone",
        "sources": snapshot["sources"],
        "kpis": [
            {"label": "Établissements (total)", "value": str(total)},
            {"label": "Pharmacies", "value": str(_safe_int(area.get("pharmacy_count")))},
            {"label": "Population", "value": f"{_format_int(population)} hab."},
            {"label": "Équipements / 100k", "value": f"{_safe_float(area.get('facilities_per_100k'))}"},
        ],
        "map_focus": _zone_focus(zone),
        "related_opportunities": [],
        "retrieved_contexts": [],
        "rag_status": "zone_facts",
        "suggested_view": _preferred_view_from_question(question),
    }


def _is_gap_competition_question(words: set[str], normalized: str) -> bool:
    if words & {"concurrence", "concurrent", "concurrents", "saturation", "opportunite",
                "opportunites", "analyser", "potentiel"}:
        return True
    return any(p in normalized for p in ("supply gap", "supply-gap", "offre et demande", "sous offre"))


def _is_vague_investment(words: set[str], normalized: str) -> bool:
    return ("investir" in words or "investissement" in words
            or "je veux investir" in normalized or "ou investir" in normalized)


def build_zone_gap_competition_answer(question: str, zone: str, category: str) -> dict | None:
    """Zone- AND category-specific concurrence / supply-gap analysis (never the global top)."""
    areas = _areas()
    specialty = _specialty()
    category = _category_or_default(category)
    scores = compute_opportunity_scores(areas, specialty, category)
    if scores.empty:
        return None
    ranked = scores.reset_index(drop=True)
    match = ranked[ranked["area_name"] == zone]
    if match.empty:
        return None
    r = match.iloc[0]
    snapshot = get_market_snapshot()
    area = _area_row(zone)

    cat_fr = CATEGORY_DISPLAY_FR.get(category, category)
    score = _safe_float(r.get("investment_readiness_score"))
    risk = _safe_float(r.get("risk_score"))
    supply_gap = _safe_float(r.get("supply_gap"))
    competition = r.get("competition_level", "N/A")
    comp_fr = _competition_label_fr(competition)
    providers = _safe_int(r.get("providers_count"))
    per100k = _safe_float(r.get("providers_per_100k"))
    data_confidence = _safe_float(r.get("data_confidence"))
    population = _safe_int(area.get("population_est"))
    density = _safe_float(area.get("population_density"))

    rank_idx = ranked.index[ranked["area_name"] == zone].tolist()
    rank = (rank_idx[0] + 1) if rank_idx else 0
    total = len(ranked)
    best = ranked.iloc[0]
    alternative = ""
    if str(best["area_name"]) != zone:
        alternative = (
            f"\n\nÀ titre de repère, la zone la mieux notée pour cette catégorie est "
            f"**{best['area_name']}** ({_safe_float(best.get('investment_readiness_score'))}/100). "
            f"Demandez explicitement une comparaison si vous souhaitez l'opposer à {zone}."
        )

    markdown = (
        f"## {cat_fr.capitalize()} à {zone}\n\n"
        f"Analyse de **concurrence et supply gap** pour une **{cat_fr}** à **{zone}** [1].\n\n"
        f"- **Score d'opportunité (catégorie) :** {score}/100 — rang **{rank}/{total}** parmi les zones.\n"
        f"- **Supply gap :** {supply_gap}/100 (plus l'indice est élevé, plus l'offre est insuffisante).\n"
        f"- **Concurrence :** {comp_fr} — {providers} prestataires comparables recensés ({per100k}/100k hab.).\n"
        f"- **Confiance des données :** {data_confidence}/100.\n"
        f"- **Risque :** {risk}/100.\n\n"
        "## Indicateurs clés\n\n"
        "| Indicateur | Valeur |\n|---|---:|\n"
        f"| Zone | {zone} |\n"
        f"| Catégorie | {cat_fr} |\n"
        f"| Population | {_format_int(population)} hab. |\n"
        f"| Score d'opportunité | {score}/100 |\n"
        f"| Supply gap | {supply_gap}/100 |\n"
        f"| Concurrence | {comp_fr} ({providers}) |\n"
        f"| Confiance des données | {data_confidence}/100 |\n"
        f"| Risque | {risk}/100 |\n\n"
        "## Limites\n\n"
        "Les comptages reposent sur OpenStreetMap et peuvent sous-estimer la concurrence réelle "
        "(acteurs informels ou non cartographiés). Validez sur le terrain : loyers, flux patients, "
        "autorisations sanitaires."
        f"{alternative}\n\n"
        "---\n*Source : moteur de scoring Invest Search + établissements OpenStreetMap.*"
    )
    return {
        "question": question,
        "answer_markdown": markdown,
        "top_zone": zone,
        "score": score,
        "risk": risk,
        "category": category,
        "sources": snapshot["sources"],
        "kpis": [
            {"label": "Zone", "value": zone},
            {"label": "Score", "value": f"{score}/100"},
            {"label": "Supply gap", "value": f"{supply_gap}/100"},
            {"label": "Concurrence", "value": f"{comp_fr} ({providers})"},
            {"label": "Confiance données", "value": f"{data_confidence}/100"},
        ],
        "map_focus": _zone_focus(zone),
        "related_opportunities": [
            {
                "zone": zone,
                "category": category,
                "score": score,
                "risk": risk,
                "supply_gap": supply_gap,
                "competition_level": competition,
                "providers": providers,
                "providers_per_100k": per100k,
                "confidence": data_confidence,
                "population": population,
                "density": density,
            }
        ],
        "retrieved_contexts": [],
        "rag_status": "zone_gap_competition",
        "suggested_view": _preferred_view_from_question(question),
    }


def build_zone_clarification_answer(question: str, zone: str) -> dict | None:
    """Zone known but no category: give a general coverage overview and ask for the type."""
    area = _area_row(zone)
    if not area:
        return None
    snapshot = get_market_snapshot()
    total = _safe_int(area.get("medical_facilities_count"))
    per100k = _safe_float(area.get("facilities_per_100k"))
    undersupply = _safe_float(area.get("undersupply_index"))
    population = _safe_int(area.get("population_est"))
    markdown = (
        f"## Couverture médicale générale — {zone}\n\n"
        f"**{zone}** compte **{total} établissements médicaux cartographiés** pour "
        f"{_format_int(population)} habitants (**{per100k}/100k**), avec un indice de sous-offre "
        f"globale de **{undersupply}/100** [1].\n\n"
        "La concurrence et le supply gap dépendent fortement du **type d'établissement** : "
        "une pharmacie, une clinique, un cabinet dentaire ou un laboratoire n'ont ni la même "
        "offre ni la même demande.\n\n"
        "## Précisez votre projet\n\n"
        f"**Pour quel type d'établissement voulez-vous le supply gap à {zone} ?** "
        "pharmacie, clinique, dentaire, vétérinaire, laboratoire ou radiologie ?\n\n"
        "---\n*Source : indicateurs zonaux Invest Search + établissements OpenStreetMap.*"
    )
    response = _quick_response(
        question=question,
        markdown=markdown,
        status="needs_clarification",
        category="Couverture médicale générale",
        top_zone=zone,
        score=_safe_float(area.get("investment_score")),
    )
    response["suggested_questions"] = [
        f"Supply gap pharmacie à {zone}",
        f"Supply gap clinique à {zone}",
        f"Supply gap dentaire à {zone}",
        f"Supply gap vétérinaire à {zone}",
    ]
    return response


def build_investment_clarification_answer(question: str) -> dict:
    """Vague investment intent with no zone and no category: ask what and where."""
    zones = ", ".join(sorted(_zone_candidates())) or "non disponible"
    markdown = (
        "## Précisons votre projet d'investissement\n\n"
        "Pour une recommandation fiable (et non générique), j'ai besoin de deux informations :\n\n"
        "1. **Quel type d'établissement ?** pharmacie, clinique, cabinet dentaire, clinique "
        "vétérinaire, laboratoire d'analyses, restaurant, café, supermarché, école, crèche, "
        "salle de sport ou activité bien-être.\n"
        "2. **Quelle zone ou contrainte ?** une zone précise, ou bien « faible concurrence » / "
        "« quartiers sous-équipés » pour obtenir un classement.\n\n"
        f"**Zones analysées :** {zones}.\n\n"
        "Exemples : *« Où ouvrir une pharmacie à faible concurrence ? »*, "
        "*« Où ouvrir un restaurant à Casablanca ? »* ou *« J'ai 800 000 DH pour un commerce »*."
    )
    response = _quick_response(
        question=question,
        markdown=markdown,
        status="needs_clarification",
        category="General",
    )
    response["suggested_questions"] = [
        "Où ouvrir une pharmacie à faible concurrence ?",
        "Où ouvrir un restaurant à Casablanca ?",
        "J'ai 800 000 DH pour un commerce",
    ]
    return response


def build_easy_client_answer(question: str, category: str = "Small Private Clinic") -> dict | None:
    words = _tokenize(question)
    short = _is_short_client_request(words)
    normalized = _normalize_text(question)
    sector_category = _sector_category_from_question(question)
    sector_key = sector_category[0] if sector_category else _sector_from_question(question)
    sector_subcategory = sector_category[1] if sector_category else None
    inferred_category = _category_from_question(question, _category_or_default(category))
    top = _top_opportunity_for(inferred_category)
    top_zone = top.get("zone", "Casablanca")
    zones = _zones_from_question(question)
    location_fact = _location_fact_from_question(question)
    has_investment_intent = _has_investment_intent(words, normalized)

    if _is_external_navigation_command(question, words, normalized):
        return build_external_command_answer(question)

    if _is_abusive_message(words):
        return build_abusive_message_answer(question)

    if location_fact:
        return build_location_scope_answer(question, location_fact, has_investment_intent)

    coverage_gap = _coverage_gap_from_question(question)
    if coverage_gap:
        return build_arrondissement_gap_answer(question, coverage_gap)

    if ({"arrondissement", "arrondissements"} & words) and (
        words & {"gap", "gaps", "manquant", "manquants", "missing", "officiel", "officiels"}
        or "non score" in normalized
        or "pas score" in normalized
    ):
        return build_coverage_gaps_answer(question)

    unknown_zone = _explicit_unknown_zone(question)
    if unknown_zone:
        return build_unknown_zone_answer(question, unknown_zone)

    # "Les deux meilleurs quartiers pour une salle de sport" -> ranked top-N,
    # not a single zone. Only when no explicit 2-zone comparison was named.
    top_n = _requested_zone_count(normalized)
    if top_n and not (len(zones) >= 2):
        ranked = build_top_zones_answer(
            question=question,
            sector=sector_key,
            subcategory=sector_subcategory,
            category=inferred_category,
            top_n=top_n,
        )
        if ranked:
            return ranked

    if sector_key and _is_comparison_question(normalized) and len(zones) >= 2:
        sector_comparison = build_sector_comparison_answer(
            question=question,
            sector=sector_key,
            zones=zones,
            subcategory=sector_subcategory,
        )
        if sector_comparison:
            return sector_comparison

    if sector_key:
        sector_answer = build_sector_opportunity_answer(
            question=question,
            sector=sector_key,
            zone=zones[0] if zones else None,
            subcategory=sector_subcategory,
        )
        if sector_answer:
            return sector_answer

    if _is_low_coverage_question(normalized):
        return build_low_coverage_answer(question)

    if _is_comparison_question(normalized) and len(zones) >= 2:
        return build_zone_comparison_answer(question, zones)

    if _is_risk_question(words) and zones:
        return build_zone_risk_answer(question, zones[0])

    if _is_count_question(words, normalized) and zones:
        facts = build_zone_facts_answer(question, zones[0])
        if facts:
            return facts

    if _is_greeting(question):
        return _quick_response(
            question=question,
            markdown=GREETING_RESPONSE,
            status="easy_greeting",
        )

    if short and words & _THANKS_TOKENS:
        return _quick_response(
            question=question,
            status="easy_thanks",
            markdown=(
                "Avec plaisir. Je peux continuer de trois façons rapides :\n\n"
                "- **Comparer** deux quartiers pour un investissement santé, restauration, commerce, éducation ou bien-être.\n"
                "- **Ouvrir la carte** pour visualiser les points sectoriels et la densité locale.\n"
                "- **Préparer un rapport** avec recommandation, risques, KPIs et sources.\n\n"
                "Donnez-moi simplement une zone, un type d'établissement ou une contrainte."
            ),
        )

    if short and (words & _HELP_TOKENS or "que peux tu faire" in normalized or "comment ca marche" in normalized):
        return _quick_response(
            question=question,
            status="easy_help",
            markdown=(
                "Je peux traiter les demandes simples immédiatement, puis passer au RAG pour les analyses plus longues.\n\n"
                "### Demandes rapides\n"
                "- **Carte** : ouvrir l'Invest Map et montrer les points du secteur demandé.\n"
                "- **Sources** : expliquer les jeux de données utilisés.\n"
                "- **Rapport** : préparer une structure de memo investisseur.\n"
                "- **Catégories** : lister les secteurs et types d'établissements analysables.\n\n"
                "### Demandes analytiques\n"
                "- Comparer deux quartiers.\n"
                "- Recommander une zone pour une clinique, pharmacie, restaurant, commerce, école ou activité bien-être.\n"
                "- Identifier les risques et hypothèses à valider sur le terrain."
            ),
        )

    if short and words & _SOURCE_TOKENS:
        snapshot = get_market_snapshot()
        return _quick_response(
            question=question,
            status="easy_sources",
            suggested_view="sources",
            markdown=(
                "Les réponses Invest Search s'appuient sur une couche de sources locale et traçable.\n\n"
                f"- **HCP / zones Casablanca** : {snapshot['district_count']} zones analysées.\n"
                f"- **OpenStreetMap** : {snapshot['facility_count']} points santé et "
                f"{snapshot.get('multisector_total', 0)} points multi-secteurs géocodés.\n"
                "- **Ministère de la Santé** : cadre sanitaire, contraintes et références publiques.\n"
                "- **Moteur Invest Search** : scores d'opportunité, risque, supply gap et concurrence par secteur.\n\n"
                "La vue **Sources** affiche la bibliothèque de données et les passages récupérés quand une réponse RAG est générée."
            ),
        )

    if short and words & _MAP_TOKENS:
        return _quick_response(
            question=question,
            status="easy_map",
            suggested_view="map",
            top_zone=top_zone,
            score=top.get("score", 0),
            risk=top.get("risk", 0),
            category=inferred_category,
            markdown=(
                f"J'ouvre la **Carte Interactive** avec un focus sur **{top_zone}**.\n\n"
                "La carte permet de lire la densité des points du secteur demandé : santé, restauration, commerce, "
                "éducation ou bien-être. Utilisez-la pour repérer les zones sous-couvertes avant de lancer une analyse plus détaillée."
            ),
        )

    if short and words & _REPORT_TOKENS:
        report = build_answer_enriched(
            question=question,
            category=inferred_category,
            locale="fr",
        )
        report["rag_status"] = "easy_report"
        report["suggested_view"] = "reports"
        return report

    if short and words & _CATEGORY_TOKENS:
        category_lines = "\n".join(
            f"- **{display}**"
            for display in CATEGORY_DISPLAY_FR.values()
        )
        return _quick_response(
            question=question,
            status="easy_categories",
            markdown=(
                "Invest Search analyse plusieurs formats d'investissement dans la santé "
                "(cœur de la plateforme) et explore d'autres secteurs (restauration, commerce, "
                "éducation, bien-être) :\n\n"
                f"{category_lines}\n\n"
                "Pour une recommandation exploitable, précisez le type d'établissement et, si possible, 2 à 3 quartiers à comparer."
            ),
        )

    detected_category = _detected_category(question)

    # Rule 1 & 7: an explicit zone mention must anchor the answer on that zone,
    # never on the global top recommendation.
    if zones:
        zone = zones[0]
        if detected_category:
            zone_answer = build_zone_gap_competition_answer(question, zone, detected_category)
            if zone_answer:
                return zone_answer
        clarification = build_zone_clarification_answer(question, zone)
        if clarification:
            return clarification

    # Rule 4: vague investment intent with neither zone nor category -> ask, don't invent.
    if detected_category is None and _is_vague_investment(words, normalized) and len(words) <= 6:
        return build_investment_clarification_answer(question)

    if not _has_domain_context(question, words, normalized):
        return build_out_of_scope_answer(question)

    return None


def _build_source_cards(contexts: list[dict]) -> list[dict]:
    cards = source_cards_from_contexts(contexts)
    for card, ctx in zip(cards, contexts):
        card["quote"] = ctx.get("text", "")[:200]
    return cards


def build_budget_advisory_answer(question: str, category: str = "Small Private Clinic", locale: str = "fr") -> dict | None:
    """Budget-aware consulting answer. Returns None if no budget is stated.

    Combines the platform's zone scoring with an indicative cost model so the
    investor gets feasibility (can I afford it?), runway, scenarios, and — when
    the budget doesn't fit the requested type — affordable alternatives.
    """
    from api.services import consulting

    budget = consulting.parse_budget(question)
    if budget is None:
        return None

    # What does the investor want? sector (food/retail/...) takes priority over
    # a medical category only if explicitly present; otherwise infer category.
    sector_category = _sector_category_from_question(question)
    sector_key = sector_category[0] if sector_category else _sector_from_question(question)
    sector_subcategory = sector_category[1] if sector_category else None
    detected_category = _detected_category(question)
    zones_in_q = _zones_from_question(question)

    # Guard: a stray number + "dh" must not bypass the out-of-scope guardrails.
    # Only treat as a budget question with real investment intent or a known type.
    words = _tokenize(question)
    normalized = _normalize_text(question)
    if not (sector_key or detected_category or _has_investment_intent(words, normalized)):
        return None

    if sector_key and sector_key != "medical":
        is_sector = True
        type_key = sector_key
        type_label = _sector_category_label(sector_key, sector_subcategory)
        opps = get_sector_opportunities(sector_key, subcategory=sector_subcategory)
    else:
        is_sector = False
        type_key = detected_category or _category_or_default(category)
        type_label = CATEGORY_DISPLAY_FR.get(type_key, type_key).lower()
        opps = get_opportunities(type_key)

    # Full ranking so an explicitly requested zone is honoured even if it is
    # outside the top-12 (the reported bug: "800k commerce à Maarif" recommended
    # Hay Hassani because Maarif was not in the top-12).
    if is_sector:
        full_ranking = get_sector_opportunities(sector_key, subcategory=sector_subcategory, limit=99)
    else:
        full_ranking = get_opportunities(type_key, limit=99)
    best = full_ranking[0] if full_ranking else (opps[0] if opps else {})

    requested_zone = zones_in_q[0] if zones_in_q else None
    chosen = next((o for o in full_ranking if o["zone"] == requested_zone), None) if requested_zone else None
    if chosen is not None:
        top = chosen
        zone_rank = next((i + 1 for i, o in enumerate(full_ranking) if o["zone"] == requested_zone), None)
    else:
        # No explicit (or unknown) zone -> use the engine's best.
        top = best
        zone_rank = 1
        requested_zone = None
    n_zones = len(full_ranking) or 1
    zone = top.get("zone", "Casablanca")
    zone_score = _safe_float(top.get("score"))
    best_zone = best.get("zone", zone)
    best_score = _safe_float(best.get("score"))
    opex_multiplier, opex_basis = _zone_opex_multiplier(zone)
    assessment = consulting.assess(type_key, budget, is_sector, opex_multiplier=opex_multiplier)
    if assessment is None:
        return None

    verdict = assessment["verdict"]
    verdict_fr = consulting.VERDICT_FR[verdict]
    fmt = consulting.format_mad
    capex_low = fmt(assessment["capex_low"])
    capex_typ = fmt(assessment["capex_typical"])
    capex_high = fmt(assessment["capex_high"])
    opex = fmt(assessment["opex_month"])
    runway = assessment["runway_months"]
    coverage_pct = int(assessment["coverage_of_typical"] * 100)
    payback_months = assessment["payback_months"]

    # Affordable alternatives, useful especially when the budget is insufficient.
    alts = [
        o for o in consulting.affordable_options(budget, limit=6)
        if not (o["key"] == type_key and o["is_sector"] == is_sector)
    ]
    if alts:
        alts_text = ", ".join(f"{o['label']} (~{fmt(o['capex_typical'])})" for o in alts)
    else:
        # Budget below every entry ticket -> don't dead-end; show the cheapest
        # concepts overall so the answer stays actionable.
        cheapest = [
            o for o in consulting.affordable_options(10 ** 12, limit=5)
            if not (o["key"] == type_key and o["is_sector"] == is_sector)
        ][:4]
        listed = ", ".join(f"{o['label']} (~{fmt(o['capex_typical'])})" for o in cheapest)
        alts_text = (
            f"aucun format ne rentre dans ce budget — les concepts les moins coûteux : {listed}. "
            "Pistes : démarrer en version *lean*, un apport/financement complémentaire, ou un format mobile/partagé"
        )

    if verdict == "insufficient":
        headline = (
            f"Avec **{fmt(budget)}**, un projet **{type_label}** standard "
            f"(~{capex_typ} clé en main) n'est **pas finançable** : le budget couvre environ "
            f"**{coverage_pct}%** du coût typique. Voici ce qui rentre dans votre enveloppe."
        )
        next_steps = (
            "1. **Réorienter** vers un format compatible avec le budget (voir alternatives).\n"
            "2. **Compléter le financement** (apport, crédit bancaire, association) si vous tenez à ce type.\n"
            "3. **Affiner les coûts réels** : devis local, droit au bail, équipement, fonds de roulement."
        )
    elif requested_zone:
        # The investor named a zone -> evaluate THAT zone (is it a good fit?),
        # with its rank, instead of overriding it with the global best.
        headline = (
            f"Avec **{fmt(budget)}**, un projet **{type_label}** est **réaliste** ({verdict_fr}). "
            f"À **{zone}**, ce secteur est classé **{zone_rank}/{n_zones}** (score {zone_score}/100)."
        )
        if zone_rank and zone_rank > 1 and best_zone != zone:
            headline += (
                f" La zone la mieux notée pour ce secteur reste **{best_zone}** ({best_score}/100) — "
                f"demandez *« comparer {zone} et {best_zone} »* pour les opposer."
            )
        next_steps = (
            f"1. **Visiter {zone}** : loyers commerciaux réels, concurrence locale, état des locaux, flux.\n"
            f"2. **Comparer avec {best_zone}** si vous hésitez sur l'emplacement.\n"
            "3. **Demander des devis** et **vérifier les autorisations** (droit au bail) avant engagement."
        )
    else:
        headline = (
            f"Avec **{fmt(budget)}**, un projet **{type_label}** est **réaliste** "
            f"({verdict_fr}). La zone prioritaire indiquée par le moteur est **{zone}** "
            f"(score {zone_score}/100)."
        )
        next_steps = (
            f"1. **Visiter {zone}** : loyers commerciaux réels, état des locaux, flux.\n"
            "2. **Demander des devis** (agencement, équipement) pour caler le CAPEX.\n"
            "3. **Vérifier les autorisations** et le droit au bail avant engagement."
        )

    markdown = (
        f"## Conseil d'investissement — budget {fmt(budget)}\n\n"
        f"{headline}\n\n"
        f"## Faisabilité — {type_label}\n\n"
        f"- **Verdict :** {verdict_fr}.\n"
        f"- **Budget vs coût typique :** {fmt(budget)} pour ~{capex_typ} → couverture **{coverage_pct}%**.\n"
        f"- **Trésorerie d'exploitation restante :** ~**{runway} mois** d'OPEX zone-aware (~{opex}/mois, x{assessment['opex_multiplier']} via {opex_basis}) après une mise en place standard.\n"
        f"- **Payback indicatif :** ~**{payback_months} mois** sur contribution proxy, à valider avec CA, marge et loyer réel.\n"
        f"- **Principaux postes de coût :** {assessment['drivers']}.\n\n"
        "## Scénarios de mise en place (indicatif)\n\n"
        "| Scénario | CAPEX clé en main | Lecture |\n|---|---:|---|\n"
        f"| Optimisé / lean | {capex_low} | local plus petit, équipement essentiel |\n"
        f"| Standard | {capex_typ} | configuration de référence |\n"
        f"| Premium | {capex_high} | emplacement premium, équipement haut de gamme |\n\n"
        "## Alternatives compatibles avec le budget\n\n"
        f"{alts_text}.\n\n"
        "## Prochaines étapes\n\n"
        f"{next_steps}\n\n"
        "## Limites\n\n"
        "Les montants sont des **fourchettes indicatives** pour Casablanca (pas-de-porte, agencement, "
        "équipement, licences, fonds de roulement) et **ne constituent pas un devis ni un conseil "
        "financier**. À valider avec fournisseurs, bailleurs et autorités compétentes.\n\n"
        "---\n*Sources : moteur de scoring Invest Search + modèle de coûts indicatif Casablanca.*"
    )

    snapshot = get_market_snapshot()
    response = {
        "question": question,
        "answer_markdown": markdown,
        "top_zone": zone,
        "score": zone_score,
        "risk": _safe_float(top.get("risk")),
        "category": type_key,
        "sector": sector_key if is_sector else "medical",
        "subcategory": sector_subcategory if is_sector else None,
        "subcategory_label": type_label if is_sector and sector_subcategory else None,
        "sources": snapshot["sources"],
        "kpis": [
            {"label": "Budget", "value": fmt(budget)},
            {"label": "Type", "value": type_label},
            {"label": "Coût typique", "value": capex_typ},
            {"label": "Faisabilité", "value": verdict_fr.split(" —")[0].split(" (")[0]},
            {"label": "OPEX zone", "value": opex},
            {"label": "Runway", "value": f"{runway} mois"},
            {"label": "Payback", "value": f"{payback_months} mois"},
            {"label": "Zone", "value": zone},
        ],
        "map_focus": _zone_focus(zone),
        "related_opportunities": opps[:5],
        "retrieved_contexts": [],
        "rag_status": "budget_advisory",
        "suggested_view": _preferred_view_from_question(question),
        "suggested_questions": [
            f"Quelle zone pour {type_label} à faible concurrence ?",
            f"Quels établissements puis-je ouvrir avec {fmt(budget)} ?",
            f"Comparer deux quartiers pour {type_label}",
        ],
    }
    return response


def build_rag_answer(
    question: str,
    category: str = "Small Private Clinic",
    locale: str = "fr",
    skip_llm: bool = False,
) -> dict:
    budget_answer = build_budget_advisory_answer(question=question, category=category, locale=locale)
    if budget_answer:
        return budget_answer

    easy_answer = build_easy_client_answer(question=question, category=category)
    if easy_answer:
        return easy_answer

    # Rule 7 safety net: if an explicit zone slipped through, keep the answer zone-specific
    # instead of letting build_answer_enriched fall back to the global top recommendation.
    explicit_zones = _zones_from_question(question)
    if explicit_zones:
        zone = explicit_zones[0]
        detected_category = _detected_category(question)
        if detected_category:
            zone_answer = build_zone_gap_competition_answer(question, zone, detected_category)
            if zone_answer:
                return zone_answer
        zone_clarification = build_zone_clarification_answer(question, zone)
        if zone_clarification:
            return zone_clarification

    import time
    t0 = time.time()

    base = build_answer_enriched(question=question, category=category, locale=locale)
    top_opp = base["related_opportunities"][0] if base["related_opportunities"] else {}

    search_query = f"{question} {base['category']} {base['top_zone']} Casablanca"
    try:
        contexts, search_mode = hybrid_search(query=search_query, top_k=8)
    except Exception:
        contexts, search_mode = [], "none"

    source_cards = _build_source_cards(contexts) if contexts else []
    if source_cards:
        base["sources"] = source_cards

    base["retrieved_contexts"] = [
        {
            "title": item["title"],
            "source_path": item["source_path"],
            "kind": item["kind"],
            "score": item["score"],
            "text": item["text"][:700],
        }
        for item in contexts[:5]
    ]

    scoring_data = {
        "top_zone": base["top_zone"],
        "category": base["category"],
        "score": base["score"],
        "risk": base["risk"],
        "top_opportunity": top_opp,
    }

    if skip_llm:
        # Fast deterministic path (e.g. web-search turns): keep the grounded
        # scoring answer, skip the slow LLM narrative to stay well under any
        # serverless timeout. Sources/contexts remain attached above.
        base["rag_status"] = f"{search_mode}_scoring"
        log.info("chat elapsed=%ss status=%s (skip_llm) sources=%d",
                 round(time.time() - t0, 2), base["rag_status"], len(source_cards))
        return base

    try:
        llm_answer, provider_tag = generate_answer(question, scoring_data, contexts)
        if "population" not in llm_answer.lower() or "densit" not in llm_answer.lower():
            llm_answer = (
                f"{llm_answer}\n\n---\n\n"
                f"## Complément Invest Search : indicateurs et paramètres\n\n"
                f"{base['answer_markdown']}"
            )
        base["answer_markdown"] = llm_answer
        base["rag_status"] = f"{search_mode}_{provider_tag}"
        base["model"] = selected_model()
    except Exception as exc:
        log.info("LLM fallback: %s", exc)
        if contexts:
            rag_sources = "\n".join(
                f"- **{ctx['source_path']}** (pertinence: {ctx['score']:.0%})"
                for ctx in contexts[:4]
            )
            base["answer_markdown"] += (
                f"\n\n## Documents recuperes\n\n{rag_sources}\n\n"
                "*Reponse generee par le moteur de scoring Invest Search. "
                "LLM local indisponible — les sources ci-dessus contiennent "
                "des details complementaires.*"
            )
        base["rag_status"] = f"{search_mode}_scoring"

    elapsed = round(time.time() - t0, 2)
    log.info("chat elapsed=%ss status=%s sources=%d", elapsed, base["rag_status"], len(source_cards))
    return base
