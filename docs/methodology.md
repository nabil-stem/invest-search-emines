# Methodology — Invest Search

## 1. Active data

- **HCP RGPH 2024:** exact legal population and household count for the 16 Casablanca arrondissements.
- **MSPS 2024:** 117 primary-care structures assigned to the 16 arrondissements and 13 public hospitals. One Mechouar centre is outside this perimeter.
- **OpenStreetMap:** geolocated medical facilities and real administrative polygons. OSM is useful but not exhaustive for private providers.
- **Purchasing power:** explicitly marked heuristic (`purchasing_power_confidence=0.35`); it is not presented as an official HCP income measure.

The versioned source tables are `data/manual/hcp_rgph_2024_casablanca.csv` and `data/manual/msps_public_facilities_2024.csv`.

## 2. Territorial model

The scored perimeter is the 16 official arrondissements of Commune de Casablanca. Nouaceur, Mediouna and Dar Bouazza are not mixed into the Casablanca ranking. Ancienne Médina is treated as a locality inside Sidi Belyout, not as a duplicated arrondissement.

Areas and map bounds are calculated from the OSM/Nominatim polygons. Facilities are assigned by point-in-polygon; unmatched records remain `Unknown` and are excluded from arrondissement counts.

## 3. Category scoring

For each investment category, the engine computes:

```text
Opportunity = weighted(
  demand,
  category supply gap,
  damped purchasing-power proxy,
  hospital accessibility,
  same-category competition,
  category data confidence
)
```

- **Demand:** profil propre à chaque activité. Les pharmacies utilisent population, densité, prescripteurs et soins publics; les laboratoires utilisent le bassin de prescripteurs; la radiologie et la physiothérapie utilisent le plateau clinique; le vétérinaire utilise population, surface résidentielle et proxy de pouvoir d'achat; l'urgence tient compte du déficit hospitalier public.
- **Supply gap:** inverse of providers per 100,000 against a category-specific analytical benchmark.
- **Competition:** same-category provider count, never total medical facilities.
- **Purchasing power:** the heuristic is pulled 65% toward neutral because its confidence is only 0.35.
- **Accessibility:** distance to the nearest mapped hospital; it does not claim to measure traffic or transit.
- **Data confidence:** OSM source quality, estimated category completeness and an MSPS validation bonus for hospitals and primary care.

When only 0 to 2 local providers are observed, positive supply-gap and low-competition signals are shrunk toward 50 according to local confidence. With zero local evidence, only 60% of the category confidence is retained. A zero OSM count is therefore treated as missing evidence, not as proven absence.

The benchmarks are analytical comparison thresholds, not legal quotas or national service standards.

## 4. Risk

```text
Risk = 25% competition + 40% data uncertainty
     + 15% low demand + 20% low accessibility
```

Data uncertainty also creates a risk floor. A category with sparse data, such as veterinary or radiology, cannot appear low-risk merely because OSM contains few competitors.

## 5. Limits

- Private provider inventories remain incomplete, especially veterinary, radiology, doctors and laboratories.
- Commercial rents, pedestrian flow, parking occupancy, patient volumes and arrondissement-level purchasing power are unavailable.
- OSM counts and MSPS public counts are displayed separately to avoid silent double counting.
- Scores are decision-screening indicators, not financial, legal or regulatory advice.
