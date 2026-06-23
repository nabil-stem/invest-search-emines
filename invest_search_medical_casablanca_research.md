# Invest Search — Recherche Data du secteur médical à Casablanca

**Version :** 2026-05-18  
**Objectif :** construire une base de données exploitable pour identifier les opportunités d’investissement dans le secteur médical à Casablanca : zones sous-équipées, densité de médecins/cliniques/pharmacies, concurrence, pouvoir d’achat local, accessibilité, et potentiel par spécialité.

---

## 1. Hypothèse produit

**Invest Search** est une plateforme d’aide à la décision pour investisseurs, fondateurs de cliniques/cabinets, laboratoires, fournisseurs d’équipements médicaux ou pharmacies.

Elle doit répondre à des questions comme :

- Dans quels quartiers de Casablanca manque-t-il des cabinets médicaux, centres de radiologie, laboratoires, pharmacies ou cliniques ?
- Quelles spécialités semblent saturées ou sous-représentées ?
- Où ouvrir un centre médical de proximité ?
- Quels arrondissements combinent forte demande, accessibilité et faible concurrence ?
- Quels segments ont du potentiel : imagerie, dialyse, pédiatrie, gynécologie, dentaire, dermatologie, urgence privée, laboratoires, soins à domicile ?

---

## 2. Sources de données prioritaires

### A. Sources officielles / institutionnelles

| Source | Utilité | Type de données | Priorité |
|---|---|---:|---:|
| Ministère de la Santé — Carte Sanitaire | Offre publique, hôpitaux, ESSB, lits, médecins, équipements lourds | Officiel | Très haute |
| Ministère de la Santé — Santé en chiffres | Médecins par région/province, infrastructures, indicateurs nationaux | Officiel | Très haute |
| Direction Régionale de la Santé Casablanca-Settat | Données régionales, contacts, annonces | Officiel | Haute |
| Casa-Stat / E-Data CRI Casablanca-Settat | Données socio-économiques, démographie, consommation, entreprises, investissement | Institutionnel | Très haute |
| HCP | Population, ménages, revenus indirects, chômage, projections | Officiel | Haute |
| OMPIC / Baromètre DirectInfo | Création d’entreprises, dynamique économique | Institutionnel | Moyenne |
| ANAM / AMO | Prestataires conventionnés, cadre assurance maladie | Officiel | Moyenne |
| CNSS / AMO | Remboursement, conventionnement, offre de soins remboursable | Officiel | Moyenne |

Liens de départ :

```text
https://www.sante.gov.ma/EtsSante/Pages/default.aspx
https://www.sante.gov.ma/EtsSante/cartesanitaire/Pages/default.aspx
https://www.sante.gov.ma/Regions/Pages/Casablanca-Settat.aspx
https://www.casainvest.ma/fr/casa-stat-e-data
https://edata.casainvest.ma/
https://www.hcp.ma/
https://www.barometreompic.ma/
https://anam.ma/anam/espace-prestataires-de-soins/
```

---

### B. Sources géographiques / POI

| Source | Utilité | Notes |
|---|---|---|
| OpenStreetMap / Overpass API | Hôpitaux, cliniques, pharmacies, médecins, dentistes, laboratoires, géolocalisation | Libre, très utile pour MVP |
| Nominatim | Géocodage inverse/adresses | Respecter limites d’usage |
| GADM / OSM boundaries | Limites administratives, arrondissements | Pour cartes et agrégation spatiale |
| Google Places API | Données riches, avis, horaires, téléphone | Utiliser API officielle uniquement, ne pas scraper Google Maps |
| annuaires médicaux publics | Complément spécialités/téléphones | Vérifier conditions d’utilisation |

Tags OpenStreetMap utiles :

```text
amenity=hospital
amenity=clinic
amenity=doctors
amenity=pharmacy
amenity=dentist
amenity=veterinary
healthcare=doctor
healthcare=hospital
healthcare=clinic
healthcare=laboratory
healthcare=physiotherapist
healthcare=centre
healthcare=pharmacy
healthcare=specialist
```

---

### C. Sources marché / contexte privé

| Source | Utilité |
|---|---|
| Articles économiques fiables : Médias24, La Vie Eco, Challenge, Aujourd’hui le Maroc | Ouvertures de cliniques, investissements, tendances |
| Trade.gov Morocco Healthcare | Vue marché : équipements, privé, digitalisation, opportunités |
| Sites des groupes privés : Akdital, Oncorad, CIM Santé, etc. | Implantations, capacités, spécialisations |
| Appels d’offres publics | Équipement médical, infrastructures, projets régionaux |

---

## 3. Données à collecter

### 3.1 Établissements médicaux

Table cible : `medical_facilities`

| Champ | Type | Exemple |
|---|---|---|
| `id` | string | `osm_123456` |
| `name` | string | `Clinique X` |
| `category` | enum | `hospital`, `clinic`, `pharmacy`, `lab`, `radiology`, `doctor`, `dentist` |
| `sub_category` | string | `cardiology`, `pediatrics`, `oncology`, `imaging` |
| `sector` | enum | `public`, `private`, `unknown` |
| `address` | string | `Maarif, Casablanca` |
| `district` | string | `Maarif` |
| `prefecture` | string | `Casablanca-Anfa` |
| `lat` | float | `33.58` |
| `lon` | float | `-7.62` |
| `phone` | string | `+212...` |
| `website` | string | `https://...` |
| `opening_hours` | string | `Mo-Fr 09:00-18:00` |
| `beds` | int/null | `120` |
| `doctors_count` | int/null | `35` |
| `specialties` | list | `["cardiology", "radiology"]` |
| `source` | string | `OSM`, `Ministry`, `manual`, `API` |
| `source_url` | string | URL |
| `confidence_score` | float | `0.0–1.0` |
| `last_verified_at` | date | `2026-05-18` |

---

### 3.2 Indicateurs socio-économiques par zone

Table cible : `area_indicators`

| Champ | Type | Exemple |
|---|---|---|
| `area_id` | string | `casablanca_maarif` |
| `area_name` | string | `Maarif` |
| `population` | int | `...` |
| `population_density` | float | habitants/km² |
| `household_consumption_proxy` | float | DH/an ou indice |
| `unemployment_rate` | float | % |
| `business_creation_count` | int | nombre entreprises |
| `medical_facilities_count` | int | total |
| `doctors_count` | int | total |
| `pharmacies_count` | int | total |
| `clinics_count` | int | total |
| `hospitals_count` | int | total |
| `nearest_public_hospital_km` | float | km |
| `nearest_emergency_km` | float | km |
| `undersupply_index` | float | 0–100 |
| `investment_score` | float | 0–100 |

---

### 3.3 Spécialités médicales

Table cible : `specialty_supply`

| Champ | Type | Exemple |
|---|---|---|
| `area_name` | string | `Ain Chock` |
| `specialty` | string | `pediatrics` |
| `providers_count` | int | `8` |
| `providers_per_100k` | float | `12.4` |
| `competition_level` | enum | `low`, `medium`, `high` |
| `opportunity_level` | enum | `low`, `medium`, `high` |
| `notes` | string | `Besoin probable si population jeune élevée` |

---

## 4. Métriques d’opportunité

### 4.1 Score général

Proposition :

```text
InvestmentScore =
  0.30 * DemandIndex
+ 0.25 * UndersupplyIndex
+ 0.15 * PurchasingPowerIndex
+ 0.10 * AccessibilityIndex
+ 0.10 * GrowthIndex
+ 0.10 * LowCompetitionIndex
```

Tous les indices sont normalisés entre 0 et 100.

### 4.2 DemandIndex

Variables possibles :

```text
DemandIndex =
  population_density_score
+ population_growth_score
+ age_structure_score
+ household_consumption_proxy
+ distance_to_existing_public_care
```

### 4.3 UndersupplyIndex

```text
UndersupplyIndex = 100 - normalized(facilities_per_100k)
```

Par catégorie :

```text
pharmacy_undersupply = 100 - pharmacies_per_100k_normalized
clinic_undersupply = 100 - clinics_per_100k_normalized
radiology_undersupply = 100 - radiology_centers_per_100k_normalized
lab_undersupply = 100 - labs_per_100k_normalized
```

### 4.4 CompetitionIndex

```text
CompetitionIndex =
  number_of_same_category_facilities_within_radius
+ number_of_high_rating_facilities_within_radius
+ number_of_large_private_groups_nearby
```

Rayons recommandés :

| Type | Rayon primaire | Rayon secondaire |
|---|---:|---:|
| Pharmacie | 300–700 m | 1 km |
| Cabinet généraliste | 500 m–1 km | 2 km |
| Spécialiste | 1–3 km | 5 km |
| Clinique | 3–5 km | 10 km |
| Radiologie / laboratoire | 2–5 km | 10 km |

---

## 5. MVP technique recommandé

### Option simple : Python + Streamlit

```text
invest-search/
  README.md
  requirements.txt
  .env.example

  data/
    raw/
    processed/
    external/
    exports/

  scripts/
    01_collect_osm.py
    02_collect_official_sources.py
    03_clean_normalize.py
    04_geocode.py
    05_compute_scores.py
    06_export_geojson.py

  notebooks/
    exploration_casablanca_healthcare.ipynb

  app/
    streamlit_app.py

  docs/
    sources.md
    data_dictionary.md
    methodology.md
```

### Packages Python

```text
pandas
geopandas
shapely
requests
beautifulsoup4
lxml
python-dotenv
streamlit
folium
streamlit-folium
plotly
scikit-learn
rapidfuzz
```

---

## 6. Requête Overpass API pour Casablanca

Exemple à utiliser dans `01_collect_osm.py` :

```overpass
[out:json][timeout:60];

area["name"="Casablanca"]["boundary"="administrative"]->.searchArea;

(
  node["amenity"~"hospital|clinic|doctors|pharmacy|dentist"](area.searchArea);
  way["amenity"~"hospital|clinic|doctors|pharmacy|dentist"](area.searchArea);
  relation["amenity"~"hospital|clinic|doctors|pharmacy|dentist"](area.searchArea);

  node["healthcare"](area.searchArea);
  way["healthcare"](area.searchArea);
  relation["healthcare"](area.searchArea);
);

out center tags;
```

Alternative si la zone Casablanca n’est pas bien reconnue :

```overpass
[out:json][timeout:60];
(
  node["amenity"~"hospital|clinic|doctors|pharmacy|dentist"](33.45,-7.75,33.70,-7.45);
  way["amenity"~"hospital|clinic|doctors|pharmacy|dentist"](33.45,-7.75,33.70,-7.45);
  relation["amenity"~"hospital|clinic|doctors|pharmacy|dentist"](33.45,-7.75,33.70,-7.45);

  node["healthcare"](33.45,-7.75,33.70,-7.45);
  way["healthcare"](33.45,-7.75,33.70,-7.45);
  relation["healthcare"](33.45,-7.75,33.70,-7.45);
);
out center tags;
```

---

## 7. Prompt principal à donner à Claude Code

Copier-coller ce prompt dans Claude Code à la racine du projet.

```md
Tu es un data engineer + full-stack developer. Construis un MVP nommé "Invest Search" pour analyser les opportunités d’investissement dans le secteur médical à Casablanca.

Objectif :
Créer une pipeline Python qui collecte, nettoie, normalise et visualise les établissements médicaux à Casablanca : hôpitaux, cliniques, pharmacies, cabinets de médecins, dentistes, laboratoires, radiologie, centres de santé.

Contraintes :
- Ne scrape jamais Google Maps directement.
- Utilise OpenStreetMap / Overpass API pour le MVP géographique.
- Prépare des connecteurs propres pour sources officielles : Ministère de la Santé, Casa-Stat/E-Data, HCP, ANAM.
- Respecte les conditions d’utilisation des sites.
- Ne collecte aucune donnée patient.
- Ne stocke que des données publiques professionnelles.
- Tout doit être reproductible et documenté.

Stack :
- Python
- pandas, geopandas, shapely, requests, beautifulsoup4, rapidfuzz
- Streamlit + Folium + Plotly pour le dashboard
- Exports CSV, JSON, GeoJSON

Structure du repo :
- scripts/01_collect_osm.py
- scripts/02_collect_official_sources.py
- scripts/03_clean_normalize.py
- scripts/04_geocode.py
- scripts/05_compute_scores.py
- scripts/06_export_geojson.py
- app/streamlit_app.py
- data/raw
- data/processed
- docs/sources.md
- docs/data_dictionary.md
- docs/methodology.md

Fonctionnalités attendues :
1. Collecter les POI médicaux depuis Overpass API.
2. Convertir les résultats en CSV propre.
3. Normaliser les catégories :
   - hospital
   - clinic
   - pharmacy
   - doctor
   - dentist
   - laboratory
   - radiology
   - health_center
   - unknown
4. Dédupliquer les établissements par nom + distance géographique.
5. Calculer des indicateurs par quartier/zone :
   - nombre total d’établissements
   - pharmacies_count
   - clinics_count
   - hospitals_count
   - doctors_count
   - density_per_km2
   - nearest_hospital_distance
   - competition_index
   - undersupply_index
   - investment_score
6. Créer une carte interactive :
   - filtres par catégorie
   - couleurs selon type d’établissement
   - heatmap de densité médicale
   - zones à fort potentiel
7. Créer une page "Opportunities" :
   - Top 10 zones où ouvrir une pharmacie
   - Top 10 zones où ouvrir un laboratoire
   - Top 10 zones où ouvrir un cabinet spécialisé
   - Top 10 zones où la concurrence est forte
8. Ajouter une méthode claire dans docs/methodology.md.
9. Ajouter un README avec commandes d’installation et d’exécution.

Critères de qualité :
- Code modulaire et commenté.
- Gestion des erreurs API.
- Logs propres.
- Cache local pour éviter de rappeler Overpass inutilement.
- Fichiers CSV versionnés dans data/processed.
- Dashboard lisible et professionnel.

Livrables :
- Repo complet fonctionnel.
- README.md
- requirements.txt
- app Streamlit lançable avec :
  streamlit run app/streamlit_app.py
```

---

## 8. Prompts de recherche à utiliser

### Recherche officielle

```text
Carte sanitaire Casablanca-Settat médecins lits hôpitaux 2023
Santé en chiffres 2023 Casablanca-Settat médecins spécialistes généralistes
Ministère Santé Casablanca Settat hôpitaux publics centres de santé
Direction Régionale Santé Casablanca Settat établissements sanitaires
HCP Casablanca Settat population arrondissements communes
Casa Stat E-Data Casablanca Settat santé infrastructure sociale
```

### Recherche marché privé

```text
cliniques privées Casablanca capacité lits spécialités
groupes cliniques privées Casablanca investissement santé
Akdital Casablanca clinique ouverture capacité
Oncorad Casablanca centre oncologie radiothérapie
CIM Santé Casablanca clinique spécialités
laboratoire analyses médicales Casablanca réseau
centre radiologie Casablanca réseau
```

### Recherche investissement

```text
marché santé Maroc secteur privé Casablanca Settat investissement
Morocco healthcare market Casablanca private clinics
medical equipment Morocco market Casablanca healthcare
digital health Morocco 2025 Casablanca
```

---

## 9. Méthode de validation des données

Chaque donnée doit avoir :

```text
source_url
source_type = official | institutional | osm | directory | press | manual
last_checked_at
confidence_score
```

Barème :

| Score | Critère |
|---:|---|
| 1.00 | Source officielle récente, donnée structurée |
| 0.85 | Source institutionnelle fiable |
| 0.70 | OSM avec nom + coordonnées + tags cohérents |
| 0.60 | Annuaire public vérifiable |
| 0.50 | Article de presse économique fiable |
| 0.30 | Donnée non vérifiée / manuelle |

---

## 10. Nettoyage et normalisation

### Déduplication

Utiliser :

- distance géographique < 50 m
- similarité nom > 85 %
- même catégorie ou catégorie proche

Exemple :

```text
"Clinique Maarif" ≈ "Clinique Al Maarif"
distance = 22 m
similarity = 91 %
=> fusionner
```

### Normalisation des noms

Règles :

```text
- trim spaces
- lowercase pour comparaison seulement
- supprimer ponctuation excessive
- uniformiser clinique/clinic, pharmacie/pharmacy, laboratoire/lab
- garder le nom original dans original_name
```

### Normalisation catégories

Mapping initial :

```python
CATEGORY_MAP = {
    "hospital": ["hospital", "hôpital", "hopital", "chu"],
    "clinic": ["clinic", "clinique", "polyclinique"],
    "pharmacy": ["pharmacy", "pharmacie"],
    "doctor": ["doctors", "cabinet médical", "medecin", "médecin"],
    "dentist": ["dentist", "dentiste"],
    "laboratory": ["laboratory", "lab", "laboratoire", "analyses"],
    "radiology": ["radiology", "radiologie", "imagerie", "scanner", "irm"],
    "health_center": ["centre de santé", "dispensaire", "essb"],
}
```

---

## 11. Dashboard attendu

Pages :

### Page 1 — Overview

- Nombre total d’établissements
- Répartition par catégorie
- Répartition public / privé / inconnu
- Carte générale
- Top zones médicalement denses
- Top zones sous-équipées

### Page 2 — Map Explorer

Filtres :

- catégorie
- spécialité
- secteur
- rayon autour d’un point
- niveau de confiance
- source

### Page 3 — Opportunity Finder

Sorties :

| Zone | Catégorie recommandée | Score | Raison |
|---|---|---:|---|
| Ain Chock | Laboratoire | 82 | population élevée + faible densité lab |
| Sidi Moumen | Cabinet généraliste | 79 | densité forte + offre limitée |
| Nouaceur | Clinique proximité | 76 | croissance urbaine + distance hôpital |

### Page 4 — Competition

- Carte des zones saturées
- Concurrents majeurs
- distance au plus proche concurrent
- densité dans rayon 1 km / 3 km / 5 km

### Page 5 — Data Quality

- taux de données géocodées
- doublons détectés
- sources utilisées
- établissements à vérifier manuellement

---

## 12. Données initiales à intégrer manuellement

À partir des sources officielles, créer un fichier `data/manual/official_baseline.csv`.

Champs :

```csv
metric,geography,value,year,source,source_url,notes
public_hospitals,Grand Casablanca,15,unknown,Ministry of Health,https://www.sante.gov.ma/Regions/Pages/GrandCasablanca.aspx,
functional_beds,Grand Casablanca,3089,unknown,Ministry of Health,https://www.sante.gov.ma/Regions/Pages/GrandCasablanca.aspx,1451 au CHU Ibn Rochd
essb,Grand Casablanca,130,unknown,Ministry of Health,https://www.sante.gov.ma/Regions/Pages/GrandCasablanca.aspx,
doctors_total,Casablanca-Settat,5826,2023,Ministry of Health - Sante en chiffres 2023,https://www.sante.gov.ma/Documents/2025/02/Sante%20en%20chiffre%202023%20VF%20%281%29.pdf,1830 généralistes + 3996 spécialistes
household_consumption_share,Casablanca-Settat,25.3,2022,Casa-Stat E-Data,https://edata.casainvest.ma/,part nationale des dépenses de consommation finale des ménages
household_consumption_per_capita,Casablanca-Settat,27128,2022,Casa-Stat E-Data,https://edata.casainvest.ma/,DH par tête
```

---

## 13. Risques et limites

### Risques data

- OSM peut être incomplet ou mal tagué.
- Les annuaires privés peuvent être obsolètes.
- Les données officielles peuvent être agrégées au niveau région/province, pas quartier.
- Les spécialités médicales ne sont pas toujours disponibles.
- Les capacités des cliniques privées ne sont pas toujours publiques.

### Risques légaux / éthiques

- Ne pas collecter de données patients.
- Ne pas scraper Google Maps.
- Respecter robots.txt et les CGU des annuaires.
- Stocker uniquement les informations professionnelles publiques.
- Marquer clairement les données estimées ou inférées.

### Risques business

- Un score élevé ne garantit pas la rentabilité.
- L’investissement médical dépend aussi des autorisations, loyers, RH, réglementation, remboursement AMO, concurrence informelle et image de marque.
- Les données doivent aider à décider, pas remplacer une étude terrain.

---

## 14. Roadmap

### Phase 1 — MVP data

- Collecte OSM
- Nettoyage
- Carte Streamlit
- Export CSV/GeoJSON
- Premier score d’opportunité

### Phase 2 — Enrichissement

- Intégration Casa-Stat / HCP
- Ajout spécialités
- Ajout distances aux hôpitaux publics
- Déduplication avancée

### Phase 3 — Business intelligence

- Scoring par type d’investissement
- Rapport automatique PDF
- Comparaison quartiers
- Simulation : “où ouvrir une clinique ?”

### Phase 4 — Produit SaaS

- Authentification
- Interface web Next.js
- Base PostgreSQL/PostGIS
- API FastAPI
- Abonnement investisseur
- Export rapport investisseur

---

## 15. Commandes attendues

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install -r requirements.txt

python scripts/01_collect_osm.py
python scripts/03_clean_normalize.py
python scripts/05_compute_scores.py
python scripts/06_export_geojson.py

streamlit run app/streamlit_app.py
```

---

## 16. Format final des exports

```text
data/processed/medical_facilities_clean.csv
data/processed/area_indicators.csv
data/processed/specialty_supply.csv
data/exports/medical_facilities.geojson
data/exports/investment_opportunities.csv
```

---

## 17. Résultat attendu du projet

À la fin, Invest Search doit pouvoir afficher :

1. une carte des établissements médicaux à Casablanca ;
2. une mesure de densité médicale par zone ;
3. une estimation de la concurrence ;
4. un score d’opportunité par quartier et par type d’investissement ;
5. une liste priorisée des zones à investiguer sur le terrain.

Formule simple à garder en tête :

```text
Bonne opportunité =
forte demande
+ faible offre actuelle
+ accessibilité correcte
+ pouvoir d’achat suffisant
+ concurrence maîtrisable
+ faisabilité réglementaire
```
