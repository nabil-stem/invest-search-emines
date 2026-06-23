"""Dedicated RAG path for explanatory / informational questions.

`build_rag_answer` is built around an investment *recommendation*: when the LLM
answer lacks population/density it appends the deterministic zone-recommendation
block. That is wrong for "comment fonctionne le scoring ?" / "quelles sont les
sources ?" — the answer would get a recommendation bolted on.

So explanatory questions are handled here instead: retrieve context, generate
with the EXPLANATION template (selected automatically by prompts.build_prompt),
and return the answer as-is (no recommendation merge). Falls back to a
context-based summary if the local LLM is unavailable.
"""

from __future__ import annotations

from api.services.llm.prompts import is_explanatory  # re-exported for callers

__all__ = ["is_explanatory", "build_explanation_answer"]


def build_explanation_answer(message: str) -> dict | None:
    from api.services import rag
    from api.services.llm import generate_answer

    query = f"{message} Casablanca"
    try:
        contexts, mode = rag.hybrid_search(query=query, top_k=8)
    except Exception:
        contexts, mode = [], "none"

    retrieved = [
        {
            "title": c.get("title", ""),
            "source_path": c.get("source_path", ""),
            "kind": c.get("kind", "documentation"),
            "score": c.get("score", 0),
            "text": (c.get("text", "") or "")[:700],
        }
        for c in contexts[:5]
    ]
    sources = rag.source_cards_from_contexts(contexts) if contexts else []

    scoring = {"top_zone": "", "category": "", "score": 0, "risk": 0, "top_opportunity": {}}
    try:
        answer_md, provider = generate_answer(message, scoring, contexts)
        status = f"{mode}_{provider}"
    except Exception:
        answer_md = _fallback_explanation(message, contexts)
        status = f"{mode}_scoring" if contexts else "explanation_unavailable"

    return {
        "question": message,
        "answer_markdown": answer_md,
        "top_zone": "Casablanca",
        "score": 0,
        "risk": 0,
        "category": "Explication",
        "sources": sources,
        "kpis": [],
        "map_focus": {"label": "Casablanca", "lat": 33.57, "lon": -7.59, "zoom": 11},
        "related_opportunities": [],
        "retrieved_contexts": retrieved,
        "rag_status": status,
        "suggested_view": "intelligence",
        "suggested_questions": [
            "Quelles sont les sources de données utilisées ?",
            "Comment est calculé le supply gap ?",
            "Quels secteurs sont couverts ?",
        ],
    }


def _fallback_explanation(message: str, contexts: list[dict]) -> str:
    if not contexts:
        return (
            "## Réponse\n\nJe n'ai pas trouvé de contexte documentaire suffisant pour expliquer "
            "ce point de façon fiable. Reformulez (méthodologie, scoring, supply gap, sources) "
            "ou réindexez la base documentaire.\n"
        )
    lines = "\n".join(
        f"- **{c.get('source_path', '?').split('/')[-1]}** : {(c.get('text', '') or '')[:200].strip()}…"
        for c in contexts[:4]
    )
    return (
        "## Réponse (extraits documentaires)\n\n"
        "Le modèle local est indisponible ; voici les passages les plus pertinents récupérés "
        "par la recherche, sans synthèse générée :\n\n"
        f"{lines}\n\n---\n*Sources : documentation et données du projet Invest Search.*"
    )
