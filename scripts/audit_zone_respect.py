"""Audit: do the deterministic ("quick") answers respect an explicitly named zone?

For each intent, the question names a zone. The answer should anchor on THAT zone
(top_zone == requested), not silently fall back to the global best (the budget
bug). Comparison must include both zones.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.services.conversation import run_turn  # noqa: E402

# (question, expected_zone_must_appear_as_top, also_must_mention)
CASES = [
    ("Ou ouvrir un cafe a Maarif ?", "Maarif", []),
    ("Ou ouvrir une pharmacie a Maarif ?", "Maarif", []),
    ("Supply gap dentaire a Sidi Moumen", "Sidi Moumen", []),
    ("Risque a Sidi Moumen", "Sidi Moumen", []),
    ("Combien de cafes a Maarif ?", "Maarif", []),
    ("Quelle est la population de Maarif ?", "Maarif", []),
    ("J ai 800 000 DH pour un commerce a Maarif", "Maarif", ["Hay Hassani"]),
    ("J ai 1 200 000 DH pour une pharmacie a Anfa", "Anfa", []),
    ("Que puis-je ouvrir avec 800000 dh a Maarif ?", None, ["Maarif"]),
    ("Comparer Anfa et Maarif pour une clinique", None, ["Anfa", "Maarif"]),
]


def main() -> None:
    print(f"{'OK':4} {'status':22} {'top_zone':16} question")
    print("-" * 80)
    issues = 0
    for question, expect_top, must_mention in CASES:
        r = run_turn(message=question, debug=False)
        top = r.get("top_zone", "")
        md = r.get("answer_markdown", "")
        ok = True
        reasons = []
        if expect_top is not None and top != expect_top:
            ok = False
            reasons.append(f"top_zone={top!r} != {expect_top!r}")
        for m in must_mention:
            if m.lower() not in md.lower():
                ok = False
                reasons.append(f"missing mention: {m}")
        if not ok:
            issues += 1
        flag = "PASS" if ok else "FAIL"
        print(f"{flag:4} {r.get('rag_status',''):22} {top:16} {question[:44]}")
        if not ok:
            print(f"     -> {'; '.join(reasons)}")
    print("-" * 80)
    print(f"{len(CASES) - issues}/{len(CASES)} respect the named zone")


if __name__ == "__main__":
    main()
