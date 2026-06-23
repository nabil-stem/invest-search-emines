"""Admin-only data freshness and refresh helpers."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from api.services.rag import build_index

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SCRIPTS_DIR = ROOT / "scripts"


def expected_admin_token() -> str | None:
    return os.environ.get("INVEST_SEARCH_ADMIN_TOKEN") or None


def data_status() -> dict:
    files = {
        "raw_osm_json": DATA_DIR / "raw" / "osm_casablanca_medical.json",
        "raw_osm_csv": DATA_DIR / "raw" / "osm_casablanca_medical.csv",
        "clean_facilities": DATA_DIR / "processed" / "medical_facilities_clean.csv",
        "area_indicators": DATA_DIR / "processed" / "area_indicators.csv",
        "specialty_supply": DATA_DIR / "processed" / "specialty_supply.csv",
        "geojson": DATA_DIR / "exports" / "medical_facilities.geojson",
        "zone_boundaries": DATA_DIR / "exports" / "casablanca_zone_boundaries.geojson",
        "opportunities": DATA_DIR / "exports" / "investment_opportunities.csv",
        "multisector_raw": DATA_DIR / "raw" / "osm_casablanca_multisector.csv",
        "sector_supply": DATA_DIR / "processed" / "sector_supply.csv",
        "subcategory_supply": DATA_DIR / "processed" / "subcategory_supply.csv",
        "arrondissement_taxonomy": DATA_DIR / "manual" / "hcp_rgph_2024_casablanca.csv",
        "hcp_rgph_2024": DATA_DIR / "manual" / "hcp_rgph_2024_casablanca.csv",
        "msps_public_2024": DATA_DIR / "manual" / "msps_public_facilities_2024.csv",
    }
    return {
        "admin_mode": True,
        "token_configured": bool(os.environ.get("INVEST_SEARCH_ADMIN_TOKEN")),
        "files": {
            key: {
                "exists": path.exists(),
                "path": str(path.relative_to(ROOT)),
                "updated_at": path.stat().st_mtime if path.exists() else None,
                "size_bytes": path.stat().st_size if path.exists() else 0,
            }
            for key, path in files.items()
        },
    }


def _run_step(name: str, command: list[str], timeout_seconds: int = 240) -> dict:
    started = time.time()
    proc = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return {
        "name": name,
        "returncode": proc.returncode,
        "elapsed_seconds": round(time.time() - started, 2),
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def refresh_data(use_cache: bool = False, rebuild_rag: bool = True) -> dict:
    """Refresh OSM-derived data, recompute scores, export GeoJSON, and optionally rebuild RAG."""
    started = time.time()
    cache_flag = "True" if use_cache else "False"
    multisector_command = [sys.executable, str(SCRIPTS_DIR / "collect_multisector_osm.py"), "--all"]
    if not use_cache:
        multisector_command.append("--refresh")
    steps = [
        (
            "OpenStreetMap Overpass",
            [
                sys.executable,
                "-c",
                f"from data_sources.osm_overpass import collect; collect(use_cache={cache_flag})",
            ],
        ),
        ("OpenStreetMap multi-sector", multisector_command),
        ("Collect zone boundaries", [sys.executable, str(SCRIPTS_DIR / "07_collect_zone_boundaries.py")]),
        ("Prepare official HCP and MSPS data", [sys.executable, str(SCRIPTS_DIR / "02_collect_official_sources.py")]),
        ("Normalize facilities", [sys.executable, str(SCRIPTS_DIR / "03_clean_normalize.py")]),
        ("Compute indicators and scores", [sys.executable, str(SCRIPTS_DIR / "05_compute_scores.py")]),
        ("Compute sector and activity scores", [sys.executable, str(SCRIPTS_DIR / "08_compute_sector_supply.py")]),
        ("Export GeoJSON", [sys.executable, str(SCRIPTS_DIR / "06_export_geojson.py")]),
    ]

    results = []
    for name, command in steps:
        result = _run_step(name, command)
        results.append(result)
        if result["returncode"] != 0:
            return {
                "ok": False,
                "failed_step": name,
                "elapsed_seconds": round(time.time() - started, 2),
                "steps": results,
                "status": data_status(),
            }

    rag_result = None
    if rebuild_rag:
        try:
            rag_index = build_index(force=True)
            rag_result = {
                "ok": True,
                "chunk_count": rag_index.get("chunk_count", 0),
                "embedding_model": rag_index.get("embedding_model"),
                "chat_model": rag_index.get("chat_model"),
            }
        except Exception as exc:  # pragma: no cover - admin diagnostics
            rag_result = {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "elapsed_seconds": round(time.time() - started, 2),
        "steps": results,
        "rag": rag_result,
        "status": data_status(),
    }
