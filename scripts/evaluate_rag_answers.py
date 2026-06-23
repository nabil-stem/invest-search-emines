"""Evaluation harness for RAG answer quality."""

import json
import time
from pathlib import Path

import requests

API = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[1] / "artifacts" / "rag_eval_results.json"

QUESTIONS = [
    "Ou ouvrir une pharmacie a faible concurrence ?",
    "Comparer Anfa et Maarif pour une clinique",
    "Quel quartier est le meilleur pour un laboratoire d'analyses ?",
    "Quels sont les risques a Sidi Moumen ?",
    "Genere un rapport investisseur pour une clinique de jour",
    "Quels quartiers ont une faible couverture medicale ?",
    "bonjour",
    "hi",
]


def evaluate_one(question: str) -> dict:
    t0 = time.time()
    try:
        r = requests.post(
            f"{API}/api/chat",
            json={"message": question, "category": "Small Private Clinic", "locale": "fr"},
            timeout=35,
        )
        r.raise_for_status()
        d = r.json()
        elapsed = round(time.time() - t0, 2)
        answer = d.get("answer_markdown", "")
        return {
            "question": question,
            "elapsed_s": elapsed,
            "rag_status": d.get("rag_status"),
            "top_zone": d.get("top_zone"),
            "score": d.get("score"),
            "sources_count": len(d.get("sources", [])),
            "contexts_count": len(d.get("retrieved_contexts", [])),
            "answer_length": len(answer),
            "has_risks": any(kw in answer.lower() for kw in ["risque", "risk", "limite", "incertai"]),
            "has_sources": any(kw in answer for kw in ["[1]", "[2]", "Sources", "source"]),
            "has_kpis": any(kw in answer.lower() for kw in ["kpi", "demographie", "concurrence", "supply"]),
            "answer_preview": answer[:300],
        }
    except Exception as exc:
        return {
            "question": question,
            "elapsed_s": round(time.time() - t0, 2),
            "error": str(exc),
        }


def main():
    print(f"Evaluating {len(QUESTIONS)} questions against {API}...")
    results = []
    for q in QUESTIONS:
        print(f"  Q: {q[:60]}...", end=" ", flush=True)
        result = evaluate_one(q)
        print(f"-> {result.get('rag_status', 'ERROR')} in {result.get('elapsed_s', '?')}s")
        results.append(result)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults written to {OUT}")

    print("\n=== SUMMARY ===")
    for r in results:
        status = r.get("rag_status", "ERROR")
        t = r.get("elapsed_s", "?")
        src = r.get("sources_count", 0)
        risks = "Y" if r.get("has_risks") else "N"
        cited = "Y" if r.get("has_sources") else "N"
        print(f"  [{status:20s}] {str(t):>5s}s  src={src}  risks={risks}  cited={cited}  | {r['question'][:50]}")


if __name__ == "__main__":
    main()
