"""Meta follow-ups about the PREVIOUS answer ("résume", "en deux phrases",
"plus de détails", ...).

These have no new sector/zone/budget — they reformat the current topic. Without
this they fall through to out-of-scope (and the user thinks memory is broken).
We use the accumulated profile to re-present the topic in the requested form.
"""

from __future__ import annotations

from api.services.invest_data import (
    _category_or_default,
    _normalize_text,
    _tokenize,
    _zone_focus,
    get_opportunities,
    get_sector_opportunities,
)
from api.services.conversation.profile import InvestorProfile, business_type_fr
from api.services.conversation.query_rewriter import rewrite_query

_SHORT_KEYS = (
    "deux phrases", "2 phrases", "une phrase", "en bref", "bref", "resume", "resumer",
    "resume moi", "plus court", "court", "concis", "synthese", "synthetise", "tldr",
    "rapidement", "en gros", "en resume", "version courte",
)
_DETAIL_KEYS = (
    "plus de detail", "plus de details", "detaille", "developpe", "plus long",
    "approfondi", "en detail", "explique mieux", "explique plus",
)
# A reformat instruction must not also introduce a new business / zone / amount.
_NEW_TOPIC_HINT = ("ouvrir", "budget", "dh", "dhs", "mad", "combien", "compare", "comparer")


def is_meta_reformat(message: str) -> bool:
    norm = _normalize_text(message)
    if not any(k in norm for k in (_SHORT_KEYS + _DETAIL_KEYS)):
        return False
    # If it clearly starts a new request, it's not a pure reformat.
    if any(h in norm for h in _NEW_TOPIC_HINT) and len(_tokenize(message)) > 8:
        return False
    return True


def _top_opportunity(profile: InvestorProfile):
    if profile.sector and profile.sector != "medical":
        subcat = profile.business_type if (profile.business_type and profile.business_type != profile.sector) else None
        opps = get_sector_opportunities(profile.sector, subcategory=subcat, limit=99)
    elif profile.business_type:
        opps = get_opportunities(_category_or_default(profile.business_type), limit=99)
    else:
        opps = []
    if not opps:
        return None
    if profile.zone:
        match = next((o for o in opps if o["zone"] == profile.zone), None)
        if match:
            return match
    return opps[0]


def build_meta_reformat_answer(profile_dict: dict, message: str) -> dict | None:
    profile = InvestorProfile.from_dict(profile_dict)
    if not (profile.business_type or profile.sector):
        return None  # nothing to reformat yet

    norm = _normalize_text(message)
    label = business_type_fr(profile)

    # "Plus de détails" -> re-run the full analysis on the same topic.
    if any(k in norm for k in _DETAIL_KEYS):
        from api.services.invest_data import build_rag_answer

        standalone = rewrite_query(profile, message)
        resp = build_rag_answer(standalone)
        resp["standalone_query"] = standalone
        return resp

    # Otherwise: a short 2-sentence summary from the computed opportunity.
    top = _top_opportunity(profile)
    if top is None:
        return None
    zone = top.get("zone", "Casablanca")
    score = top.get("score", 0)
    comp = str(top.get("competition_level", "faible")).lower()
    gap = top.get("supply_gap")
    budget_clause = ""
    if profile.budget:
        from api.services import consulting

        budget_clause = f" avec un budget de {consulting.format_mad(profile.budget)}"

    gap_txt = f", supply gap {gap:.0f}/100" if isinstance(gap, (int, float)) else ""
    markdown = (
        f"**En bref —** pour {label}{budget_clause} à Casablanca, la zone prioritaire est "
        f"**{zone}** (score {score:.0f}/100, concurrence {comp}{gap_txt}). "
        f"À confirmer sur le terrain : loyers, flux piéton et ticket moyen."
    )
    return {
        "question": message,
        "answer_markdown": markdown,
        "top_zone": zone,
        "score": score,
        "risk": top.get("risk", 0),
        "category": profile.business_type or profile.sector or "General",
        "sources": [],
        "kpis": [
            {"label": "Zone", "value": zone},
            {"label": "Score", "value": f"{score:.0f}/100"},
            {"label": "Concurrence", "value": comp},
        ],
        "map_focus": _zone_focus(zone),
        "related_opportunities": [],
        "retrieved_contexts": [],
        "rag_status": "summary",
        "suggested_view": "intelligence",
        "suggested_questions": [
            f"Donne-moi plus de détails sur {zone}",
            f"Compare {zone} avec un autre quartier",
            f"Quel budget pour {label} ?",
        ],
    }
