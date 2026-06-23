"""A/B accuracy comparison of two Ollama chat models for Invest Search RAG.

Compares (by default) qwen3:8b vs qwen2.5:7b on an identical set of in-scope
investment questions. For each (model, question) it pins the model via
OLLAMA_CHAT_MODEL, builds the *same* scoring context + retrieved contexts, then
asks the model to write the investment note (the raw LLM output, isolated from
the app's deterministic fallback/merge so we measure the model itself).

Each answer is scored on a faithfulness / precision rubric (0-100):

  grounded_zone     25  recommended zone (from the deterministic scoring engine)
                        is named in the answer
  numbers_grounded  15  share of substantive numbers in the answer that trace
                        back to the provided scoring data / contexts
  has_citation      15  uses [n] / "Source" references
  no_foreign_zone   10  does not present a *different* Casablanca district as the
                        recommendation (hallucinated location)
  has_risk          10  includes a risks / limits / uncertainty section
  has_next_steps     9  includes field-validation next steps
  has_population      8  cites population
  has_density         8  cites density

Plus latency and word-count (reported, not scored).

Usage:
  python scripts/ab_eval_models.py
  python scripts/ab_eval_models.py --models qwen3:latest qwen2.5:7b --runs 1

Requires Ollama running with the models installed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.services import invest_data as D  # noqa: E402
from api.services.llm import providers  # noqa: E402
from api.services.rag import hybrid_search  # noqa: E402

OUT_JSON = ROOT / "artifacts" / "ab_model_eval.json"

DEFAULT_MODELS = ["qwen3:latest", "qwen2.5:7b"]

# In-scope questions WITHOUT explicit zone names so they reach the LLM path
# (questions naming a district are answered deterministically and bypass the
# model, so they can't discriminate model quality).
QUESTIONS = [
    {"q": "Ou ouvrir une pharmacie a faible concurrence a Casablanca ?", "cat": "Pharmacy"},
    {"q": "Quel est le meilleur quartier pour un laboratoire d'analyses medicales ?", "cat": "Medical Analysis Laboratory"},
    {"q": "Genere un rapport investisseur pour une clinique de jour.", "cat": "Small Private Clinic"},
    {"q": "Quelle zone privilegier pour un cabinet dentaire ?", "cat": "Dental Clinic"},
    {"q": "Recommande un emplacement pour un centre de radiologie.", "cat": "Radiology Center"},
    {"q": "Ou implanter une clinique veterinaire avec une bonne demande ?", "cat": "Veterinary Clinic"},
    {"q": "Quelle est la meilleure opportunite pour un cabinet de dermatologie ?", "cat": "Dermatology Cabinet"},
]


def _zone_names() -> list[str]:
    areas = D._areas()
    if areas.empty or "area_name" not in areas:
        return []
    return [str(z) for z in areas["area_name"].dropna().unique()]


ALL_ZONES = _zone_names()


def _numbers(text: str) -> list[str]:
    """Substantive numbers in the text (>=2 digits or decimals), excluding
    citation markers like [1] and list ordinals so they don't skew grounding."""
    text = re.sub(r"\[\d+\]", " ", text)
    raw = re.findall(r"\d[\d  .,]*\d|\d", text)
    out = []
    for token in raw:
        digits = re.sub(r"[^\d]", "", token)
        if len(digits) >= 2:  # skip bare single digits (list / citation noise)
            out.append(digits)
    return out


def _grounded_number_pool(scoring: dict, contexts: list[dict]) -> set[str]:
    pool: set[str] = set()
    top = scoring.get("top_opportunity", {})
    for value in [
        scoring.get("score"), scoring.get("risk"),
        top.get("population"), top.get("density"), top.get("providers"),
        top.get("providers_per_100k"), top.get("supply_gap"),
    ]:
        if value is None:
            continue
        pool.add(re.sub(r"[^\d]", "", str(value)))
        pool.add(re.sub(r"[^\d]", "", str(int(round(float(value)))) if isinstance(value, (int, float)) else str(value)))
    for ctx in contexts:
        for num in _numbers(ctx.get("text", "")):
            pool.add(num)
    pool.discard("")
    return pool


def _score_answer(answer: str, scoring: dict, contexts: list[dict]) -> dict:
    low = answer.lower()
    top_zone = str(scoring.get("top_zone", ""))

    grounded_zone = top_zone.lower() in low if top_zone else False

    # Foreign zone presented as recommendation: any *other* district named.
    foreign = [
        z for z in ALL_ZONES
        if z.lower() != top_zone.lower() and re.search(rf"\b{re.escape(z.lower())}\b", low)
    ]
    no_foreign_zone = len(foreign) == 0

    has_citation = bool(re.search(r"\[\d+\]", answer)) or "source" in low
    has_population = "population" in low
    has_density = "densit" in low
    has_risk = any(kw in low for kw in ["risque", "limite", "incertain", "fiabilit"])
    has_next_steps = any(kw in low for kw in ["prochaine", "etape", "étape", "terrain", "valid"])
    # A *genuine* refusal is short and gives no recommendation. Merely mentioning
    # "hors perimetre" inside a complete, zone-grounded answer (some models echo
    # the system prompt's scope language) is not a refusal and must not be
    # penalised as one.
    mentions_scope = "hors perimetre" in low or "hors périmètre" in low
    refused = mentions_scope and (not grounded_zone or len(answer.split()) < 50)

    nums = _numbers(answer)
    pool = _grounded_number_pool(scoring, contexts)
    grounded_nums = [n for n in nums if n in pool]
    numbers_grounded = (len(grounded_nums) / len(nums)) if nums else 1.0

    composite = (
        25 * grounded_zone
        + 15 * numbers_grounded
        + 15 * has_citation
        + 10 * no_foreign_zone
        + 10 * has_risk
        + 9 * has_next_steps
        + 8 * has_population
        + 8 * has_density
    )
    if refused:  # refusing an in-scope question is a hard failure
        composite *= 0.3

    return {
        "composite": round(composite, 1),
        "grounded_zone": grounded_zone,
        "no_foreign_zone": no_foreign_zone,
        "foreign_zones": foreign,
        "has_citation": has_citation,
        "has_population": has_population,
        "has_density": has_density,
        "has_risk": has_risk,
        "has_next_steps": has_next_steps,
        "refused_in_scope": refused,
        "numbers_grounded": round(numbers_grounded, 3),
        "n_numbers": len(nums),
        "word_count": len(answer.split()),
    }


def _build_inputs(question: str, category: str) -> tuple[dict, list[dict], str]:
    """Reproduce the scoring context + retrieved contexts the app would build."""
    base = D.build_answer_enriched(question=question, category=category)
    top_opp = base["related_opportunities"][0] if base["related_opportunities"] else {}
    search_query = f"{question} {base['category']} {base['top_zone']} Casablanca"
    try:
        contexts, _ = hybrid_search(query=search_query, top_k=8)
    except Exception:
        contexts = []
    scoring = {
        "top_zone": base["top_zone"],
        "category": base["category"],
        "score": base["score"],
        "risk": base["risk"],
        "top_opportunity": top_opp,
    }
    return scoring, contexts, base["top_zone"]


def evaluate_model(model: str, runs: int) -> dict:
    os.environ["OLLAMA_CHAT_MODEL"] = model
    os.environ["LLM_PROVIDER"] = "ollama"
    rows = []
    for item in QUESTIONS:
        scoring, contexts, top_zone = _build_inputs(item["q"], item["cat"])
        best = None
        for _ in range(runs):
            t0 = time.time()
            try:
                answer, _provider = providers.generate_answer(item["q"], scoring, contexts)
                elapsed = round(time.time() - t0, 2)
                scored = _score_answer(answer, scoring, contexts)
                scored["elapsed_s"] = elapsed
                scored["error"] = None
            except Exception as exc:  # noqa: BLE001
                scored = {"composite": 0.0, "error": str(exc), "elapsed_s": round(time.time() - t0, 2)}
                answer = ""
            if best is None or scored["composite"] > best["composite"]:
                best = scored
                best_answer = answer
        best["question"] = item["q"]
        best["expected_zone"] = top_zone
        best["answer_preview"] = best_answer[:400]
        best["answer_full"] = best_answer[:2000]
        rows.append(best)
        flag = "ERR" if best.get("error") else f"{best['composite']:.0f}"
        print(f"  [{model:>14}] {flag:>4}  {best.get('elapsed_s','?')!s:>6}s  {item['q'][:46]}")

    scored_rows = [r for r in rows if not r.get("error")]
    n = len(scored_rows) or 1
    agg = {
        "composite": round(sum(r["composite"] for r in scored_rows) / n, 1),
        "grounded_zone": round(sum(r["grounded_zone"] for r in scored_rows) / n, 3),
        "no_foreign_zone": round(sum(r["no_foreign_zone"] for r in scored_rows) / n, 3),
        "has_citation": round(sum(r["has_citation"] for r in scored_rows) / n, 3),
        "has_risk": round(sum(r["has_risk"] for r in scored_rows) / n, 3),
        "numbers_grounded": round(sum(r["numbers_grounded"] for r in scored_rows) / n, 3),
        "refused_in_scope": sum(r.get("refused_in_scope", False) for r in scored_rows),
        "avg_latency_s": round(sum(r["elapsed_s"] for r in scored_rows) / n, 2),
        "avg_words": round(sum(r["word_count"] for r in scored_rows) / n, 1),
        "errors": len(rows) - len(scored_rows),
    }
    return {"model": model, "aggregate": agg, "per_question": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--runs", type=int, default=1, help="runs per question; best composite kept")
    args = parser.parse_args()

    print(f"A/B model eval: {args.models}  ({len(QUESTIONS)} questions, runs={args.runs})\n")
    results = []
    for model in args.models:
        print(f"Model: {model}")
        results.append(evaluate_model(model, args.runs))
        print()

    report = {"models": args.models, "n_questions": len(QUESTIONS), "results": results}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== AGGREGATE ===")
    header = f"{'model':<16} {'comp':>6} {'zone':>6} {'noForgn':>8} {'cite':>6} {'risk':>6} {'numGnd':>7} {'lat(s)':>7} {'words':>6}"
    print(header)
    print("-" * len(header))
    for r in results:
        a = r["aggregate"]
        print(
            f"{r['model']:<16} {a['composite']:>6.1f} {a['grounded_zone']:>6.2f} "
            f"{a['no_foreign_zone']:>8.2f} {a['has_citation']:>6.2f} {a['has_risk']:>6.2f} "
            f"{a['numbers_grounded']:>7.2f} {a['avg_latency_s']:>7.1f} {a['avg_words']:>6.0f}"
        )
    if len(results) >= 2:
        best = max(results, key=lambda r: r["aggregate"]["composite"])
        print(f"\nHighest composite accuracy: {best['model']} ({best['aggregate']['composite']:.1f}/100)")
    print(f"\nFull results -> {OUT_JSON}")


if __name__ == "__main__":
    main()
