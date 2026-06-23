# Data Enrichment Study — Invest Search

**Goal:** identify the data points that would make the Invest Search database
*richer and more accurate*, ranked by impact on the scoring model and the RAG,
with sources, integration effort, and the concrete schema changes each implies.

This study is grounded in the current pipeline:

- **Scoring** (`app/utils/scoring.py`): `InvestmentReadiness = 0.30·Demand +
  0.25·SupplyGap + 0.15·PurchasingPower + 0.10·Accessibility +
  0.10·LowCompetition + 0.10·DataConfidence`.
- **Indicators** (`data/processed/area_indicators.csv`) and **facilities**
  (`data/processed/medical_facilities_clean.csv`).
- **RAG** retrieval over project files (`api/services/rag.py`).

---

## 1. The accuracy gap today

Three scoring inputs are **placeholders or weak proxies** — they currently add
weight without adding signal:

| Index | Weight | Current state in code | Problem |
|---|---|---|---|
| `purchasing_power` | 0.15 | `purchasing_power_proxy` if present, else **hardcoded 50.0** | 15% of the score is flat for every zone unless the proxy column exists |
| `GrowthIndex` | 0.10 (methodology) | **Placeholder 50 for MVP** | No urban-growth signal at all |
| `data_uncertainty` (risk) | 0.25 of risk | **Constant 35.0** for every zone | Risk doesn't reflect *actual* per-zone data reliability |

On top of that, the methodology's own *Limitations* section flags **OSM
incompleteness, rents, footfall, parking, and regulatory constraints** as not
yet quantified. Every item below closes one of these gaps.

---

## 2. High-value data points (prioritised)

Priority = (impact on score/accuracy) × (feasibility) ÷ (effort). **P1 = do
first.**

### P1 — Ministry of Health facility registry (cross-validation of OSM)
- **Feeds:** `DataConfidence`, `SupplyGap`, `LowCompetition`, and the `risk`
  data-uncertainty term (today a constant 35).
- **Why:** OSM under-counts facilities; zones showing 0 may be data gaps, not
  real deserts (the app already warns about this for Maarif/Mediouna). A second
  authoritative source lets us (a) fill missing facilities and (b) compute a
  *real* per-zone confidence from source agreement instead of a constant.
- **Source:** Carte Sanitaire / *Santé en chiffres* (Ministère de la Santé),
  delegation-level establishment lists. Partly manual today
  (`data/manual/official_baseline.csv`).
- **Effort:** Medium (mostly manual curation + a matcher against OSM by
  name+geo, reusing `data_sources/deduplication.py`).
- **Schema:** new `source='ministry'` rows in facilities; new
  `source_agreement_score` per facility → aggregate to a real
  `data_confidence` per zone.

### P1 — Purchasing power / income proxy (replace the flat 50)
- **Feeds:** `PurchasingPower` (15% of the readiness score, currently flat).
- **Why:** This is the single biggest "dead weight" in the model. A real proxy
  immediately differentiates affluent vs. low-income districts — decisive for
  dermatology, radiology, private clinics (which weight purchasing power 0.20–0.25).
- **Source:** Casa-Stat / E-Data CRI Casablanca-Settat, HCP socio-economic
  indicators; or a proxy from rent levels + car ownership + amenity mix.
- **Effort:** Low–Medium (one numeric column per district).
- **Schema:** populate the already-supported `purchasing_power_proxy` column in
  `area_indicators.csv` — the code path exists (`scoring.py:149`), it just needs
  data.

### P1 — Commercial rents (€/m²) per district
- **Feeds:** a new **cost/feasibility** dimension and the investor report.
- **Why:** a high-opportunity zone with unaffordable rent is a bad investment;
  rent is the #1 missing decision variable in the enriched answer's "données à
  compléter" list.
- **Source:** Mubawab / Avito listings (scrape average asking €/m² for commercial
  units by district), or CRI commercial-lease references.
- **Effort:** Medium (scraper + monthly refresh; values are noisy → store median
  + sample size).
- **Schema:** `area_indicators.csv`: `rent_commercial_med`, `rent_sample_n`.

### P2 — Footfall / pedestrian flow proxy
- **Feeds:** `Demand` (today only population density).
- **Why:** pharmacies and dental/GP cabinets depend on passing traffic, not just
  residential density. Distinguishes a dense-but-residential block from a
  commercial high street.
- **Source:** OSM POI density (retail, transit stops, schools) as a proxy;
  optionally Google Places `popularity`/`user_ratings_total` (already a stub in
  `data_sources/google_places_optional.py`).
- **Effort:** Medium (computed from data we can already pull).
- **Schema:** `area_indicators.csv`: `footfall_proxy`, plus a `demand` blend that
  mixes density and footfall.

### P2 — Public-transport & road accessibility
- **Feeds:** `Accessibility` (today only `nearest_hospital_km`).
- **Why:** accessibility for a *patient* is about reaching the clinic (tram/bus
  stops, main roads, parking), not distance to the nearest hospital.
- **Source:** OSM `public_transport`, `highway`, `amenity=parking`; Casa Tramway
  GTFS if available.
- **Effort:** Medium (geo-joins on existing OSM extracts).
- **Schema:** `area_indicators.csv`: `transit_stops_count`, `parking_count`,
  `main_road_access_index`.

### P2 — Regulatory / licensing constraints per category
- **Feeds:** `risk` and a hard feasibility flag.
- **Why:** pharmacies in Morocco have **numerus clausus / geographic spacing
  rules**; a zone can be statistically attractive yet legally closed to a new
  pharmacy. This is a correctness issue, not just enrichment.
- **Source:** Ministry of Health pharmacy regulations, Conseil de l'Ordre.
- **Effort:** Low (a small rules table) but high research value.
- **Schema:** new `data/manual/regulatory_constraints.csv`
  (`category, rule_type, min_spacing_m, notes`).

### P3 — Demographic structure (age bands)
- **Feeds:** category-specific `Demand` (pediatrics → children share, etc.).
- **Source:** HCP census age pyramids by district.
- **Effort:** Medium. **Schema:** `area_indicators.csv`: `pct_under_15`,
  `pct_over_60`.

### P3 — Temporal / freshness metadata
- **Feeds:** `DataConfidence`, RAG trustworthiness.
- **Why:** a facility last confirmed in 2019 is weaker evidence than one
  confirmed this year. Enables time-decay on confidence.
- **Source:** OSM `last_edit` timestamp; collection date per row.
- **Effort:** Low. **Schema:** facilities: `last_verified_date`.

---

## 3. Impact on the RAG specifically

Richer **structured** data only helps the chatbot if it reaches retrieval. Two
companion changes:

1. **Per-zone fact sheets.** Generate one markdown card per district
   (population, density, rents, purchasing power, per-category supply,
   undersupply, risks) into `data/processed/zone_profiles/*.md`. These are
   far more retrievable than raw CSV row-dumps (which the retrieval eval showed
   are low-signal and were crowding the index). This directly lifts Recall@k.
2. **Re-index discipline.** Every enrichment must end with a RAG re-index
   (`POST /api/admin/refresh` → `build_index(force=True)`), otherwise new data is
   invisible to chat. Add `last_verified_date` into the chunk text so freshness
   is searchable.

---

## 4. Quick wins vs. heavy lifts

| Effort | Item | Score impact |
|---|---|---|
| **Low** | purchasing_power_proxy column | Unblocks 15% of the score |
| **Low** | regulatory constraints table | Prevents recommending illegal sites |
| **Low** | freshness metadata | Real (not constant) data confidence |
| **Medium** | Ministry registry cross-validation | Biggest accuracy + trust gain |
| **Medium** | commercial rents | Adds the missing cost axis |
| **Medium** | footfall + transit | Sharper demand/accessibility |

---

## 5. Recommended sequence

1. **Populate `purchasing_power_proxy`** (data already wired into scoring) — fast,
   removes the largest dead weight.
2. **Ministry registry cross-validation** → real `data_confidence` and
   `risk` uncertainty; fixes the "0 facilities = data gap?" ambiguity.
3. **Commercial rents** → adds the cost dimension to the investor report.
4. **Footfall + transit** → upgrade `Demand`/`Accessibility` from single-proxy.
5. **Generate per-zone fact sheets + re-index** so every new field is RAG-visible.
6. **Regulatory table** in parallel (cheap, high correctness value).

> Each step is independently shippable and measurable: re-run
> `scripts/evaluate_retrieval.py` (retrieval) and `scripts/evaluate_rag_answers.py`
> (answers) before/after to confirm the enrichment helped rather than just
> enlarged the index.
