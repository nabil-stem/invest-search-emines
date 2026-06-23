# Data Dictionary — Invest Search

## medical_facilities_clean.csv

| Champ | Type | Description |
|---|---|---|
| id | string | Identifiant unique (ex: osm_node_123456) |
| name | string | Nom nettoyé de l'établissement |
| original_name | string | Nom brut d'origine |
| name_fr | string | Nom en français (si disponible) |
| name_ar | string | Nom en arabe (si disponible) |
| category | enum | hospital, clinic, pharmacy, doctor, dentist, laboratory, radiology, health_center, veterinary, unknown |
| sub_category | string | Spécialité médicale (si disponible) |
| sector | enum | public, private, unknown |
| district | string | Arrondissement / quartier de Casablanca |
| address | string | Adresse |
| lat | float | Latitude |
| lon | float | Longitude |
| phone | string | Numéro de téléphone |
| website | string | Site web |
| opening_hours | string | Horaires d'ouverture |
| operator | string | Opérateur / gestionnaire |
| beds | int/null | Nombre de lits (hôpitaux/cliniques) |
| source | string | Source de la donnée (OSM, Ministry, manual, API) |
| source_url | string | URL de la source |
| confidence_score | float | Score de confiance 0.0–1.0 |

## area_indicators.csv

| Champ | Type | Description |
|---|---|---|
| area_id | string | Identifiant de la zone |
| area_name | string | Nom de l'arrondissement |
| prefecture | string | Préfecture |
| population_est | int | Population estimée |
| area_km2 | float | Superficie en km² |
| population_density | float | Habitants par km² |
| medical_facilities_count | int | Total d'établissements médicaux |
| facilities_per_100k | float | Établissements pour 100 000 habitants |
| pharmacy_count | int | Nombre de pharmacies |
| clinic_count | int | Nombre de cliniques |
| hospital_count | int | Nombre d'hôpitaux |
| doctor_count | int | Nombre de cabinets de médecins |
| dentist_count | int | Nombre de dentistes |
| laboratory_count | int | Nombre de laboratoires |
| radiology_count | int | Nombre de centres de radiologie |
| health_center_count | int | Nombre de centres de santé |
| nearest_hospital_km | float | Distance au plus proche hôpital (km) |
| undersupply_index | float | Indice de sous-équipement (0–100) |
| demand_index | float | Indice de demande (0–100) |
| accessibility_index | float | Indice d'accessibilité (0–100) |
| low_competition_index | float | Indice de faible concurrence (0–100) |
| investment_score | float | Score d'investissement composite (0–100) |

## specialty_supply.csv

| Champ | Type | Description |
|---|---|---|
| area_name | string | Nom de l'arrondissement |
| specialty | string | Catégorie médicale |
| providers_count | int | Nombre de prestataires |
| providers_per_100k | float | Prestataires pour 100 000 habitants |
| competition_level | enum | low, medium, high |
| opportunity_level | enum | low, medium, high |
| notes | string | Notes complémentaires |
