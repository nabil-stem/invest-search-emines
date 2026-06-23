# Consulting Approach — from "where" to "what should I do"

Invest Search started as a *location* engine ("where is the best zone"). To make
it a real **investment assistant**, it needs to reason about the investor's
**constraints** — first and foremost their **budget** — and give consultative,
scenario-based advice. This documents the approach and how to extend it.

## 1. The budget-aware layer (`api/services/consulting.py`)

When an investor states a budget ("j'ai 500000 dh", "1 million de dirhams",
"200k mad", "budget 1,5M"), the assistant:

1. **Parses the amount** (`parse_budget`) — handles French/English, `k`/`million`
   multipliers, spaces and separators. Guarded so a stray number doesn't bypass
   the out-of-scope rules (requires real investment intent or a known type).
2. **Looks up an indicative cost model** (`CATEGORY_COSTS`, `SECTOR_COSTS`) — a
   turnkey CAPEX range (low / typical / high) + rough monthly OPEX per
   establishment type for Casablanca.
3. **Assesses feasibility** (`assess`): verdict (insufficient / tight /
   comfortable / ample), budget-vs-typical coverage %, and **runway** = months of
   OPEX covered by what's left after a standard setup.
4. **Falls back to alternatives** (`affordable_options`): when the budget doesn't
   fit the requested type, it lists establishment types that *do* fit, cheapest
   first — turning a "no" into actionable options.
5. **Combines with the zone scoring**: `build_budget_advisory_answer` overlays the
   cost analysis on the platform's existing zone recommendation (medical category
   or non-medical sector), so the investor gets *where* **and** *whether they can
   afford it*, with scenarios and next steps.

Output is a `budget_advisory` chat status with: feasibility verdict, a scenarios
table (lean / standard / premium CAPEX), runway, affordable alternatives,
field-validation next steps, and an explicit **indicative-figures disclaimer**
(never a quote or definitive financial advice).

## 2. Why a cost model and not the LLM

Budget feasibility must be **deterministic and consistent** — an LLM inventing
setup costs is exactly the "fabricated numbers" failure mode the model A/B work
flagged. The cost model is a small, auditable table that can be calibrated with
real Moroccan data over time, while the LLM is reserved for narrative framing.

## 3. How to make it more accurate

The cost ranges are indicative. To harden them (in priority order):

1. **Calibrate CAPEX/OPEX** with real quotes (agencement, équipement) and
   licensing/pas-de-porte references per category — the single biggest accuracy
   lever.
2. **Zone-aware rents**: fold the commercial-rent enrichment
   (`docs/data_enrichment_study.md`) into OPEX so runway varies by district, not
   just by type.
3. **Financing scenarios**: add apport/loan splits and a simple break-even /
   payback estimate per zone.
4. **Regulatory feasibility**: pharmacies (numerus clausus / spacing), education
   (accreditation) — a hard "is this even allowed here" gate before the score.

## 4. Beyond budget — other consulting dimensions to add next

The same pattern (parse a constraint → deterministic model → advisory overlay)
extends to:

- **Risk appetite** ("faible risque") → filter/sort by `risk_score`.
- **Timeline / ramp-up** → expected time-to-open per type.
- **Target clientele / positioning** (premium vs popular) → weight purchasing
  power vs density.
- **Multi-site / portfolio** budgets → split across zones.

Each should stay deterministic, cite its assumptions, and end with field
validation — consistent with the platform's "indicative, not a financial
recommendation" stance.
