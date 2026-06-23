"""Multi-turn conversation tests (scenarios from the spec).

Simulates the stateless-server contract: the client passes the prior
investor_profile back on each turn. Runs in-process (no server needed).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.services.conversation import run_turn  # noqa: E402


def turn(profile, message):
    r = run_turn(message=message, profile_dict=profile, debug=True)
    p = r["investor_profile"]
    print(f"  USER: {message}")
    print(f"    status={r['rag_status']}  zone={r.get('top_zone')}")
    print(f"    profile: budget={p['budget']} sector={p['sector']} type={p['business_type']} "
          f"zone={p['zone']} compare={p['comparison_zones']} obj={p['objective']}")
    sq = r.get("standalone_query")
    if sq:
        print(f"    standalone: {sq[:140]}")
    return p, r


def main():
    print("Scenario 1 — budget+sector then zone")
    p, _ = turn(None, "J'ai 800 000 DH et je veux ouvrir une pharmacie.")
    assert p["budget"] == 800000 and p["business_type"] == "Pharmacy", p
    p, r = turn(p, "Sidi Moumen.")
    assert p["zone"] == "Sidi Moumen", p
    assert r["rag_status"] != "needs_clarification", "should analyse, not re-ask"

    print("\nScenario 2 — compare with Maarif (keep budget+sector)")
    p, r = turn(p, "Compare avec Maarif.")
    assert "Maarif" in p["comparison_zones"] and p["business_type"] == "Pharmacy", p
    assert p["budget"] == 800000, p

    print("\nScenario 3 — change only the budget")
    p, r = turn(p, "Et si mon budget est seulement 400 000 DH ?")
    assert p["budget"] == 400000 and p["business_type"] == "Pharmacy", p
    assert p["zone"] == "Sidi Moumen", p

    print("\nScenario 4 — switch sector to restaurant (keep budget+zone)")
    p, r = turn(p, "Et pour un restaurant ?")
    assert p["sector"] == "food", p
    assert p["budget"] == 400000, "budget should persist"

    print("\nScenario 5 — new conversation resets")
    p, r = turn(p, "Nouvelle discussion")
    assert not any([p["budget"], p["sector"], p["business_type"], p["zone"]]), p

    print("\nALL CONVERSATION SCENARIOS PASSED")


if __name__ == "__main__":
    main()
