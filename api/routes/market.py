"""Market data endpoints."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from api.services.invest_data import (
    get_facility_points,
    get_market_snapshot,
    get_opportunities,
    get_sector_facility_points,
    get_sector_opportunities,
    get_sector_summary,
    get_zones,
)

router = APIRouter()

GEOJSON_PATH = Path(__file__).resolve().parents[2] / "data" / "exports" / "medical_facilities.geojson"
BOUNDARIES_PATH = Path(__file__).resolve().parents[2] / "data" / "exports" / "casablanca_zone_boundaries.geojson"


@router.get("/snapshot")
def snapshot() -> dict:
    return get_market_snapshot()


@router.get("/zones")
def zones() -> list[dict]:
    return get_zones()


@router.get("/opportunities")
def opportunities(category: str = Query("Small Private Clinic")) -> list[dict]:
    return get_opportunities(category)


@router.get("/sectors")
def sectors() -> dict:
    return get_sector_summary()


@router.get("/sector-opportunities")
def sector_opportunities(
    sector: str = Query("food"),
    subcategory: str | None = Query(None),
) -> list[dict]:
    return get_sector_opportunities(sector, subcategory=subcategory)


@router.get("/sector-facilities")
def sector_facilities(
    sector: str = Query("food"),
    subcategory: str | None = Query(None),
    limit: int = Query(300, ge=1, le=2000),
) -> list[dict]:
    return get_sector_facility_points(sector=sector, subcategory=subcategory, limit=limit)


@router.get("/facilities")
def facilities(limit: int = Query(300, ge=1, le=1000)) -> list[dict]:
    return get_facility_points(limit=limit)


@router.get("/geojson")
def geojson():
    if not GEOJSON_PATH.exists():
        return JSONResponse({"type": "FeatureCollection", "features": []})
    data = json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))
    return JSONResponse(data)


@router.get("/zone-boundaries")
def zone_boundaries():
    if not BOUNDARIES_PATH.exists():
        return JSONResponse({"type": "FeatureCollection", "features": []})
    data = json.loads(BOUNDARIES_PATH.read_text(encoding="utf-8"))
    return JSONResponse(data)
