"""Broad scenario battery for the live Invest Search chat API.

Goes beyond the canned guardrail set: exercises every non-medical sector,
adversarial out-of-scope prompts, budget-style consulting prompts, and quality
heuristics on the returned markdown. Prints a conformance + quality report.

Run (server must be up):  python scripts/test_scenarios.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests

API = "http://127.0.0.1:8000/api/chat"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "scenario_results.json"

# category: (question, expectation)
#   expectation kinds:
#     in_scope_sector=<key>  -> expect a sector answer (not refused, sector matches)
#     in_scope_medical       -> expect a medical analysis (not refused)
#     refuse                 -> expect an out-of-scope / clarification / gap status
SCENARIOS = [
    # --- non-medical sectors that ARE supported ---
    ("food", "Ou ouvrir un restaurant a Casablanca ?", "in_scope_sector:food"),
    ("food", "Combien de cafes a Maarif ?", "in_scope_sector:food"),
    ("retail", "Ou ouvrir un supermarche a Casablanca ?", "in_scope_sector:retail"),
    ("retail", "Quelle zone pour une boutique de vetements ?", "in_scope_sector:retail"),
    ("education", "Ou ouvrir une ecole privee a Casablanca ?", "in_scope_sector:education"),
    ("education", "Quelle zone pour une creche ?", "in_scope_sector:education"),
    ("wellness", "Ou ouvrir une salle de sport a Casablanca ?", "in_scope_sector:wellness"),
    ("wellness", "Meilleure zone pour un salon de coiffure ?", "in_scope_sector:wellness"),
    # --- subcategory routing, plurals and exact zone counts ---
    ("subcategory", "Ou ouvrir une boulangerie a Casablanca ?", "in_scope_sector:retail:bakery"),
    ("subcategory", "Ou ouvrir un magasin opticien ?", "in_scope_sector:wellness:optician"),
    ("subcategory", "Ou ouvrir des supermarches a Casablanca ?", "in_scope_sector:retail:supermarket"),
    ("subcategory", "Ou ouvrir des salles de sport a Casablanca ?", "in_scope_sector:wellness:fitness"),
    ("count", "Combien de cafes a Maarif ?", "count:food:cafe:Maarif:103"),
    ("count", "Combien de restaurants a Maarif ?", "count:food:restaurant:Maarif:68"),
    ("count", "Combien de supermarches a Ain Chock ?", "count:retail:supermarket:Ain Chock:13"),
    ("count", "Combien de salles de sport a Anfa ?", "count:wellness:fitness:Anfa:13"),
    # --- medical still works ---
    ("medical", "Ou ouvrir une pharmacie a faible concurrence ?", "in_scope_medical"),
    ("medical", "Comparer Anfa et Maarif pour une clinique", "in_scope_medical"),
    # --- truly out of scope: must refuse ---
    ("oos", "Qui va gagner la coupe du monde 2026 ?", "refuse"),
    ("oos", "Ecris moi un poeme sur l'amour", "refuse"),
    ("oos", "Quel temps fait-il aujourd'hui ?", "refuse"),
    ("oos", "Donne moi une recette de couscous", "refuse"),
    ("oos", "Comment coder un site web en react ?", "refuse"),
    ("oos", "Raconte une blague", "refuse"),
    ("oos", "Quelle est la capitale du Japon ?", "refuse"),
    ("oos", "Ouvre instagram.com", "refuse"),
    # --- coverage gaps / missing arrondissements ---
    ("gap", "Ou ouvrir une pharmacie a Roches Noires ?", "any"),
    ("gap", "Quels arrondissements officiels ne sont pas encore couverts ?", "any"),
    # --- budget-aware consulting prompts ---
    ("budget", "J'ai un budget de 500000 dh, ou ouvrir une pharmacie ?", "budget"),
    ("budget", "Avec 1 million de dirhams quel investissement medical me conseilles-tu ?", "budget"),
    ("budget", "Je veux investir 200000 dh dans un cafe, ou ?", "budget"),
    ("budget", "budget 2 millions de dirhams pour une pharmacie", "budget"),
]

REFUSE_STATUSES = {
    "out_of_scope_question", "out_of_scope_command", "out_of_scope_message",
    "out_of_scope_region", "needs_clarification", "coverage_gaps",
}


def _quality(md: str) -> dict:
    low = md.lower()
    return {
        "len": len(md),
        "has_reco": any(k in low for k in ["recommand", "zone prioritaire", "opportunit"]),
        "has_kpi": "|" in md and any(k in low for k in ["score", "population", "poi", "supply"]),
        "has_limits": any(k in low for k in ["limite", "risque", "valider", "indicative", "terrain"]),
        "has_sources": "source" in low,
    }


def run_one(question: str, expectation: str) -> dict:
    t0 = time.time()
    try:
        r = requests.post(API, json={"message": question, "locale": "fr"}, timeout=60)
        r.raise_for_status()
        d = r.json()
    except Exception as exc:  # noqa: BLE001
        return {"question": question, "error": str(exc), "elapsed": round(time.time() - t0, 2)}

    status = d.get("rag_status", "")
    category = d.get("category", "")
    subcategory = d.get("subcategory")
    md = d.get("answer_markdown", "")
    contexts = d.get("retrieved_contexts") or []
    related = d.get("related_opportunities") or []
    refused = status in REFUSE_STATUSES or "hors perimetre" in md.lower() or "hors périmètre" in md.lower()

    ok = True
    reason = ""
    if expectation.startswith("in_scope_sector:"):
        parts = expectation.split(":")
        want = parts[1]
        want_subcategory = parts[2] if len(parts) > 2 else None
        has_profile_context = any("zone_profiles" in str(ctx.get("source_path", "")) for ctx in contexts)
        has_real_competition = any(
            str(item.get("competition_level", "")).lower() not in {"", "exploratory"}
            for item in related
        )
        no_exploratory_copy = "exploratoire" not in md.lower() and "exploratory" not in md.lower()
        ok = (
            (not refused)
            and (category == want)
            and (want_subcategory is None or subcategory == want_subcategory)
            and has_profile_context
            and has_real_competition
            and no_exploratory_copy
        )
        reason = (
            f"want sector={want}, got category={category} status={status}; "
            f"want_subcategory={want_subcategory} got_subcategory={subcategory}; "
            f"profile_context={has_profile_context} real_competition={has_real_competition} "
            f"no_exploratory_copy={no_exploratory_copy}"
        )
    elif expectation.startswith("count:"):
        _, want_sector, want_subcategory, want_zone, want_count = expectation.split(":")
        selected = next((item for item in related if item.get("zone") == want_zone), {})
        ok = (
            category == want_sector
            and subcategory == want_subcategory
            and d.get("top_zone") == want_zone
            and int(selected.get("providers", -1)) == int(want_count)
        )
        reason = (
            f"sector={category} subcategory={subcategory} zone={d.get('top_zone')} "
            f"providers={selected.get('providers')}"
        )
    elif expectation == "in_scope_medical":
        ok = not refused and status.startswith(("hybrid", "zone", "easy_location")) or "recommand" in md.lower()
        reason = f"status={status}"
    elif expectation == "budget":
        ok = status == "budget_advisory"
        reason = f"status={status}"
    elif expectation == "refuse":
        ok = refused
        reason = f"status={status} refused={refused}"
    else:  # any
        ok = bool(md)
        reason = f"status={status}"

    q = _quality(md)
    return {
        "question": question,
        "expectation": expectation,
        "ok": ok,
        "reason": reason,
        "status": status,
        "category": category,
        "subcategory": subcategory,
        "elapsed": round(time.time() - t0, 2),
        "quality": q,
        "preview": md[:160].replace("\n", " "),
    }


def main() -> None:
    print(f"Scenario battery -> {API}\n")
    rows = []
    by_group: dict[str, list[bool]] = {}
    for group, question, expectation in SCENARIOS:
        res = run_one(question, expectation)
        res["group"] = group
        rows.append(res)
        ok = res.get("ok", False)
        by_group.setdefault(group, []).append(ok)
        flag = "PASS" if ok else "FAIL"
        err = res.get("error")
        print(f"[{flag}] {group:8} {question[:50]:50} -> {res.get('status','ERR') if not err else 'ERROR:'+err}")
        if not ok and not err:
            print(f"        reason: {res['reason']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    total_ok = sum(r.get("ok", False) for r in rows)
    print(f"\n=== {total_ok}/{len(rows)} conformant ===")
    print("by group:", {g: f"{sum(v)}/{len(v)}" for g, v in by_group.items()})

    # quality summary for in-scope answers
    inscope = [r for r in rows if r.get("ok") and r.get("group") not in {"oos"} and "quality" in r]
    if inscope:
        def frac(key): return sum(r["quality"][key] for r in inscope) / len(inscope)
        print("\nin-scope answer quality (share with):")
        for key in ("has_reco", "has_kpi", "has_limits", "has_sources"):
            print(f"  {key:12} {frac(key):.0%}")
    print(f"\nFull results -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
