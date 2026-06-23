"""Assign facility coordinates to real OSM administrative zone polygons."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BOUNDARIES_PATH = ROOT / "data" / "exports" / "casablanca_zone_boundaries.geojson"


def load_zone_boundaries() -> list[dict]:
    if not BOUNDARIES_PATH.exists():
        return []
    data = json.loads(BOUNDARIES_PATH.read_text(encoding="utf-8"))
    return [
        feature
        for feature in data.get("features", [])
        if not feature.get("properties", {}).get("is_alias")
    ]


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _point_in_polygon(lon: float, lat: float, polygon: list) -> bool:
    if not polygon or not _point_in_ring(lon, lat, polygon[0]):
        return False
    return not any(_point_in_ring(lon, lat, hole) for hole in polygon[1:])


def point_in_geometry(lon: float, lat: float, geometry: dict) -> bool:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if geometry_type == "Polygon":
        return _point_in_polygon(lon, lat, coordinates)
    if geometry_type == "MultiPolygon":
        return any(_point_in_polygon(lon, lat, polygon) for polygon in coordinates)
    return False


def assign_zone(
    lat: float,
    lon: float,
    boundaries: list[dict],
    fallback_districts: pd.DataFrame | None = None,
) -> str:
    if pd.isna(lat) or pd.isna(lon):
        return "Unknown"

    for feature in boundaries:
        if point_in_geometry(lon, lat, feature.get("geometry", {})):
            return feature.get("properties", {}).get("zone", "Unknown")

    return "Unknown"
