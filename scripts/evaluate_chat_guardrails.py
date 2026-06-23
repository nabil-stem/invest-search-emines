"""Guardrail acceptance tests for the Invest Search chat endpoint.

Runs a battery of cases against POST /api/chat and asserts that the backend
honours explicit zone intent, fuzzy zone matching, category detection,
clarification, out-of-scope guards, and existing easy behaviours.

Usage:
    python scripts/evaluate_chat_guardrails.py
    CHAT_API=http://127.0.0.1:8078 python scripts/evaluate_chat_guardrails.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

API = os.environ.get("CHAT_API", "http://127.0.0.1:8000").rstrip("/")
ENDPOINT = f"{API}/api/chat"


def ask(message: str) -> dict:
    body = json.dumps({"message": message, "category": "Small Private Clinic", "locale": "fr"}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.load(resp)


def contains(answer: dict, needle: str) -> bool:
    return needle.lower() in (answer.get("answer_markdown", "") or "").lower()


# Each case: (label, question, assertion(answer) -> (ok, detail))
CASES = [
    # --- Zone priority ---
    ("zone-1 concurrence+gap maarif",
     "Analyser la concurrence et le supply gap en maarif",
     lambda a: (a["top_zone"] == "Maarif" and contains(a, "maarif")
                and a["rag_status"] != "semantic_ollama",
                f"top_zone={a['top_zone']} status={a['rag_status']}")),
    ("zone-2 fuzzy maariff",
     "analyser concurrence et supply gap a maariff",
     lambda a: (a["top_zone"] == "Maarif", f"top_zone={a['top_zone']}")),
    ("zone-3 count pharmacie maarif",
     "combien de pharmacie a maarif",
     lambda a: (a["top_zone"] == "Maarif" and any(ch.isdigit() for ch in a.get("answer_markdown", "")),
                f"top_zone={a['top_zone']}")),
    ("zone-4 risque sidi moumene",
     "risque sidi moumene",
     lambda a: (a["top_zone"] == "Sidi Moumen", f"top_zone={a['top_zone']}")),

    # --- Category detection ---
    ("cat-5 supply gap pharmacie maarif",
     "supply gap pharmacie maarif",
     lambda a: (a["top_zone"] == "Maarif" and a["category"] == "Pharmacy",
                f"top_zone={a['top_zone']} cat={a['category']}")),
    ("cat-6 supply gap veterinaire anfa",
     "supply gap veterinaire anfa",
     lambda a: (a["top_zone"] == "Anfa" and a["category"] == "Veterinary Clinic",
                f"top_zone={a['top_zone']} cat={a['category']}")),
    ("cat-7 clinique de jour not lab",
     "analyse complete pour ouvrir une clinique de jour a Casablanca",
     lambda a: (a["category"] == "Small Private Clinic", f"cat={a['category']}")),

    # --- Clarification ---
    ("clar-8 supply gap maarif (no category)",
     "supply gap maarif",
     lambda a: (a["top_zone"] == "Maarif"
                and (a["rag_status"] == "needs_clarification" or contains(a, "type d'etablissement")
                     or contains(a, "type d'établissement")),
                f"top_zone={a['top_zone']} status={a['rag_status']}")),
    ("clar-9 je veux investir",
     "je veux investir",
     lambda a: (a["rag_status"] == "needs_clarification"
                and len(a.get("suggested_questions", [])) >= 2,
                f"status={a['rag_status']} suggestions={len(a.get('suggested_questions', []))}")),

    # --- Out of scope ---
    ("oos-10 ronaldo",
     "chercher la mere de Cristiano Ronaldo",
     lambda a: (a["rag_status"] == "out_of_scope_question" and a["top_zone"] != "Anfa",
                f"status={a['rag_status']} top_zone={a['top_zone']}")),
    ("oos-11 clinique marrakech",
     "ou ouvrir une clinique a Marrakech",
     lambda a: (a["rag_status"] == "out_of_scope_region", f"status={a['rag_status']}")),
    ("oos-12 clinique bouskoura",
     "ou ouvrir une clinique a Bouskoura",
     lambda a: (a["rag_status"] == "out_of_scope_region" and a["top_zone"] == "Bouskoura",
                f"status={a['rag_status']} top_zone={a['top_zone']}")),
    ("oos-13 open youtube command",
     "ouvrir youtube.com",
     lambda a: (a["rag_status"] == "out_of_scope_command" and a["top_zone"] != "Anfa",
                f"status={a['rag_status']} top_zone={a['top_zone']}")),
    ("oos-14 bare external domain",
     "youtube.com",
     lambda a: (a["rag_status"] == "out_of_scope_question" and a["top_zone"] != "Anfa",
                f"status={a['rag_status']} top_zone={a['top_zone']}")),
    ("oos-15 abusive message",
     "fuck you",
     lambda a: (a["rag_status"] == "out_of_scope_message" and a["top_zone"] != "Anfa",
                f"status={a['rag_status']} top_zone={a['top_zone']}")),

    # --- Local aliases / sub-neighbourhoods ---
    ("alias-16 pharmacie sidi maarouf",
     "supply gap pharmacie sidi maarouf",
     lambda a: (a["top_zone"] == "Ain Chock" and a["category"] == "Pharmacy",
                f"top_zone={a['top_zone']} cat={a['category']}")),

    # --- Existing behaviour still passes ---
    ("keep-17 bonjour",
     "bonjour",
     lambda a: (a["rag_status"] == "easy_greeting", f"status={a['rag_status']}")),
    ("keep-18 pharmacie faible concurrence",
     "ou ouvrir une pharmacie a faible concurrence",
     lambda a: (a["category"] == "Pharmacy" and a["top_zone"] not in ("", "Casablanca"),
                f"cat={a['category']} top_zone={a['top_zone']}")),
    ("keep-19 rapport pharmacie",
     "rapport pharmacie",
     lambda a: (a.get("suggested_view") == "reports", f"view={a.get('suggested_view')}")),
    ("keep-20 carte pharmacie",
     "carte pharmacie",
     lambda a: (a.get("suggested_view") == "map", f"view={a.get('suggested_view')}")),

    # --- Multi-sector expansion ---
    ("sector-21 restaurant opportunity",
     "ou ouvrir un restaurant a Casablanca",
     lambda a: (a["rag_status"] == "sector_opportunity"
                and a["category"] == "food"
                and a["top_zone"] not in ("", "Casablanca"),
                f"status={a['rag_status']} cat={a['category']} top_zone={a['top_zone']}")),
    ("sector-22 cafes maarif",
     "combien de cafes a Maarif",
     lambda a: (a["rag_status"] == "sector_zone_analysis"
                and a["category"] == "food"
                and a["top_zone"] == "Maarif"
                and contains(a, "POIs"),
                f"status={a['rag_status']} cat={a['category']} top_zone={a['top_zone']}")),
    ("sector-23 education opportunity",
     "ou ouvrir une ecole a Casablanca",
     lambda a: (a["rag_status"] == "sector_opportunity"
                and a["category"] == "education",
                f"status={a['rag_status']} cat={a['category']} top_zone={a['top_zone']}")),
    ("sector-24 roches noires now scored",
     "supply gap restaurant Roches Noires",
     lambda a: (a["rag_status"] in {"sector_zone_analysis", "coverage_gap_arrondissement"}
                and "Roches" in a["top_zone"]
                and (a["rag_status"] == "coverage_gap_arrondissement" or a["category"] == "food"),
                f"status={a['rag_status']} cat={a.get('category')} top_zone={a['top_zone']}")),
    ("gap-25 missing arrondissements",
     "quels arrondissements officiels ne sont pas scores",
     lambda a: (a["rag_status"] == "coverage_gaps"
                and (contains(a, "Mers Sultan") or contains(a, "aucun gap")),
                f"status={a['rag_status']} top_zone={a['top_zone']}")),
]


def main() -> int:
    print(f"Target: {ENDPOINT}\n")
    passed = 0
    failed = 0
    for label, question, assertion in CASES:
        try:
            answer = ask(question)
            ok, detail = assertion(answer)
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"EXC {exc}"
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"[{status}] {label:38} | {detail}")
    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
