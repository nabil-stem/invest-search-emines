"""Admin endpoints for controlled data refresh operations."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.services.admin_refresh import data_status, expected_admin_token, refresh_data

router = APIRouter()


class RefreshRequest(BaseModel):
    use_cache: bool = False
    rebuild_rag: bool = True


def _require_admin(x_admin_token: str | None) -> None:
    expected = expected_admin_token()
    if not expected:
        raise HTTPException(status_code=503, detail="INVEST_SEARCH_ADMIN_TOKEN is not configured")
    if x_admin_token != expected:
        raise HTTPException(status_code=403, detail="Admin token required")


@router.get("/admin/data-status")
def get_data_status() -> dict:
    return data_status()


@router.post("/admin/refresh-data")
def refresh(request: RefreshRequest, x_admin_token: str | None = Header(default=None)) -> dict:
    _require_admin(x_admin_token)
    return refresh_data(use_cache=request.use_cache, rebuild_rag=request.rebuild_rag)
