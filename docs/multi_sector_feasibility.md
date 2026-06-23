# Multi-Sector Feasibility Study — Beyond the Medical Market

**Question:** can Invest Search expand beyond the Casablanca medical market
(to retail, education, food & beverage, wellness, …) **without losing the
accuracy** it has today?

**Short answer:** Yes — but only as a **sector-pack architecture** with
per-sector data and per-sector calibration. A single "any business" model
sharing one set of weights would *lose* accuracy. The good news: ~70% of the
platform is already sector-agnostic; the medical-specific parts are localized
and can be abstracted cleanly.

---

## 1. What already generalizes (sector-agnostic core)

These components make **no real assumption about "medical"** and would be reused
as-is:

| Component | File | Why it generalizes |
|---|---|---|
| Territorial grid (districts, population, density, area) | `area_indicators.csv` | Demographics are sector-independent |
| Scoring *skeleton* | `app/utils/scoring.py` | Demand / SupplyGap / Competition / Accessibility / PurchasingPower / DataConfidence apply to **any** location-based business |
| Distance / competition radius engine | `compute_competition_radius`, `haversine_km` | Pure geometry |
| Deduplication, geocoding, enrichment | `data_sources/*` | Tag-agnostic |
| RAG retrieval (semantic + BM25 + RRF) | `api/services/rag.py` | Indexes *files*, not medical concepts |
| Map, zones, UI shell | `frontend/`, `app/` | Generic |

The opportunity model `0.30·Demand + 0.25·SupplyGap + 0.15·PurchasingPower +
0.10·Accessibility + 0.10·LowCompetition + 0.10·DataConfidence` is, conceptually,
a **generic retail-location model**. Nothing in its structure is medical.

---

## 2. What is medical-specific (must be abstracted)

| Hard-coded to medical | Location | Impact of expansion |
|---|---|---|
| `INVESTMENT_CATEGORIES` → `data_category` maps to OSM **medical** tags (pharmacy, clinic, dentist…) | `scoring.py:17` | Need a tag set per sector |
| Overpass collection queries only **medical amenities** | `data_sources/osm_overpass.py`, `scripts/01_collect_osm.py` | Need sector-parameterised queries |
| `specialty_supply.csv` + `undersupply_index` built from medical facilities | pipeline `03`/`05` | Recompute per sector |
| Category weights **curated for medical** behaviour | `scoring.py` weights | **Must be recalibrated per sector** (accuracy risk) |
| Former guardrails accepted only the health vertical | `api/services/llm/prompts.py`, `invest_data.py` scope logic | Now needs continuous sector-aware tests |
| Former French copy centered only on health | prompts, templates | Keep health as the core vertical while naming supported sectors |

The two items in **bold** are where accuracy is won or lost.

---

## 3. The accuracy risk — and how to contain it

Naively reusing the medical weights for, say, restaurants would degrade accuracy
because the **drivers differ by sector**:

| Driver | Medical | Retail / F&B | Education |
|---|---|---|---|
| Population density (Demand) | High | High | Medium |
| Footfall / high-street | Medium | **Critical** | Low |
| Purchasing power | High (private care) | High | **Critical** (private schools) |
| Catchment radius | 0.5–5 km by specialty | 0.2–1 km | 2–5 km |
| Supply/undersupply | Strong | Moderate (saturation matters more) | Strong |
| Regulatory spacing | Pharmacies | Licensing varies | Accreditation |

**Containment strategy (keeps accuracy):**

1. **No shared weights.** Each sector ships its own weight vector + competition
   radius + saturation thresholds, exactly like the current per-category config —
   just extended one level up to "sector".
2. **Per-sector data confidence.** OSM coverage differs (restaurants: excellent;
   private schools: fair; informal retail: poor). Carry a sector-specific
   `data_confidence` so the score honestly reflects weaker data.
3. **Per-sector evaluation gate.** Each new sector gets its own labeled retrieval
   set (`scripts/evaluate_retrieval.py`) and answer set
   (`scripts/evaluate_rag_answers.py`). **A sector only launches if it meets the
   medical baseline metrics** — this is the explicit "don't lose accuracy" gate.
4. **Calibration before launch.** Tune weights against a few known good/bad real
   locations per sector (ground truth) instead of guessing.

---

## 4. Proposed architecture: sector packs

Introduce a `Sector` abstraction above the existing category config:

```
sectors/
  medical.py      # existing INVESTMENT_CATEGORIES, OSM medical tags, prompts
  retail.py       # OSM shop=* tags, retail weights, retail prompts
  education.py    # OSM amenity=school/university, education weights
  food.py         # OSM amenity=restaurant/cafe/fast_food
```

Each pack declares:

```python
Sector(
    key="retail",
    label_fr="commerce de détail",
    osm_tags={"shop": ["*"]},           # drives the Overpass query
    categories={...},                   # like INVESTMENT_CATEGORIES, calibrated
    scope_keywords={...},               # drives the chat guardrail
    confidence_band=(0.55, 0.80),       # OSM reliability for this sector
)
```

Changes required:

- **Pipeline:** parameterise scripts `01`–`06` by `--sector` (tag set in, sector
  suffix on outputs: `area_indicators_retail.csv`, etc.).
- **Scoring:** `compute_opportunity_scores(areas, spec, category, sector)` — same
  math, sector-selected weights.
- **Guardrails:** keep the sector-aware scope check aligned with
  `active_sectors`; the bot accepts a question if it matches *any* enabled
  sector. This is the riskiest refactor (the current guardrails are deeply
  medical) and needs its own test set.
- **RAG:** one index per sector (or sector-tagged chunks) so retrieval doesn't
  mix restaurant and clinic context.
- **UI:** a sector switcher; everything downstream keys off the active sector.

---

## 5. Feasibility by candidate sector

| Sector | OSM data quality | Reuses model well | Extra data needed | Verdict |
|---|---|---|---|---|
| **Pharmacy-adjacent / wellness** (opticians, parapharmacy, beauty) | Good | High (already near medical) | Minor | **Easiest pilot** |
| **Food & Beverage** (restaurants, cafés) | Excellent | High, but footfall-driven | Footfall, rents | **Strong pilot** |
| **Retail / commerce** | Good (`shop=*`) | Medium (very footfall/rent dependent) | Footfall, rents, income | Feasible after enrichment |
| **Education** (private schools, crèches) | Fair | Medium | Income, age structure | Feasible, data-limited |
| **Fitness / gyms** | Fair | High | Income, footfall | Feasible |

The **footfall + rents + purchasing-power** enrichments recommended in
`data_enrichment_study.md` are *prerequisites* for the non-medical sectors —
expansion and enrichment are the same roadmap.

---

## 6. Phased plan

- **Phase 0 — Refactor in place (no new sector).** Extract the medical vertical
  into a `Sector` pack without changing behaviour. Prove the abstraction by
  re-running existing evals and getting identical results. *Low risk, high value.*
- **Phase 1 — One pilot sector (F&B or wellness).** Sector-parameterise the OSM
  pipeline; calibrate weights; build a sector eval set; launch **only if** it
  meets the medical baseline (Hit@5, composite accuracy).
- **Phase 2 — Sector-aware guardrails + UI switcher.** Generalise scope logic;
  add the sector selector; per-sector RAG index.
- **Phase 3 — Scale to remaining sectors** once enrichment (rents, footfall,
  income) lands, each behind its own eval gate.

---

## 7. Recommendation

**Feasible and worth doing — as sector packs, not a generic model.** Concretely:

- Do **Phase 0** now (pure refactor, fully testable, zero accuracy risk) — it
  also makes the medical code cleaner.
- Pick **one pilot sector** with good OSM data (F&B or wellness) and treat the
  per-sector **evaluation gate** as the non-negotiable accuracy guarantee.
- Sequence expansion *behind* the data enrichment roadmap: footfall, rents and
  purchasing power are shared prerequisites, so the two initiatives reinforce
  each other.

Accuracy is preserved not by hoping the medical model transfers, but by
**per-sector calibration + per-sector eval gates** — the same discipline already
applied to the model and retrieval comparisons in this repo.
