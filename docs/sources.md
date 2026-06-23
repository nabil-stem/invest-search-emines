# Sources de données — Invest Search

## Sources actives (MVP)

| Source | Type | URL | Données |
|---|---|---|---|
| OpenStreetMap / Overpass API | POI géographiques | https://overpass-api.de/api/interpreter | Hôpitaux, cliniques, pharmacies, médecins, dentistes, laboratoires |
| MSPS — soins de santé primaires 2024 | Officiel | https://data.gov.ma/data/fr/dataset/2932e8a4-272c-4101-80ef-85519de47e7c | Liste détaillée, agrégée par arrondissement dans le projet |
| MSPS — hôpitaux 2024 | Officiel | https://data.gov.ma/data/fr/dataset/0977885b-7596-4499-9880-bf9f375e3c72 | Liste nominative des hôpitaux publics |
| Casa-Stat / E-Data CRI | Institutionnel | https://edata.casainvest.ma/ | Données socio-économiques |
| HCP RGPH 2024 — Excel | Officiel | https://www.hcp.ma/file/242341/ | Population et ménages exacts des 16 arrondissements |
| HCP Casablanca-Settat | Officiel | https://www.hcp.ma/reg-casablanca/ | Publications régionales, population, projections |

## Sources prévues (Phase 2+)

| Source | Type | Usage prévu |
|---|---|---|
| ANAM | Officiel | Prestataires conventionnés AMO |
| CNSS | Officiel | Conventionnement, remboursement |
| Google Places API | API commerciale | Enrichissement avis, horaires |
| Annuaires médicaux | Annuaire | Spécialités, téléphones |
| Presse économique | Veille | Ouvertures, investissements, tendances |

## Plan d'intégration avant présentation

| Priorité | Source | Statut cible |
|---:|---|---|
| P0 | OpenStreetMap + frontières OSM | Déjà utilisé, rafraîchi via admin |
| P0 | HCP RGPH 2024 | Intégré et versionné par arrondissement |
| P0 | MSPS 2024 | Intégré: offre publique agrégée par arrondissement |
| P1 | Data Quality Center | Confiance et trous par catégorie intégrés; validation privée à poursuivre |
| P2 | Google Places API | Enrichissement optionnel si clé disponible |
| P2 | Loyer / flux / transport | Données à qualifier ou proxies à expliciter |

## Barème de confiance

| Score | Critère |
|---:|---|
| 1.00 | Source officielle récente, donnée structurée |
| 0.85 | Source institutionnelle fiable |
| 0.70 | OSM avec nom + coordonnées + tags cohérents |
| 0.60 | Annuaire public vérifiable |
| 0.50 | Article de presse économique fiable |
| 0.30 | Donnée non vérifiée / manuelle |
