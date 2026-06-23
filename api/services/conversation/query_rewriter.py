"""Turn the accumulated investor profile into a self-contained RAG query.

The RAG / scoring engine is stateless and routes on the *text* of the question
(budget amount, zone names, "comparer", category keywords). So the rewritten
query must (a) read as a complete standalone request and (b) contain the keywords
that make `build_rag_answer` route to the right analysis.
"""

from __future__ import annotations

from api.services.conversation.profile import InvestorProfile, business_type_fr


def _budget_clause(profile: InvestorProfile) -> str:
    if not profile.budget:
        return ""
    # Raw "<int> DH" so consulting.parse_budget reliably re-parses it downstream.
    return f"avec un budget de {int(profile.budget)} DH "


def rewrite_query(profile: InvestorProfile, message: str) -> str:
    """Produce a standalone French query from the profile."""
    bt = business_type_fr(profile)

    # Comparison: "Comparer ... entre A et B ..." triggers the comparison route.
    if profile.objective == "comparaison" and profile.zone and profile.comparison_zones:
        zones = [profile.zone] + [z for z in profile.comparison_zones if z != profile.zone]
        budget_note = "Tenir compte du budget deja indique comme contrainte qualitative. " if profile.budget else ""
        return (
            f"Comparer l'opportunité d'ouvrir {bt} "
            f"entre {' et '.join(zones)} à {profile.city}. "
            f"{budget_note}"
            "Analyser la concurrence, la densité, la demande, le risque de saturation "
            "et recommander la meilleure zone."
        )

    # Specific zone: feasibility analysis anchored on that zone.
    if profile.zone:
        budget = _budget_clause(profile)
        lead = f"L'utilisateur dispose d'un budget de {int(profile.budget)} DH et " if profile.budget else "L'utilisateur "
        return (
            f"{lead}souhaite ouvrir {bt} à {profile.zone}, {profile.city}. "
            "Évaluer la faisabilité, la concurrence, la demande locale, les risques, "
            "les données disponibles sur les établissements et donner une recommandation d'investissement."
        )

    # Open-ended: let the engine find the best zone.
    budget = _budget_clause(profile)
    return (
        f"Où ouvrir {bt} {budget}à {profile.city} à faible concurrence ? "
        "Évaluer les meilleures zones, la demande, la concurrence et les risques."
    )
