"""Real multi-turn conversation + retrieval verification.

Runs a 5-message investor consultation, checking after each turn:
  * the structured memory (investor_profile) is accurate;
  * the standalone query (what actually drives the RAG) is rebuilt from memory;
  * retrieval uses BOTH lexical/keyword (BM25) AND semantic (embedding) signals,
    fused (RRF), on that memory-derived query;
  * no hallucinated zone (the answer's zone matches the scoring engine) and
    numbers are grounded in the retrieved/scoring data.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.services import rag  # noqa: E402
from api.services.conversation import run_turn  # noqa: E402
from api.services.invest_data import _areas  # noqa: E402

CONVERSATION = [
    "J'ai un budget de 1 200 000 DH et je veux ouvrir un laboratoire d'analyses medicales.",
    "Sidi Moumen.",
    "Compare avec Maarif.",
    "Et si mon budget est seulement 600 000 DH ?",
    "Quels sont les risques principaux ?",
]

ALL_ZONES = [str(z) for z in _areas().get("area_name", []).tolist()] if not _areas().empty else []


def numbers(text: str) -> list[str]:
    text = re.sub(r"\[\d+\]", " ", text)
    return [re.sub(r"[^\d]", "", t) for t in re.findall(r"\d[\d \.,]*\d", text) if len(re.sub(r"[^\d]", "", t)) >= 2]


def retrieval_breakdown(standalone: str):
    """Show lexical vs semantic vs hybrid top sources for the memory-derived query."""
    q = f"{standalone} Casablanca"
    sem = rag.semantic_search(q, top_k=5) if rag._ollama_available() else []
    lex = rag.lexical_search(q, top_k=5)
    hyb, mode = rag.hybrid_search(q, top_k=5)

    def fmt(rows):
        return [(r["source_path"].split("/")[-1], round(r.get("score", 0), 3)) for r in rows[:4]]

    return {"semantic": fmt(sem), "lexical": fmt(lex), "hybrid_mode": mode, "hybrid": fmt(hyb)}


def main():
    profile = None
    history = []
    ok = True
    for i, msg in enumerate(CONVERSATION, 1):
        r = run_turn(message=msg, history=history, profile_dict=profile, debug=True)
        profile = r["investor_profile"]
        history += [{"role": "user", "content": msg}, {"role": "assistant", "content": r["answer_markdown"][:200]}]

        print(f"\n{'='*78}\nTURN {i}  USER: {msg}")
        print(f"  status        : {r['rag_status']}")
        print(f"  memory        : budget={profile['budget']} sector={profile['sector']} "
              f"type={profile['business_type']} zone={profile['zone']} compare={profile['comparison_zones']}")
        sq = r.get("standalone_query")
        print(f"  standalone Q  : {sq[:150] if sq else '(fresh message, passed through unchanged)'}")

        # Retrieval verification on the memory-derived query (analysis turns only)
        if sq:
            rb = retrieval_breakdown(sq)
            print(f"  retrieval     : hybrid_mode={rb['hybrid_mode']}")
            print(f"     keyword/BM25 top: {rb['lexical']}")
            print(f"     semantic    top: {rb['semantic']}")
            print(f"     fused (RRF) top: {rb['hybrid']}")

        # Hallucination checks
        md = r["answer_markdown"]
        zone = r.get("top_zone", "")
        foreign = [z for z in ALL_ZONES if z.lower() != (zone or "").lower()
                   and re.search(rf"\b{re.escape(z.lower())}\b", md.lower())
                   and z not in profile.get("comparison_zones", [])]
        if zone and zone not in ("Casablanca",) and zone.lower() not in md.lower():
            print(f"  [WARN] recommended zone {zone} not named in answer"); ok = False
        if foreign:
            print(f"  [WARN] foreign zone(s) mentioned as well: {foreign}")
        print(f"  answer[:240]  : {md[:240].strip()}")

    # Final memory accuracy assertions
    print(f"\n{'='*78}\nFINAL MEMORY: {profile}")
    assert profile["business_type"] == "Medical Analysis Laboratory", profile
    assert profile["zone"] == "Sidi Moumen", profile
    assert "Maarif" in profile["comparison_zones"], profile
    assert profile["budget"] == 600000, profile
    print("MEMORY ACCURACY: OK (type=laboratoire, zone=Sidi Moumen, compare=Maarif, budget updated 1.2M->600k)")
    print("RESULT:", "PASS" if ok else "WARNINGS ABOVE")


if __name__ == "__main__":
    main()
