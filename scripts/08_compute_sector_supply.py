"""Build persisted multi-sector supply scores and RAG fact sheets.

The raw OSM multi-sector collection is point-level. This script assigns every
POI to a Casablanca zone, aggregates supply per sector and district, applies
sector-specific score weights, then writes:

* data/processed/sector_supply.csv
* data/processed/subcategory_supply.csv
* data/processed/zone_profiles/<sector>_<area>.md

Run with:
    .api310/Scripts/python.exe scripts/08_compute_sector_supply.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_sources.sectors import SECTORS, Sector  # noqa: E402
from data_sources.zone_boundaries import assign_zone, load_zone_boundaries  # noqa: E402

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
RAW_MULTI = RAW_DIR / "osm_casablanca_multisector.csv"
DISTRICTS_CSV = RAW_DIR / "casablanca_districts.csv"
AREAS_CSV = PROCESSED_DIR / "area_indicators.csv"
SUPPLY_CSV = PROCESSED_DIR / "sector_supply.csv"
SUBCATEGORY_SUPPLY_CSV = PROCESSED_DIR / "subcategory_supply.csv"
PROFILE_DIR = PROCESSED_DIR / "zone_profiles"


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def _normalize_0_100(series: pd.Series, *, invert: bool = False) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0)
    low = float(values.min())
    high = float(values.max())
    if high == low:
        normalized = pd.Series(50.0, index=values.index)
    else:
        normalized = (values - low) / (high - low) * 100
    if invert:
        normalized = 100 - normalized
    return normalized.round(1)


def _competition_level(per_100k: float, sector: Sector) -> str:
    low, high = sector.competition_thresholds_per_100k
    if per_100k <= low:
        return "Faible"
    if per_100k <= high:
        return "Modérée"
    return "Élevée"


def _competition_level_for_thresholds(per_100k: float, thresholds: tuple[float, float]) -> str:
    low, high = thresholds
    if per_100k <= low:
        return "Faible"
    if per_100k <= high:
        return "Modérée"
    return "Élevée"


def _slug(value: str) -> str:
    value = value.lower()
    value = value.replace("'", "")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "zone"


def _ensure_districts(points: pd.DataFrame) -> pd.DataFrame:
    if points.empty:
        return points
    points = points.copy()
    if "district" in points and points["district"].fillna("").str.strip().ne("").any():
        points["district"] = points["district"].fillna("Unknown").replace("", "Unknown")
        return points

    districts = _read_csv(DISTRICTS_CSV)
    boundaries = load_zone_boundaries()
    points["district"] = points.apply(
        lambda row: assign_zone(row.get("lat"), row.get("lon"), boundaries, districts),
        axis=1,
    )
    points["district"] = points["district"].fillna("Unknown").replace("", "Unknown")
    return points


def compute_sector_supply() -> pd.DataFrame:
    points = _ensure_districts(_read_csv(RAW_MULTI))
    areas = _read_csv(AREAS_CSV)
    if points.empty:
        raise RuntimeError(f"No multi-sector POIs found at {RAW_MULTI}")
    if areas.empty:
        raise RuntimeError(f"No area indicators found at {AREAS_CSV}")

    rows: list[pd.DataFrame] = []
    for sector_key, sector in SECTORS.items():
        if sector_key == "medical":
            continue
        sector_points = points[
            (points["sector"] == sector_key)
            & (points["district"].fillna("Unknown") != "Unknown")
        ].copy()
        grouped = sector_points.groupby("district").agg(
            providers_count=("id", "count"),
            average_confidence=("confidence_score", "mean"),
        )

        ranked = areas.copy()
        ranked = ranked.merge(grouped, left_on="area_name", right_index=True, how="left")
        ranked["sector"] = sector_key
        ranked["sector_label_fr"] = sector.label_fr
        ranked["providers_count"] = ranked["providers_count"].fillna(0).astype(int)
        ranked["average_confidence"] = (
            pd.to_numeric(ranked["average_confidence"], errors="coerce")
            .fillna(sector.confidence)
            .clip(0, 1)
        )
        ranked["providers_per_100k"] = ranked.apply(
            lambda row: (
                row["providers_count"] / row["population_est"] * 100000
                if row.get("population_est", 0)
                else 0
            ),
            axis=1,
        )
        ranked["population_score"] = _normalize_0_100(ranked["population_est"])
        ranked["density_score"] = _normalize_0_100(ranked["population_density"])
        ranked["purchasing_power_score"] = _normalize_0_100(ranked["purchasing_power_proxy"])
        ranked["low_competition_score"] = _normalize_0_100(
            ranked["providers_per_100k"], invert=True
        )
        ranked["confidence_score"] = (ranked["average_confidence"] * 100).round(1)
        ranked["demand_score"] = (
            ranked["population_score"] * 0.40
            + ranked["density_score"] * 0.25
            + ranked["purchasing_power_score"] * 0.35
        ).round(1)

        weights = sector.score_weights
        ranked["sector_opportunity_score"] = (
            ranked["population_score"] * weights["population"]
            + ranked["density_score"] * weights["density"]
            + ranked["purchasing_power_score"] * weights["purchasing_power"]
            + ranked["low_competition_score"] * weights["low_competition"]
            + ranked["confidence_score"] * weights["osm_confidence"]
        ).round(1)
        ranked["risk_score"] = (
            (100 - ranked["confidence_score"]) * 0.42
            + _normalize_0_100(ranked["providers_count"]) * 0.24
            + (100 - ranked["demand_score"]) * 0.22
            + (100 - ranked["purchasing_power_score"]) * 0.12
        ).round(1)
        ranked["supply_gap"] = ranked["low_competition_score"]
        ranked["competition_level"] = ranked["providers_per_100k"].apply(
            lambda value: _competition_level(float(value), sector)
        )
        ranked["scoring_status"] = "scored"
        ranked["weights_version"] = "sector_weights_v1"
        ranked["assigned_pois_sector"] = int(len(sector_points))
        ranked["total_pois_sector"] = int(len(points[points["sector"] == sector_key]))
        rows.append(ranked)

    supply = pd.concat(rows, ignore_index=True)
    columns = [
        "sector",
        "sector_label_fr",
        "area_id",
        "area_name",
        "prefecture",
        "providers_count",
        "providers_per_100k",
        "competition_level",
        "average_confidence",
        "population_est",
        "population_density",
        "purchasing_power_proxy",
        "population_score",
        "density_score",
        "purchasing_power_score",
        "demand_score",
        "low_competition_score",
        "supply_gap",
        "sector_opportunity_score",
        "risk_score",
        "scoring_status",
        "weights_version",
        "assigned_pois_sector",
        "total_pois_sector",
    ]
    return supply[columns].sort_values(["sector", "sector_opportunity_score"], ascending=[True, False])


def compute_subcategory_supply() -> pd.DataFrame:
    """Score each supported business type independently within its sector.

    Competition uses an empirical-Bayes rate: sparse or empty zones are shrunk
    toward the citywide category rate instead of being treated as proven white
    space. Confidence also grows with the local sample size.
    """
    points = _ensure_districts(_read_csv(RAW_MULTI))
    areas = _read_csv(AREAS_CSV)
    if points.empty or areas.empty:
        raise RuntimeError("Multi-sector POIs and area indicators are required")

    total_population = float(pd.to_numeric(areas["population_est"], errors="coerce").fillna(0).sum())
    rows: list[pd.DataFrame] = []
    for sector_key, sector in SECTORS.items():
        if sector_key == "medical":
            continue
        sector_points = points[
            (points["sector"] == sector_key)
            & (points["district"].fillna("Unknown") != "Unknown")
        ].copy()
        total_sector_points = int(len(points[points["sector"] == sector_key]))

        for category in sector.category_intent_aliases:
            category_points = sector_points[sector_points["category"] == category].copy()
            grouped = category_points.groupby("district").agg(
                providers_count=("id", "count"),
                source_confidence=("confidence_score", "mean"),
            )
            ranked = areas.copy().merge(grouped, left_on="area_name", right_index=True, how="left")
            ranked["sector"] = sector_key
            ranked["sector_label_fr"] = sector.label_fr
            ranked["subcategory"] = category
            ranked["subcategory_label_fr"] = sector.category_labels_fr.get(category, category)
            ranked["providers_count"] = ranked["providers_count"].fillna(0).astype(int)
            ranked["source_confidence"] = (
                pd.to_numeric(ranked["source_confidence"], errors="coerce")
                .fillna(sector.confidence)
                .clip(0, 1)
            )
            ranked["providers_per_100k"] = ranked.apply(
                lambda row: row["providers_count"] / row["population_est"] * 100000
                if row.get("population_est", 0) else 0,
                axis=1,
            )

            city_rate = (len(category_points) / total_population * 100000) if total_population else 0
            ranked["competition_rate_smoothed"] = ranked.apply(
                lambda row: (
                    (row["providers_count"] + city_rate)
                    / (row["population_est"] + 100000)
                    * 100000
                ) if row.get("population_est", 0) else city_rate,
                axis=1,
            )
            ranked["population_score"] = _normalize_0_100(ranked["population_est"])
            ranked["density_score"] = _normalize_0_100(ranked["population_density"])
            ranked["purchasing_power_score"] = _normalize_0_100(ranked["purchasing_power_proxy"])
            ranked["low_competition_score"] = _normalize_0_100(
                ranked["competition_rate_smoothed"], invert=True
            )
            evidence_factor = 0.55 + 0.45 * (ranked["providers_count"].clip(upper=8) / 8)
            ranked["average_confidence"] = (ranked["source_confidence"] * evidence_factor).round(3)
            ranked["confidence_score"] = (ranked["average_confidence"] * 100).round(1)
            ranked["demand_score"] = (
                ranked["population_score"] * 0.40
                + ranked["density_score"] * 0.25
                + ranked["purchasing_power_score"] * 0.35
            ).round(1)

            weights = sector.category_score_weights.get(category, sector.score_weights)
            ranked["sector_opportunity_score"] = (
                ranked["population_score"] * weights["population"]
                + ranked["density_score"] * weights["density"]
                + ranked["purchasing_power_score"] * weights["purchasing_power"]
                + ranked["low_competition_score"] * weights["low_competition"]
                + ranked["confidence_score"] * weights["osm_confidence"]
                - (1 - evidence_factor) * 20
            ).clip(lower=0).round(1)
            ranked["risk_score"] = (
                (100 - ranked["confidence_score"]) * 0.48
                + _normalize_0_100(ranked["providers_count"]) * 0.18
                + (100 - ranked["demand_score"]) * 0.22
                + (100 - ranked["purchasing_power_score"]) * 0.12
            ).round(1)

            share = len(category_points) / max(1, len(sector_points))
            threshold_scale = max(0.08, share)
            thresholds = tuple(value * threshold_scale for value in sector.competition_thresholds_per_100k)
            ranked["competition_level"] = ranked["providers_per_100k"].apply(
                lambda value: _competition_level_for_thresholds(float(value), thresholds)
            )
            ranked["supply_gap"] = ranked["low_competition_score"]
            ranked["scoring_status"] = "scored_subcategory"
            ranked["weights_version"] = "subcategory_weights_v2_bayes"
            ranked["assigned_pois_subcategory"] = int(len(category_points))
            ranked["total_pois_subcategory"] = int(
                len(points[(points["sector"] == sector_key) & (points["category"] == category)])
            )
            ranked["assigned_pois_sector"] = int(len(sector_points))
            ranked["total_pois_sector"] = total_sector_points
            rows.append(ranked)

    supply = pd.concat(rows, ignore_index=True)
    columns = [
        "sector", "sector_label_fr", "subcategory", "subcategory_label_fr",
        "area_id", "area_name", "prefecture", "providers_count", "providers_per_100k",
        "competition_rate_smoothed", "competition_level", "average_confidence",
        "population_est", "population_density", "purchasing_power_proxy",
        "population_score", "density_score", "purchasing_power_score", "demand_score",
        "low_competition_score", "supply_gap", "sector_opportunity_score", "risk_score",
        "scoring_status", "weights_version", "assigned_pois_subcategory",
        "total_pois_subcategory", "assigned_pois_sector", "total_pois_sector",
    ]
    return supply[columns].sort_values(
        ["sector", "subcategory", "sector_opportunity_score"], ascending=[True, True, False]
    )


def _category_counts(points: pd.DataFrame, sector: str, area_name: str) -> str:
    scoped = points[(points["sector"] == sector) & (points["district"] == area_name)]
    if scoped.empty:
        return "Aucun POI sectoriel assigne dans la zone."
    return ", ".join(
        f"{category}: {count}"
        for category, count in scoped["category"].value_counts().head(6).items()
    )


def write_zone_profiles(supply: pd.DataFrame, subcategory_supply: pd.DataFrame) -> int:
    points = _ensure_districts(_read_csv(RAW_MULTI))
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    for stale in PROFILE_DIR.glob("*.md"):
        stale.unlink()

    count = 0
    for _, row in supply.iterrows():
        sector = str(row["sector"])
        area_name = str(row["area_name"])
        sector_meta = SECTORS[sector]
        weights = ", ".join(
            f"{name}={weight:.2f}" for name, weight in sector_meta.score_weights.items()
        )
        category_counts = _category_counts(points, sector, area_name)
        category_rows = subcategory_supply[
            (subcategory_supply["sector"] == sector)
            & (subcategory_supply["area_name"] == area_name)
        ].sort_values("sector_opportunity_score", ascending=False)
        category_table = "\n".join(
            f"| {item['subcategory_label_fr']} | {int(item['providers_count'])} | "
            f"{float(item['providers_per_100k']):.1f} | {item['competition_level']} | "
            f"{float(item['sector_opportunity_score']):.1f} | {float(item['risk_score']):.1f} |"
            for _, item in category_rows.iterrows()
        ) or "| Non disponible | 0 | 0 | Non disponible | 0 | 100 |"
        content = (
            f"# Profil zone-sectoriel: {area_name} / {sector_meta.label_fr}\n\n"
            f"- Source table: `data/processed/sector_supply.csv`\n"
            f"- Sector: `{sector}` ({sector_meta.label_fr})\n"
            f"- Zone: {area_name}\n"
            f"- Prefecture: {row.get('prefecture', '')}\n"
            f"- Providers count: {int(row['providers_count'])}\n"
            f"- Providers per 100k residents: {float(row['providers_per_100k']):.1f}\n"
            f"- Competition level: {row['competition_level']}\n"
            f"- Supply gap: {float(row['supply_gap']):.1f}/100\n"
            f"- Sector opportunity score: {float(row['sector_opportunity_score']):.1f}/100\n"
            f"- Risk score: {float(row['risk_score']):.1f}/100\n"
            f"- Population estimate: {int(row['population_est'])}\n"
            f"- Population density: {float(row['population_density']):.1f} hab./km2\n"
            f"- Purchasing power proxy: {float(row['purchasing_power_proxy']):.1f}/100\n"
            f"- OSM confidence: {float(row['average_confidence']):.2f}\n"
            f"- Category mix in zone: {category_counts}\n"
            f"- Scoring weights: {weights}\n\n"
            "## Scores par activité\n\n"
            "| Activité | POIs | POIs/100k | Concurrence | Opportunité | Risque data |\n"
            "|---|---:|---:|---|---:|---:|\n"
            f"{category_table}\n\n"
            "Interpretation: a high score means the zone combines demand, purchasing-power "
            "potential, relatively low mapped competition and acceptable OSM reliability. "
            "This does not replace field validation on rents, footfall, lease terms and "
            "informal competitors.\n"
        )
        out = PROFILE_DIR / f"{sector}_{_slug(area_name)}.md"
        out.write_text(content, encoding="utf-8")
        count += 1
    return count


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    supply = compute_sector_supply()
    subcategory_supply = compute_subcategory_supply()
    supply.to_csv(SUPPLY_CSV, index=False, encoding="utf-8-sig")
    subcategory_supply.to_csv(SUBCATEGORY_SUPPLY_CSV, index=False, encoding="utf-8-sig")
    profiles = write_zone_profiles(supply, subcategory_supply)
    print(f"Wrote {len(supply)} rows to {SUPPLY_CSV}")
    print(f"Wrote {len(subcategory_supply)} rows to {SUBCATEGORY_SUPPLY_CSV}")
    print(f"Wrote {profiles} RAG fact sheets to {PROFILE_DIR}")


if __name__ == "__main__":
    main()
