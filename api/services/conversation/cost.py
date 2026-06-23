"""Cost-estimate intent: "quel budget faut-il pour ouvrir X ?".

The inverse of affordability: the investor gives a *type* (and maybe a zone) but
NO amount, and wants to know the budget required. Previously this fell through to
a generic RAG/zone answer (e.g. "score de Nouaceur") and never gave the cost.
Here we answer deterministically from the indicative cost model.
"""

from __future__ import annotations

from api.services import consulting
from api.services.invest_data import (
    CATEGORY_DISPLAY_FR,
    _category_or_default,
    _detected_category,
    _normalize_text,
    _sector_from_question,
    _zone_focus,
    _zones_from_question,
)

try:
    from api.services.invest_data import _sector_category_from_question
except ImportError:
    _sector_category_from_question = None  # type: ignore
try:
    from api.services.invest_data import _zone_opex_multiplier
except ImportError:
    _zone_opex_multiplier = None  # type: ignore

_COST_PHRASES = (
    "quel budget", "quel est le budget", "combien de budget", "combien ca coute",
    "combien coute", "cout pour ouvrir", "cout d ouvrir", "cout de", "budget necessaire",
    "budget pour ouvrir", "budget faut il", "budget pour une", "budget pour un",
    "prix pour ouvrir", "investissement necessaire", "investissement pour ouvrir",
    "ca coute combien", "combien faut il pour ouvrir", "de combien j ai besoin",
    "combien il faut pour ouvrir", "budget minimum", "budget approximatif pour",
)


def is_cost_estimate_question(message: str) -> bool:
    norm = _normalize_text(message)
    if consulting.parse_budget(message) is not None:
        return False  # an amount was given -> feasibility/affordability, not cost
    return any(p in norm for p in _COST_PHRASES)


def _resolve_type(message: str):
    """Return (is_sector, key, label, cost_profile) or None."""
    category = _detected_category(message)
    if category:
        profile = consulting.CATEGORY_COSTS.get(category)
        return (False, category, CATEGORY_DISPLAY_FR.get(category, category).lower(), profile)
    sc = _sector_category_from_question(message) if _sector_category_from_question else None
    sector = sc[0] if sc else _sector_from_question(message)
    if sector and sector != "medical":
        profile = consulting.SECTOR_COSTS.get(sector)
        label = consulting.SECTOR_LABELS.get(sector, sector)
        return (True, sector, label, profile)
    return None


def build_cost_estimate_answer(message: str) -> dict | None:
    resolved = _resolve_type(message)
    if resolved is None:
        return None
    is_sector, key, label, profile = resolved
    if profile is None:
        return None

    fmt = consulting.format_mad
    zones = _zones_from_question(message)
    zone = zones[0] if zones else None

    opex = profile.opex_month
    opex_note = ""
    if zone and _zone_opex_multiplier is not None:
        try:
            mult, basis = _zone_opex_multiplier(zone)
            opex = profile.opex_month * mult
            opex_note = f" (ajusté pour {zone} : ×{mult} via {basis})"
        except Exception:
            pass

    zone_suffix = f" à {zone}" if zone else ""
    markdown = (
        f"## Budget pour ouvrir une {label}{zone_suffix}\n\n"
        f"Pour une **{label}**, comptez typiquement **~{fmt(profile.capex_typical)}** "
        f"clé en main (fourchette **{fmt(profile.capex_low)} – {fmt(profile.capex_high)}**), "
        f"plus environ **{fmt(opex)}/mois** de charges d'exploitation{opex_note}.\n\n"
        "## Détail des coûts de mise en place\n\n"
        "| Scénario | CAPEX clé en main | Lecture |\n|---|---:|---|\n"
        f"| Optimisé / lean | {fmt(profile.capex_low)} | local plus petit, équipement essentiel |\n"
        f"| Standard | {fmt(profile.capex_typical)} | configuration de référence |\n"
        f"| Premium | {fmt(profile.capex_high)} | emplacement premium, équipement haut de gamme |\n\n"
        f"**Principaux postes :** {profile.drivers}.\n\n"
        "## Limites\n\n"
        "Fourchettes **indicatives** pour Casablanca (pas-de-porte, agencement, équipement, "
        "licences, fonds de roulement) — **pas un devis**. À valider avec fournisseurs et bailleurs"
        + (f", et avec le loyer réel à {zone}." if zone else ".")
        + "\n\n---\n*Source : modèle de coûts indicatif Invest Search.*"
    )
    return {
        "question": message,
        "answer_markdown": markdown,
        "top_zone": zone or "Casablanca",
        "score": 0,
        "risk": 0,
        "category": key if not is_sector else key,
        "sources": [],
        "kpis": [
            {"label": "Type", "value": label},
            {"label": "Budget typique", "value": fmt(profile.capex_typical)},
            {"label": "Fourchette", "value": f"{fmt(profile.capex_low)}–{fmt(profile.capex_high)}"},
            {"label": "OPEX/mois", "value": fmt(opex)},
        ],
        "map_focus": _zone_focus(zone) if zone else {"label": "Casablanca", "lat": 33.57, "lon": -7.59, "zoom": 11},
        "related_opportunities": [],
        "retrieved_contexts": [],
        "rag_status": "cost_estimate",
        "suggested_view": "intelligence",
        "suggested_questions": [
            f"Où ouvrir une {label} à faible concurrence ?",
            f"J'ai ce budget, est-ce suffisant pour une {label} ?",
            f"Quels établissements puis-je ouvrir avec {fmt(profile.capex_typical)} ?",
        ],
    }
