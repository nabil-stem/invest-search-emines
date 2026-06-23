"""Short factual answers for simple data questions about a zone.

"Quelle est la population d'Anfa ?", "densité de Maarif ?", "superficie de Sidi
Moumen ?" used to return a needs_clarification block. These are pure data
lookups, so we answer them directly from area_indicators in 1-2 sentences —
deterministic, zero hallucination, no investment-note structure.

Category counts ("combien de cafés à Maarif ?") are intentionally NOT handled
here: the existing sector handler already returns the exact count (and the
scenario suite asserts its structure).
"""

from __future__ import annotations

from api.services.invest_data import (
    _area_row,
    _detected_category,
    _format_int,
    _normalize_text,
    _safe_float,
    _safe_int,
    _sector_from_question,
    _zone_focus,
    _zones_from_question,
)

_CONSULTING_WORDS = ("ouvrir", "implanter", "recommand", "investir", "faisabilite", "ou ouvrir")


def _fact_key(norm: str) -> str | None:
    if any(w in norm for w in ("population", "habitant", "nombre d habitant", "combien de personne")):
        return "population"
    if "densite" in norm:
        return "density"
    if any(w in norm for w in ("superficie", "surface", "etendue", "km2", "km 2")) or " taille " in f" {norm} ":
        return "area"
    if "pouvoir d achat" in norm or "revenu" in norm:
        return "purchasing"
    if "score" in norm:
        return "score"
    return None


def is_factual_question(message: str) -> bool:
    if not _zones_from_question(message):
        return False
    norm = _normalize_text(message)
    if any(w in norm for w in _CONSULTING_WORDS):
        return False
    # A category count ("combien de cafés à X") is handled by the sector handler.
    if "combien" in norm and (_sector_from_question(message) or _detected_category(message)):
        return False
    return _fact_key(norm) is not None


def build_factual_answer(message: str) -> dict | None:
    zones = _zones_from_question(message)
    if not zones:
        return None
    zone = zones[0]
    area = _area_row(zone)
    if not area:
        return None
    norm = _normalize_text(message)
    key = _fact_key(norm)

    pop = _safe_int(area.get("population_est"))
    density = _safe_float(area.get("population_density"))
    area_km2 = _safe_float(area.get("area_km2"))
    pp = _safe_float(area.get("purchasing_power_proxy"))
    score = _safe_float(area.get("investment_score"))
    year = area.get("population_year") or "estimation"

    if key == "population":
        label, sentence, value = (
            "Population",
            f"**{zone}** compte environ **{_format_int(pop)} habitants** ({year}).",
            f"{_format_int(pop)} hab.",
        )
    elif key == "density":
        density_fr = f"{density:,.0f}".replace(",", " ")
        label, sentence, value = (
            "Densité",
            f"La densité de population de **{zone}** est d'environ **{density_fr} habitants/km²**.",
            f"{density_fr}/km²",
        )
    elif key == "area":
        label, sentence, value = (
            "Superficie",
            f"La superficie de **{zone}** est d'environ **{area_km2:g} km²** "
            f"(pour {_format_int(pop)} habitants).",
            f"{area_km2:g} km²",
        )
    elif key == "purchasing":
        label, sentence, value = (
            "Pouvoir d'achat",
            f"L'indice de pouvoir d'achat (proxy) de **{zone}** est de **{pp:.0f}/100**.",
            f"{pp:.0f}/100",
        )
    elif key == "score":
        label, sentence, value = (
            "Score d'investissement",
            f"Le score d'investissement global de **{zone}** est de **{score:.1f}/100**.",
            f"{score:.1f}/100",
        )
    else:
        return None

    markdown = (
        f"**{zone} — {label} : {value}**\n\n"
        f"{sentence}\n\n"
        "*Source : indicateurs zonaux Invest Search (HCP / OpenStreetMap).*"
    )
    return {
        "question": message,
        "answer_markdown": markdown,
        "top_zone": zone,
        "score": score,
        "risk": 0,
        "category": "Donnée factuelle",
        "sources": [],
        "kpis": [{"label": label, "value": value}, {"label": "Zone", "value": zone}],
        "map_focus": _zone_focus(zone),
        "related_opportunities": [],
        "retrieved_contexts": [],
        "rag_status": "factual",
        "suggested_view": "intelligence",
        "suggested_questions": [
            f"Quelle est la densité de {zone} ?",
            f"Où ouvrir une pharmacie à {zone} ?",
            f"Comparer {zone} et Maarif",
        ],
    }
