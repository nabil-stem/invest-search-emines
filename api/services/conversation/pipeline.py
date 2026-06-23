"""Conversational orchestration: the turn pipeline.

    user_input + history + investor_profile
        -> update profile
        -> (non-investment / greeting / out-of-scope) pass through unchanged
        -> check missing essential fields -> clarify (one question)
        -> else rewrite a standalone query -> RAG + generation -> answer
        -> attach updated profile (+ debug)

Design choices that keep the existing app intact:
  * Fresh, *complete* investment questions are sent to `build_rag_answer`
    UNCHANGED (so greetings, out-of-scope guardrails and the eval suites keep
    behaving exactly as before).
  * The conversational rewrite only activates on follow-ups (a prior profile
    exists) or declarative-but-incomplete intents (e.g. "je veux ouvrir une
    pharmacie" with no zone -> ask the zone).
"""

from __future__ import annotations

from api.services.invest_data import (
    SECTORS,
    _category_or_default,
    _has_investment_intent,
    _normalize_text,
    _tokenize,
    _zone_focus,
    _zones_from_question,
    build_rag_answer,
)
from api.services import consulting
from api.services.conversation.profile import (
    InvestorProfile,
    business_type_fr,
    is_open_ended,
    is_reset,
    update_profile,
    _is_declarative,
)
from api.services.conversation.query_rewriter import rewrite_query
from api.services.conversation.coverage import (
    build_unsupported_business_answer,
    detect_unsupported_business,
)
from api.services.conversation.intents import (
    build_affordability_answer,
    is_affordability_question,
    is_context_fragment,
)
from api.services.conversation.explain import build_explanation_answer, is_explanatory
from api.services.conversation.factual import build_factual_answer, is_factual_question
from api.services.conversation.cost import build_cost_estimate_answer, is_cost_estimate_question
from api.services.conversation.reformat import build_meta_reformat_answer, is_meta_reformat
from api.services.conversation.typos import correct_typos
from api.services.invest_data import _detected_category, _sector_from_question


def _is_investment_turn(message: str) -> bool:
    words = _tokenize(message)
    normalized = _normalize_text(message)
    return bool(
        _detected_category(message)
        or _sector_from_question(message)
        or consulting.parse_budget(message)
        or _zones_from_question(message)
        or _has_investment_intent(words, normalized)
    )


def missing_fields(profile: InvestorProfile, message: str) -> list[str]:
    """Essential fields still needed before a confident analysis."""
    missing: list[str] = []
    if not (profile.sector or profile.business_type):
        missing.append("sector")
        return missing  # ask the type first
    if profile.objective != "comparaison" and not profile.zone:
        if _is_declarative(message) and not is_open_ended(message):
            missing.append("zone")
    return missing


def _category_for(profile: InvestorProfile) -> str:
    if profile.sector == "medical" and profile.business_type:
        return _category_or_default(profile.business_type)
    return "Small Private Clinic"


def _wrap_quick(markdown: str, status: str, profile: InvestorProfile,
                suggested: list[str] | None = None) -> dict:
    return {
        "question": "",
        "answer_markdown": markdown,
        "top_zone": profile.zone or "Casablanca",
        "score": 0,
        "risk": 0,
        "category": profile.business_type or "General",
        "sources": [],
        "kpis": [
            {"label": "Secteur", "value": profile.sector or "à préciser"},
            {"label": "Type", "value": str(profile.business_type or "à préciser")},
            {"label": "Budget", "value": consulting.format_mad(profile.budget) if profile.budget else "à préciser"},
            {"label": "Zone", "value": profile.zone or "à préciser"},
        ],
        "map_focus": _zone_focus(profile.zone) if profile.zone else {"label": "Casablanca", "lat": 33.57, "lon": -7.59, "zoom": 11},
        "related_opportunities": [],
        "retrieved_contexts": [],
        "rag_status": status,
        "suggested_view": "intelligence",
        "suggested_questions": suggested or [],
    }


def build_clarification(profile: InvestorProfile, missing: list[str]) -> dict:
    if "sector" in missing:
        markdown = (
            "## Précisons votre projet\n\n"
            "Quel **type d'établissement** souhaitez-vous ouvrir à Casablanca ? "
            "Par exemple : pharmacie, clinique, laboratoire, **restaurant, commerce, école "
            "ou salle de sport**. Indiquez aussi votre **budget** si vous voulez une analyse de faisabilité."
        )
        suggested = [
            "Où ouvrir une pharmacie à faible concurrence ?",
            "Où ouvrir un restaurant à Casablanca ?",
            "J'ai un budget de 800 000 DH, que puis-je ouvrir ?",
        ]
        return _wrap_quick(markdown, "needs_clarification", profile, suggested)

    # zone missing
    bt = business_type_fr(profile)
    if profile.budget:
        question = f"Dans **quel quartier de Casablanca** souhaitez-vous évaluer l'ouverture de {bt} ?"
    else:
        question = (
            f"Quel est votre **budget approximatif** et dans **quel quartier de Casablanca** "
            f"souhaitez-vous ouvrir {bt} ?"
        )
    markdown = (
        f"## Une précision pour {bt}\n\n{question}\n\n"
        "Vous pouvez aussi répondre par une zone (ex. *Sidi Moumen*, *Maarif*, *Anfa*) ou demander "
        "*« où ouvrir à faible concurrence ? »* pour que je classe les zones moi-même."
    )
    suggested = [
        f"Où ouvrir {bt} à faible concurrence ?",
        "Sidi Moumen", "Maarif", "Anfa",
    ]
    return _wrap_quick(markdown, "needs_clarification", profile, suggested)


# Deterministic analytical answers that are still data-grounded — we attach the
# retrieved RAG passages so the UI shows the "RAG / sources" evidence on them too
# (the investor sees the grounding), without altering the reliable computed content.
_RAG_EVIDENCE_STATUSES = {
    "budget_advisory", "budget_options", "cost_estimate", "sector_opportunity",
    "sector_zone_analysis", "zone_gap_competition", "zone_comparison",
    "zone_risk_analysis", "coverage_analysis",
}


def _attach_rag_evidence(resp: dict, message: str) -> dict:
    if resp.get("rag_status") not in _RAG_EVIDENCE_STATUSES:
        return resp
    if resp.get("retrieved_contexts"):
        return resp
    try:
        from api.services import rag

        # Lexical/BM25 only: fast (no embedding round-trip) and the evidence panel
        # only needs the relevant *source files*. Diversity-capped like the app.
        query = f"{message} {resp.get('top_zone', '')} Casablanca"
        contexts = rag.cap_per_source(rag.lexical_search(query, top_k=12), 6)
    except Exception:
        return resp
    if not contexts:
        return resp
    resp["retrieved_contexts"] = [
        {
            "title": c.get("title", ""),
            "source_path": c.get("source_path", ""),
            "kind": c.get("kind", "documentation"),
            "score": c.get("score", 0),
            "text": (c.get("text", "") or "")[:500],
        }
        for c in contexts[:4]
    ]
    return resp


# Long analytical answers are shown CONCISE by default (recommendation + key
# figures), with an explicit "plus de détails" offer — unless the user asked for
# the full study. Keeps the demo readable and interactive without losing data.
_CONCISE_STATUSES = {
    "budget_advisory", "cost_estimate", "sector_opportunity", "sector_zone_analysis",
    "zone_gap_competition", "zone_comparison", "zone_risk_analysis", "coverage_analysis",
    "hybrid_ollama", "lexical_metadata_ollama", "lexical_scoring", "hybrid_scoring",
}
_FULL_REQUEST_KEYS = (
    "detail", "complet", "complete", "rapport", "approfondi", "tout savoir",
    "version longue", "etude complete", "exhaustif", "en entier",
)


def _wants_full(message: str) -> bool:
    norm = _normalize_text(message)
    return any(k in norm for k in _FULL_REQUEST_KEYS)


def _apply_conciseness(resp: dict, message: str) -> dict:
    if resp.get("rag_status") not in _CONCISE_STATUSES:
        return resp
    if _wants_full(message):
        return resp
    md = resp.get("answer_markdown", "") or ""
    if len(md) < 650:
        return resp  # already short enough
    resp["full_answer_markdown"] = md  # keep the long version for expansion
    head = md.split("\n## ")[0].strip()  # recommendation / headline section
    kpis = resp.get("kpis", [])[:4]
    kpi_line = " · ".join(f"**{k['label']}** {k['value']}" for k in kpis if k.get("value"))
    out = head
    if kpi_line:
        out += f"\n\n{kpi_line}"
    out += (
        "\n\n*Réponse synthétique. Pour le détail complet (POIs, KPIs, alternatives, risques), "
        "dites **« plus de détails »**.*"
    )
    resp["answer_markdown"] = out
    return resp


def run_turn(
    message: str,
    history: list[dict] | None = None,
    profile_dict: dict | None = None,
    debug: bool = False,
    web_search: bool = False,
) -> dict:
    """Process one conversational turn. Returns a chat answer + updated profile."""
    history = history or []

    # Typo tolerance: detection sees a corrected form ("pharmacei" -> "pharmacie"),
    # but the user's ORIGINAL text is what we echo back for display.
    original_message = message
    message = correct_typos(message)

    if is_reset(message):
        from api.services.llm.prompts import GREETING_RESPONSE
        fresh = InvestorProfile()
        resp = _wrap_quick(GREETING_RESPONSE, "easy_greeting", fresh)
        resp["investor_profile"] = fresh.to_dict()
        if debug:
            resp["debug"] = {"reset": True, "investor_profile": fresh.to_dict()}
        return resp

    prior = InvestorProfile.from_dict(profile_dict)
    has_prior = prior.has_any_field()
    profile = update_profile(InvestorProfile.from_dict(profile_dict), message)

    standalone: str | None = None

    def _answer_message(msg: str) -> dict:
        # Answer a message on its own terms (fresh-style), preserving guardrails
        # and the honest data-gap for unsupported business types.
        # Explanatory questions ("comment fonctionne le scoring", "quelles
        # sources ?") use a dedicated teaching layout instead of the investment
        # note (and avoid build_rag_answer's recommendation merge).
        if is_explanatory(msg):
            explanation = build_explanation_answer(msg)
            if explanation:
                return explanation
        unsupported = detect_unsupported_business(msg)
        if unsupported:
            return build_unsupported_business_answer(msg, unsupported)
        # On a web-search turn the web results are the focus, so skip the slow
        # LLM narrative and keep the fast grounded scoring answer.
        return build_rag_answer(msg, skip_llm=web_search)

    factual = build_factual_answer(message) if is_factual_question(message) else None
    # "Quel budget faut-il pour ouvrir X ?" (no amount given) -> cost estimate.
    cost = build_cost_estimate_answer(message) if is_cost_estimate_question(message) else None
    # Affordability ("que puis-je ouvrir avec ce budget ?") works in any state,
    # fresh OR follow-up — it must not fall into the unsupported-business path.
    affordability = (
        build_affordability_answer(profile.to_dict(), message)
        if is_affordability_question(message)
        else None
    )

    # Meta follow-up about the previous answer ("résume", "en deux phrases",
    # "plus de détails") — only meaningful with prior context.
    meta = (
        build_meta_reformat_answer(profile.to_dict(), message)
        if (has_prior and is_meta_reformat(message))
        else None
    )

    if factual is not None:
        # Pure data lookup ("population d'Anfa ?", "densité de Maarif ?") -> short
        # factual answer, regardless of conversation state.
        resp = factual
    elif cost is not None:
        resp = cost
    elif affordability is not None:
        resp = affordability
    elif meta is not None:
        resp = meta
    elif not has_prior:
        # FRESH turn: preserve every existing behaviour (greetings, out-of-scope
        # guardrails, deterministic answers). We only attach the extracted
        # profile so the next turn has context.
        resp = _answer_message(message)
    elif is_context_fragment(message):
        # Thin fragment ("Sidi Moumen", "compare avec Maarif", "et un café") that
        # only makes sense against the profile -> rewrite with context.
        missing = missing_fields(profile, message)
        if missing:
            resp = build_clarification(profile, missing)
        else:
            standalone = rewrite_query(profile, message)
            resp = build_rag_answer(standalone, category=_category_for(profile), skip_llm=web_search)
            resp["standalone_query"] = standalone
    else:
        # A real new question mid-conversation -> answer the LAST message instead
        # of forcing it into the previous project (the reported bug). Memory is
        # still updated for later turns, but it no longer overrides intent.
        resp = _answer_message(message)

    # Surface the RAG evidence on data-grounded deterministic answers too.
    resp = _attach_rag_evidence(resp, message)
    # Concise by default, with a "plus de détails" offer (unless full was asked).
    resp = _apply_conciseness(resp, original_message)

    # Optional web-search fallback: only when the user explicitly asks for it.
    # Appended AFTER conciseness so it is never truncated. Clearly unverified.
    if web_search:
        from api.services.web_search import format_web_section, search_web

        results = search_web(standalone or message)
        resp["web_results"] = results
        resp["answer_markdown"] = (resp.get("answer_markdown", "") or "") + format_web_section(results)

    resp["investor_profile"] = profile.to_dict()
    # Always echo the user's ORIGINAL text (never the corrected/rewritten form),
    # so the UI displays exactly what was typed.
    resp["question"] = original_message
    if original_message != message:
        resp["corrected_query"] = message  # transparency only
    if debug:
        resp["debug"] = {
            "investor_profile": profile.to_dict(),
            "standalone_query": standalone,
            "corrected_query": message if original_message != message else None,
            "missing_fields": missing_fields(profile, message) if has_prior else [],
            "has_prior": has_prior,
            "history_used": history[-6:],
            "retrieved_sources": [c.get("source_path") for c in resp.get("retrieved_contexts", [])],
        }
    return resp
