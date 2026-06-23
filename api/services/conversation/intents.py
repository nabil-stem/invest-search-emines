"""Follow-up intent classification + interactive consulting answers.

Fixes the "memory overrides the last question" bug: previously every follow-up
was rewritten from the stored profile (budget+sector+zone), so a new question
like "what can I open with this budget?" was answered as the OLD project.

Two helpers decide how a follow-up is handled:
  * is_affordability_question -> list establishments that fit the budget.
  * is_context_fragment      -> a thin fragment ("Sidi Moumen", "compare avec
                                Maarif", "et un café") that NEEDS the profile to
                                be meaningful -> rewrite. Anything else is a real
                                new question and is answered on its own.
"""

from __future__ import annotations

import re

from api.services import consulting
from api.services.invest_data import (
    CATEGORY_DISPLAY_FR,
    _detected_category,
    _normalize_text,
    _sector_from_question,
    _tokenize,
    _zone_focus,
    _zones_from_question,
)

try:
    from api.services.invest_data import _sector_category_from_question
except ImportError:
    _sector_category_from_question = None  # type: ignore

_AFFORDABILITY_PHRASES = (
    "que puis je ouvrir", "qu est ce que je peux ouvrir", "que peux je ouvrir",
    "que peut on ouvrir", "quoi ouvrir", "quel commerce ouvrir", "quel etablissement ouvrir",
    "quels etablissements", "quels commerces", "quels business", "quel business",
    "avec ce budget", "avec mon budget", "avec ce montant", "avec cette somme",
    "qu est ce qui rentre", "options pour ce budget", "que faire avec ce budget",
    "que puis je faire avec", "rentre dans mon budget", "rentre dans ce budget",
)

# Words that mark an independent question (so it's NOT a thin context fragment).
_INDEPENDENT_MARKERS = (
    "comment", "pourquoi", "explique", "expliquer", "methodologie", "scoring",
    "sources", "rapport", "liste", "combien", "faible couverture", "meilleurs quartiers",
    "quels quartiers", "indice", "calcul", "saturation", "que puis", "puis je",
)

_FRAGMENT_INTRO = ("et ", " et,", "ou ", "aussi ", "puis ", "sinon ", "plutot ")


def is_affordability_question(message: str) -> bool:
    norm = _normalize_text(message)
    return any(p in norm for p in _AFFORDABILITY_PHRASES)


def _has_thin_signal(message: str) -> bool:
    """Does the message carry only a zone / budget / sector / comparison hint?"""
    if _zones_from_question(message):
        return True
    if consulting.parse_budget(message) is not None:
        return True
    if _sector_from_question(message) or _detected_category(message):
        return True
    if _sector_category_from_question is not None and _sector_category_from_question(message):
        return True
    norm = _normalize_text(message)
    return any(s in f" {norm} " for s in (" compare ", " comparer ", " versus ", " vs "))


def is_context_fragment(message: str) -> bool:
    """A short follow-up that only makes sense against the stored profile."""
    norm = _normalize_text(message)
    words = _tokenize(message)
    if any(m in norm for m in _INDEPENDENT_MARKERS):
        return False
    starts_fragment = any(norm.startswith(intro.strip()) or norm.startswith(intro) for intro in _FRAGMENT_INTRO)
    short = len(words) <= 6
    return (short or starts_fragment) and _has_thin_signal(message)


def _label_fr(option: dict) -> str:
    if option["is_sector"]:
        return option["label"]
    return CATEGORY_DISPLAY_FR.get(option["key"], option["key"])


def build_affordability_answer(profile_dict: dict, message: str) -> dict | None:
    """Interactive: list establishment types whose typical setup cost fits the budget."""
    budget = profile_dict.get("budget") or consulting.parse_budget(message)
    if not budget:
        return None

    zone = (profile_dict.get("zone") or "").strip() or None
    zone_suffix = f" à {zone}" if zone else ""

    fmt = consulting.format_mad
    fitting = consulting.affordable_options(budget, limit=10)

    if fitting:
        rows = "\n".join(f"| {_label_fr(o)} | ~{fmt(o['capex_typical'])} |" for o in fitting)
        zone_close = (
            f"Pour **{zone}**, dites-moi le type qui vous intéresse et je l'évalue (concurrence, "
            f"demande, faisabilité) à {zone}."
            if zone
            else "Dites-moi lequel vous intéresse (et éventuellement un quartier) pour une analyse "
            "de zone, de concurrence et de faisabilité."
        )
        body = (
            f"## Établissements ouvrables avec {fmt(budget)}{zone_suffix}\n\n"
            "Voici les types d'établissement dont le **coût de mise en place typique** "
            "(local, agencement, équipement, licences, fonds de roulement) rentre dans votre "
            "budget, du plus accessible au plus cher :\n\n"
            "| Type d'établissement | Coût clé en main typique |\n|---|---:|\n"
            f"{rows}\n\n"
            f"{zone_close}"
        )
        status_kpi = f"{len(fitting)} types compatibles"
    else:
        cheapest = consulting.affordable_options(10**12, limit=4)
        rows = "\n".join(f"| {_label_fr(o)} | ~{fmt(o['capex_typical'])} |" for o in cheapest)
        body = (
            f"## Budget {fmt(budget)} : sous les tickets d'entrée habituels\n\n"
            f"Avec **{fmt(budget)}**, aucun format standard n'est finançable clé en main. "
            "Les concepts les **moins coûteux** restent :\n\n"
            "| Type d'établissement | Coût clé en main typique |\n|---|---:|\n"
            f"{rows}\n\n"
            "Pistes : démarrer en version *lean* (local plus petit, équipement essentiel, "
            "occasion), un apport complémentaire, ou un format mobile/partagé."
        )
        status_kpi = "Budget serré"

    markdown = (
        f"{body}\n\n"
        "## Limites\n\n"
        "Montants **indicatifs** pour Casablanca, hors loyer mensuel et fonds de roulement détaillé. "
        "À valider avec devis et bailleurs.\n\n"
        "---\n*Source : modèle de coûts indicatif Invest Search.*"
    )
    zone = profile_dict.get("zone") or "Casablanca"
    return {
        "question": message,
        "answer_markdown": markdown,
        "top_zone": zone,
        "score": 0,
        "risk": 0,
        "category": "Conseil budget",
        "sources": [],
        "kpis": [
            {"label": "Budget", "value": fmt(budget)},
            {"label": "Compatibles", "value": status_kpi},
            {"label": "Étape", "value": "Choisir un type + zone"},
        ],
        "map_focus": _zone_focus(zone) if profile_dict.get("zone") else {"label": "Casablanca", "lat": 33.57, "lon": -7.59, "zoom": 11},
        "related_opportunities": [],
        "retrieved_contexts": [],
        "rag_status": "budget_options",
        "suggested_view": "intelligence",
        "suggested_questions": [
            f"Où ouvrir une pharmacie avec {fmt(budget)} ?",
            "Où ouvrir un commerce à faible concurrence ?",
            "Compare deux quartiers pour ce projet",
        ],
    }
