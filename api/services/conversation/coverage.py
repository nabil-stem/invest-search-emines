"""Honest handling of business types outside the current data perimeter.

The platform covers: santé (medical) + food, retail, education, wellness. If an
investor asks to open a business that resolves to NONE of these (e.g. bijouterie,
discothèque, laverie, station de lavage), the system must NOT fabricate a medical
recommendation (the old behaviour defaulted to "Small Private Clinic"). Instead
it returns a transparent coverage-gap answer — and still offers a generic
demographic starting point from the zone indicators, clearly labelled as not
business-specific.
"""

from __future__ import annotations

import re

from api.services.invest_data import (
    _areas,
    _detected_category,
    _format_int,
    _is_external_navigation_command,
    _normalize_text,
    _safe_float,
    _safe_int,
    _sector_from_question,
    _tokenize,
    _zone_focus,
    _zones_from_question,
)

try:
    from api.services.invest_data import _sector_category_from_question
except ImportError:  # older revisions
    _sector_category_from_question = None  # type: ignore

_OPEN_INTENT = ("ouvrir", "ouvre", "implanter", "implante", "lancer", "monter", "creer", "installer")

# Words that follow "ouvrir ..." but are NOT a concrete business type.
_GENERIC_NOUNS = {
    "projet", "business", "commerce", "entreprise", "societe", "activite", "affaire",
    "boite", "etablissement", "structure", "investissement", "chose", "truc",
    "magasin", "boutique",  # already resolved to retail elsewhere; avoid double-handling
    # Prepositions / fillers that can follow the verb ("ouvrir avec…", "ouvrir
    # dans…", "puis-je ouvrir avec…") and must never be read as a business.
    "avec", "pour", "dans", "chez", "vers", "sans", "sous", "sur", "quoi", "quel",
    "quelle", "quels", "quelles", "ici", "la", "ca", "cela", "ce", "cette", "mon",
    "ma", "mes", "comme", "environ",
}

_BUSINESS_RE = re.compile(
    r"(?:ouvrir|ouvre|implanter|implante|lancer|monter|creer|installer)\s+"
    r"(?:une?\s+|des\s+|mon\s+|ma\s+|mes\s+|le\s+|la\s+|un\s+)?"
    r"([a-z][a-z\-]{2,})"
)


def _resolves_to_sector_or_category(message: str) -> bool:
    if _detected_category(message):
        return True
    if _sector_from_question(message):
        return True
    if _sector_category_from_question and _sector_category_from_question(message):
        return True
    return False


def detect_unsupported_business(message: str) -> str | None:
    """Return the business word if the user wants to open something we don't cover."""
    normalized = _normalize_text(message)
    words = _tokenize(message)

    if not any(verb in normalized for verb in _OPEN_INTENT):
        return None
    # Let external-command / navigation requests be refused by the normal guardrail.
    if _is_external_navigation_command(message, words, normalized):
        return None
    # If it maps to a covered sector/category, it's supported — not our case.
    if _resolves_to_sector_or_category(message):
        return None

    match = _BUSINESS_RE.search(normalized)
    if not match:
        return None
    business = match.group(1)
    if business in _GENERIC_NOUNS or len(business) < 3:
        return None
    return business


def _generic_demographic_rows(limit: int = 5) -> list[dict]:
    areas = _areas()
    if areas.empty or "area_name" not in areas:
        return []
    df = areas.copy()
    for col in ("population_est", "population_density", "purchasing_power_proxy"):
        if col not in df.columns:
            df[col] = 0
    df = df.sort_values(["population_est", "population_density"], ascending=False).head(limit)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "zone": str(r["area_name"]),
            "population": _safe_int(r.get("population_est")),
            "density": _safe_float(r.get("population_density")),
            "purchasing_power": _safe_float(r.get("purchasing_power_proxy")),
        })
    return rows


def build_unsupported_business_answer(message: str, business: str) -> dict:
    """Transparent coverage-gap answer + a generic demographic starting point."""
    rows = _generic_demographic_rows()
    zones_in_q = _zones_from_question(message)
    focus_zone = zones_in_q[0] if zones_in_q else (rows[0]["zone"] if rows else "Casablanca")

    table = "\n".join(
        f"| {r['zone']} | {_format_int(r['population'])} | {r['density']:,.0f}/km² | {r['purchasing_power']:.0f}/100 |"
        for r in rows
    ) or "| — | — | — | — |"

    markdown = (
        f"## « {business.capitalize()} » : type non couvert par les données\n\n"
        f"Invest Search couvre aujourd'hui la **santé** et les secteurs "
        f"**restauration, commerce, éducation et bien-être**. Le type « **{business}** » "
        f"n'a pas encore de **données cartographiées** (POIs OpenStreetMap) ni de **scoring "
        f"calibré** : je ne vais donc **pas inventer** une recommandation ou un score "
        f"spécifique pour ce métier.\n\n"
        "## Point de départ démographique (générique, non spécifique au métier)\n\n"
        "En attendant des données dédiées, voici les zones les plus peuplées/denses — "
        "un repère de demande potentielle valable pour la plupart des commerces de proximité :\n\n"
        "| Quartier | Population | Densité | Pouvoir d'achat (proxy) |\n"
        "|---|---:|---:|---:|\n"
        f"{table}\n\n"
        "## Pour obtenir une analyse fiable\n\n"
        f"1. **Collecter les POIs** « {business} » via OpenStreetMap (étendre un *sector pack*) "
        "puis recalculer le scoring et réindexer le RAG.\n"
        "2. **Ou** reformuler vers un secteur couvert (ex. *commerce*, *restauration*, *bien-être*) "
        "si votre projet s'en rapproche.\n"
        "3. Croiser avec loyers commerciaux, flux piéton et réglementation locale.\n\n"
        "---\n*Aucune donnée spécifique à ce métier n'est disponible — réponse limitée aux "
        "indicateurs démographiques généraux pour éviter toute fabrication.*"
    )
    return {
        "question": message,
        "answer_markdown": markdown,
        "top_zone": focus_zone,
        "score": 0,
        "risk": 0,
        "category": f"Hors périmètre données : {business}",
        "sources": [],
        "kpis": [
            {"label": "Type demandé", "value": business},
            {"label": "Statut", "value": "Non couvert (données)"},
            {"label": "Secteurs couverts", "value": "Santé, food, retail, éducation, wellness"},
            {"label": "Action", "value": "Collecter ou reformuler"},
        ],
        "map_focus": _zone_focus(focus_zone) if rows else {"label": "Casablanca", "lat": 33.57, "lon": -7.59, "zoom": 11},
        "related_opportunities": [],
        "retrieved_contexts": [],
        "rag_status": "data_coverage_gap",
        "suggested_view": "intelligence",
        "suggested_questions": [
            "Où ouvrir un commerce à faible concurrence ?",
            "Où ouvrir un restaurant à Casablanca ?",
            "Quels secteurs sont couverts par Invest Search ?",
        ],
    }
