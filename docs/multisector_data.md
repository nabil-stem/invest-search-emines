# Multi-Sector Data Collection — OSM + Web Scraping

This documents the data assets added to take Invest Search beyond the medical
market (Phase 1 of `docs/multi_sector_feasibility.md`).

## 1. Sector packs

`data_sources/sectors.py` defines a `Sector` registry — the abstraction that lets
one OSM pipeline serve any vertical. Each pack declares its OSM tag filters,
sub-categories, and a default confidence (OSM coverage varies by sector).

| sector | key | OSM filter (summary) | default confidence |
|---|---|---|---|
| medical | `medical` | `amenity=hospital/clinic/...`, `healthcare=*` | 0.70 |
| food & beverage | `food` | `amenity=restaurant/cafe/fast_food/bar/...` | 0.72 |
| retail | `retail` | `shop=*` | 0.62 |
| education | `education` | `amenity=school/university/kindergarten/...` | 0.65 |
| wellness & beauty | `wellness` | `shop=hairdresser/beauty/...`, `leisure=fitness_centre`, `amenity=gym/spa` | 0.60 |

## 2. OSM collection (live)

`data_sources/osm_multisector.py` builds a sector-parameterised Overpass query,
fetches the Casablanca bounding box, classifies each POI, and writes
`data/raw/osm_casablanca_<sector>.csv` (+ a JSON cache). Run via:

```
python scripts/collect_multisector_osm.py --sector food
python scripts/collect_multisector_osm.py --all          # every non-medical sector
python scripts/collect_multisector_osm.py --sector retail --refresh   # bypass cache
```

**Collected (live, June 2026):**

| sector | POIs | top categories |
|---|---:|---|
| food | 1 362 | cafe 672, restaurant 455, fast_food 153, bar 64 |
| retail | 1 251 | supermarket 243, clothing 120, bakery 75, sports 69 |
| education | 519 | school 459, university 51, kindergarten 9 |
| wellness | 198 | fitness 74, hairdresser 49, optician 40, beauty 24 |
| **total** | **3 330** | 80% named, 100% geolocated |

Combined output: `data/raw/osm_casablanca_multisector.csv`. The schema matches
the medical raw schema (id, name, lat, lon, category, source, confidence_score, …)
plus a `sector` column, so the existing cleaning / dedup / district-assignment
pipeline (`scripts/03`–`04`, `data_sources/*`) can process it with minimal change.

> Note: `medical` is intentionally excluded from `--all` because it has its own
> established pipeline (`scripts/01` + `osm_overpass.py`) sharing the same raw
> filenames.

## 3. Web scraping (demographic cross-validation)

`data_sources/web_scraper.py` is a **responsible** scraper: descriptive
User-Agent, on-disk HTML cache, polite delay, and an openly-licensed source
(French Wikipedia, CC BY-SA). It extracts the official arrondissement taxonomy
for the Préfecture de Casablanca into
`data/raw/wikipedia_casablanca_districts.csv` (`name`, `name_ascii`,
`prefecture`). Run via:

```
python -m data_sources.web_scraper
```

**Cross-validation findings** (scraped 16 official arrondissements vs. our zone
list): 11/16 matched after accent normalisation. The scrape surfaced:

- **4 official arrondissements missing from our dataset:** Al Fida, Mers Sultan,
  Roches Noires, Sidi Othmane → candidate zones to add.
- Our dataset also covers neighbouring provinces (Dar Bouazza, Mediouna,
  Nouaceur) that are *outside* the Casablanca prefecture proper — useful to label
  as such.
- Accent/spelling differences (Aïn Chock ↔ Ain Chock, Maârif ↔ Maarif) — handled
  by the `name_ascii` join key.

## 4. Processed scoring + RAG fact sheets

`scripts/08_compute_sector_supply.py` turns the raw point collection into two
processed assets:

```powershell
.api310\Scripts\python.exe scripts\08_compute_sector_supply.py
```

- `data/processed/sector_supply.csv` stores one row per sector and zone with
  providers, providers per 100k residents, competition level, supply gap,
  opportunity score, risk score and the scoring weight version.
- `data/processed/subcategory_supply.csv` stores one row per business activity
  and zone (café, restaurant, boulangerie, supermarché, crèche, fitness, etc.).
  Sparse competition rates are shrunk toward the citywide prior and local
  confidence is reduced when too few POIs support the observation.
- `data/processed/zone_profiles/*.md` stores one RAG fact sheet per sector-zone
  pair so chat answers can cite persisted context rather than relying only on
  deterministic templates.

Weights and competition thresholds are defined in `data_sources/sectors.py`.
They vary by vertical: food prioritises purchasing power and mapped saturation,
retail gives more weight to purchasing power, education balances population and
ability-to-pay, and wellness keeps a stronger OSM-confidence penalty.

## 5. API + chat integration status

Implemented in the FastAPI layer:

- `GET /api/sectors` returns sector counts, assigned/unknown POIs, top categories
  and arrondissement coverage gaps.
- `GET /api/sector-opportunities?sector=food` returns the persisted
  `sector_supply.csv` ranking with real competition labels.
- `GET /api/sector-opportunities?sector=food&subcategory=cafe` returns the
  activity-specific ranking from `subcategory_supply.csv`.
- `GET /api/sector-facilities?sector=food` returns mapped POIs for the selected
  sector.
- `subcategory=<key>` filters that map feed to the exact requested activity.
- `/api/chat` now answers deterministic multi-sector questions such as
  *"où ouvrir un restaurant à Casablanca ?"*, *"combien de cafés à Maarif ?"*
  and *"où ouvrir une école à Casablanca ?"* without falling back to medical RAG.
- Official-but-not-yet-scorable arrondissements such as Roches Noires or Mers
  Sultan now return a coverage-gap answer instead of a fabricated score.

## 6. Remaining next steps

1. Collect or verify real boundaries/population for Al Fida, Mers Sultan, Roches
   Noires and Sidi Othmane before adding them to the scoring table.
2. Replace proxy commercial rent multipliers with observed lease samples by
   district.
3. Add a sector scoring evaluation report with human-labelled benchmark
   questions for each vertical.

All collection steps are cached and re-runnable; live Overpass calls are paused
between sectors to respect the public endpoint.
