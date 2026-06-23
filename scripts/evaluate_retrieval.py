"""Retrieval-quality evaluation for the Invest Search RAG.

Compares three retrieval strategies on a small labeled set of
(query -> expected source files):

  * semantic  - cosine similarity over Ollama embeddings
  * lexical   - BM25 over the chunk text
  * hybrid    - Reciprocal Rank Fusion of the two (what the app uses)

Metrics (computed at the *source file* level, since several chunks map to one
file): Precision@k, Recall@k, Hit@k and MRR. Results are printed and written to
artifacts/retrieval_eval.json.

Run:  python scripts/evaluate_retrieval.py [--k 5]

This talks directly to the RAG index (no API server needed) but does require
Ollama to be running for the semantic/hybrid rows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.services import rag  # noqa: E402

OUT = ROOT / "artifacts" / "retrieval_eval.json"

# Labeled set: query -> list of source_path substrings considered relevant.
# Substring match keeps labels robust to chunk suffixes (e.g. "#3").
LABELED_QUERIES: list[dict] = [
    {
        "query": "methodologie de calcul du score d'investissement",
        "relevant": ["docs/methodology.md"],
    },
    {
        "query": "dictionnaire des donnees colonnes area_indicators",
        "relevant": ["docs/data_dictionary.md"],
    },
    {
        "query": "supply gap et indice de sous-equipement par quartier",
        "relevant": [
            "data/processed/area_indicators.csv",
            "docs/methodology.md",
            "invest_search_medical_casablanca_research.md",
            "docs/data_dictionary.md",
        ],
    },
    {
        "query": "liste des etablissements medicaux pharmacies cliniques nettoyes",
        "relevant": ["data/processed/medical_facilities_clean.csv"],
    },
    {
        "query": "offre par specialite niveau de concurrence prestataires",
        "relevant": [
            "data/processed/specialty_supply.csv",
            "invest_search_medical_casablanca_research.md",
            "docs/sources.md",
            "docs/data_dictionary.md",
        ],
    },
    {
        "query": "sources de donnees OpenStreetMap ministere de la sante",
        "relevant": ["docs/sources.md"],
    },
    {
        "query": "comment fonctionne le moteur de scoring d'opportunite",
        "relevant": ["docs/methodology.md", "README.md"],
    },
    {
        "query": "population densite et quartiers de Casablanca",
        "relevant": [
            "data/processed/area_indicators.csv",
            "data/manual/hcp_rgph_2024_casablanca.csv",
            "docs/sources.md",
            "docs/methodology.md",
        ],
    },
    {
        "query": "restaurant restauration supply gap Hay Hassani Casablanca sector_supply",
        "relevant": ["data/processed/zone_profiles/food_hay_hassani.md", "data/processed/sector_supply.csv"],
    },
    {
        "query": "commerce retail competition Ain Chock providers per 100k",
        "relevant": ["data/processed/zone_profiles/retail_ain_chock.md", "data/processed/sector_supply.csv"],
    },
    {
        "query": "ecole education scoring Sidi Moumen competition level",
        "relevant": ["data/processed/zone_profiles/education_sidi_moumen.md", "data/processed/sector_supply.csv"],
    },
    {
        "query": "wellness fitness Hay Hassani poids scoring sectoriel",
        "relevant": ["data/processed/zone_profiles/wellness_hay_hassani.md", "data/processed/sector_supply.csv"],
    },
    {
        "query": "limites fiabilite et incertitude des donnees",
        "relevant": ["docs/methodology.md", "docs/sources.md"],
    },
    {
        "query": "presentation generale de la plateforme Invest Search",
        "relevant": ["README.md", "invest_search_medical_casablanca_research.md", "docs/methodology.md"],
    },
]


def _candidate_k(k: int) -> int:
    return max(k, k * rag.CANDIDATE_MULTIPLIER)


def _retrieve(mode: str, query: str, k: int) -> list[dict]:
    """Retrieve top-k for a mode, applying the same per-source diversity cap the
    app uses so the three strategies are compared on equal footing."""
    ck = _candidate_k(k)
    if mode == "semantic":
        return rag.cap_per_source(rag.semantic_search(query, top_k=ck), k)
    if mode == "lexical":
        return rag.cap_per_source(rag.lexical_search(query, top_k=ck), k)
    if mode == "hybrid":
        results, _mode = rag.hybrid_search(query, top_k=k)
        return results
    raise ValueError(mode)


def _is_relevant(source_path: str, relevant: list[str]) -> bool:
    return any(rel in source_path for rel in relevant)


def _score_query(results: list[dict], relevant: list[str], k: int) -> dict:
    top = results[:k]
    hits = [r for r in top if _is_relevant(r.get("source_path", ""), relevant)]
    # Recall at the *file* level: how many expected files appear in top-k.
    found_files = {
        rel for rel in relevant if any(rel in r.get("source_path", "") for r in top)
    }
    rr = 0.0
    for rank, r in enumerate(top, start=1):
        if _is_relevant(r.get("source_path", ""), relevant):
            rr = 1.0 / rank
            break
    return {
        "precision_at_k": len(hits) / k if k else 0.0,
        "recall_at_k": len(found_files) / len(relevant) if relevant else 0.0,
        "hit_at_k": 1.0 if hits else 0.0,
        "reciprocal_rank": rr,
        "top_sources": [r.get("source_path", "") for r in top[:k]],
    }


def evaluate(k: int) -> dict:
    modes = ["semantic", "lexical", "hybrid"]
    ollama_up = rag._ollama_available()
    if not ollama_up:
        print("WARNING: Ollama not reachable - semantic is empty; hybrid uses lexical fallback.\n")

    report: dict = {"k": k, "ollama_available": ollama_up, "modes": {}, "per_query": []}

    per_query_rows = []
    aggregate = {m: {"precision_at_k": [], "recall_at_k": [], "hit_at_k": [], "reciprocal_rank": []} for m in modes}

    for item in LABELED_QUERIES:
        row = {"query": item["query"], "relevant": item["relevant"], "modes": {}}
        for mode in modes:
            try:
                results = _retrieve(mode, item["query"], k)
            except Exception as exc:  # noqa: BLE001
                results = []
                row["modes"][mode] = {"error": str(exc)}
                continue
            scored = _score_query(results, item["relevant"], k)
            row["modes"][mode] = scored
            for metric in aggregate[mode]:
                aggregate[mode][metric].append(scored[metric])
        per_query_rows.append(row)

    report["per_query"] = per_query_rows
    for mode in modes:
        vals = aggregate[mode]
        n = len(vals["precision_at_k"]) or 1
        report["modes"][mode] = {
            "precision_at_k": round(sum(vals["precision_at_k"]) / n, 4),
            "recall_at_k": round(sum(vals["recall_at_k"]) / n, 4),
            "hit_at_k": round(sum(vals["hit_at_k"]) / n, 4),
            "mrr": round(sum(vals["reciprocal_rank"]) / n, 4),
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5, help="top-k cutoff for metrics")
    args = parser.parse_args()

    print(f"Building / loading RAG index...")
    rag.load_index()
    print(f"Evaluating retrieval on {len(LABELED_QUERIES)} queries (k={args.k})...\n")

    report = evaluate(args.k)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{'mode':<10} {'P@k':>8} {'Recall@k':>10} {'Hit@k':>8} {'MRR':>8}")
    print("-" * 48)
    for mode, m in report["modes"].items():
        print(
            f"{mode:<10} {m['precision_at_k']:>8.3f} {m['recall_at_k']:>10.3f} "
            f"{m['hit_at_k']:>8.3f} {m['mrr']:>8.3f}"
        )
    print(f"\nFull results -> {OUT}")


if __name__ == "__main__":
    main()
