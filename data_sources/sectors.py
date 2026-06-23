"""Sector packs — the abstraction that lets Invest Search go beyond medical.

Each sector declares:
  * label_fr        : French display label
  * osm_filters     : list of (osm_key, value_regex) used to build the Overpass
                      query. A value of ".+" means "tag exists with any value".
  * categories      : sub-category -> keyword list, used to classify a POI within
                      the sector (matched against amenity/shop/healthcare/name).
  * confidence      : default per-POI confidence (OSM reliability varies by sector)

This mirrors the medical `INVESTMENT_CATEGORIES` design (in app/utils/scoring.py)
one level up, so the same OSM pipeline, scoring skeleton and RAG can serve any
sector. See docs/multi_sector_feasibility.md for the rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Sector:
    key: str
    label_fr: str
    osm_filters: list[tuple[str, str]]
    categories: dict[str, list[str]] = field(default_factory=dict)
    category_labels_fr: dict[str, str] = field(default_factory=dict)
    category_intent_aliases: dict[str, list[str]] = field(default_factory=dict)
    category_score_weights: dict[str, dict[str, float]] = field(default_factory=dict)
    confidence: float = 0.70
    score_weights: dict[str, float] = field(
        default_factory=lambda: {
            "population": 0.25,
            "density": 0.20,
            "purchasing_power": 0.20,
            "low_competition": 0.25,
            "osm_confidence": 0.10,
        }
    )
    competition_thresholds_per_100k: tuple[float, float] = (10.0, 45.0)


SECTORS: dict[str, Sector] = {
    "medical": Sector(
        key="medical",
        label_fr="marché médical",
        osm_filters=[
            ("amenity", "hospital|clinic|doctors|pharmacy|dentist|veterinary"),
            ("healthcare", ".+"),
        ],
        categories={
            "hospital": ["hospital", "hôpital", "hopital", "chu"],
            "clinic": ["clinic", "clinique", "polyclinique"],
            "pharmacy": ["pharmacy", "pharmacie"],
            "doctor": ["doctors", "doctor", "medecin", "médecin"],
            "dentist": ["dentist", "dentiste"],
            "laboratory": ["laboratory", "laboratoire", "analyses"],
            "radiology": ["radiology", "radiologie", "imagerie", "scanner", "irm"],
            "health_center": ["centre de santé", "dispensaire", "health_centre", "physiothérapie"],
            "veterinary": ["veterinary", "vétérinaire"],
        },
        confidence=0.70,
        score_weights={
            "population": 0.25,
            "density": 0.20,
            "purchasing_power": 0.20,
            "low_competition": 0.25,
            "osm_confidence": 0.10,
        },
        competition_thresholds_per_100k=(8.0, 35.0),
    ),
    "food": Sector(
        key="food",
        label_fr="restauration",
        osm_filters=[
            ("amenity", "restaurant|cafe|fast_food|bar|pub|food_court|ice_cream"),
        ],
        categories={
            "restaurant": ["restaurant"],
            "cafe": ["cafe", "café", "coffee"],
            "fast_food": ["fast_food"],
            "bar": ["bar", "pub"],
            "ice_cream": ["ice_cream", "glacier"],
        },
        category_labels_fr={
            "restaurant": "restaurant",
            "cafe": "café",
            "fast_food": "fast-food",
            "bar": "bar",
            "ice_cream": "glacier",
        },
        category_intent_aliases={
            "restaurant": ["restaurant", "restaurants", "resto", "restos"],
            "cafe": ["café", "cafés", "cafe", "cafes", "coffee shop", "coffee shops"],
            "fast_food": ["fast food", "fast foods", "snack", "snacks"],
            "bar": ["bar", "bars", "pub", "pubs"],
            "ice_cream": ["glacier", "glaciers", "glace", "glaces"],
        },
        category_score_weights={
            "restaurant": {"population": 0.10, "density": 0.28, "purchasing_power": 0.32, "low_competition": 0.20, "osm_confidence": 0.10},
            "cafe": {"population": 0.08, "density": 0.28, "purchasing_power": 0.36, "low_competition": 0.18, "osm_confidence": 0.10},
            "fast_food": {"population": 0.18, "density": 0.32, "purchasing_power": 0.18, "low_competition": 0.22, "osm_confidence": 0.10},
        },
        confidence=0.72,  # OSM coverage of F&B in Casablanca is strong
        score_weights={
            "population": 0.18,
            "density": 0.18,
            "purchasing_power": 0.26,
            "low_competition": 0.26,
            "osm_confidence": 0.12,
        },
        competition_thresholds_per_100k=(20.0, 85.0),
    ),
    "retail": Sector(
        key="retail",
        label_fr="commerce de détail",
        osm_filters=[
            ("shop", ".+"),
        ],
        categories={
            "supermarket": ["supermarket", "convenience", "grocery"],
            "clothing": ["clothes", "clothing", "boutique", "shoes", "fashion"],
            "electronics": ["electronics", "mobile_phone", "computer"],
            "bakery": ["bakery", "pastry", "boulangerie"],
            "furniture": ["furniture", "houseware"],
            "hardware": ["hardware", "doityourself", "trade"],
        },
        category_labels_fr={
            "supermarket": "supermarché",
            "clothing": "boutique de vêtements",
            "electronics": "magasin d'électronique",
            "bakery": "boulangerie",
            "furniture": "magasin de meubles",
            "hardware": "quincaillerie",
            "sports": "magasin de sport",
        },
        category_intent_aliases={
            "supermarket": ["supermarché", "supermarchés", "supermarche", "supermarches", "épicerie", "epicerie"],
            "clothing": ["boutique de vêtements", "boutiques de vêtements", "vetements", "vêtement", "vêtements", "habillement", "chaussures"],
            "electronics": ["magasin électronique", "magasin electronique", "électronique", "electronique", "téléphone", "telephone", "informatique"],
            "bakery": ["boulangerie", "boulangeries", "pâtisserie", "patisserie", "pâtisseries", "patisseries"],
            "furniture": ["magasin de meubles", "meubles", "mobilier"],
            "hardware": ["quincaillerie", "quincailleries", "bricolage"],
            "sports": ["magasin de sport", "magasins de sport", "articles de sport"],
        },
        category_score_weights={
            "supermarket": {"population": 0.28, "density": 0.22, "purchasing_power": 0.18, "low_competition": 0.22, "osm_confidence": 0.10},
            "clothing": {"population": 0.10, "density": 0.22, "purchasing_power": 0.38, "low_competition": 0.20, "osm_confidence": 0.10},
            "electronics": {"population": 0.10, "density": 0.16, "purchasing_power": 0.42, "low_competition": 0.20, "osm_confidence": 0.12},
            "bakery": {"population": 0.22, "density": 0.30, "purchasing_power": 0.18, "low_competition": 0.20, "osm_confidence": 0.10},
        },
        confidence=0.62,  # informal retail is under-mapped
        score_weights={
            "population": 0.16,
            "density": 0.18,
            "purchasing_power": 0.32,
            "low_competition": 0.22,
            "osm_confidence": 0.12,
        },
        competition_thresholds_per_100k=(18.0, 75.0),
    ),
    "education": Sector(
        key="education",
        label_fr="éducation",
        osm_filters=[
            ("amenity", "school|kindergarten|college|university|language_school|driving_school"),
        ],
        categories={
            "school": ["school", "école", "ecole"],
            "kindergarten": ["kindergarten", "crèche", "creche", "maternelle"],
            "university": ["university", "université", "college", "faculté"],
            "language_school": ["language_school", "langues"],
            "driving_school": ["driving_school", "auto-école"],
        },
        category_labels_fr={
            "school": "école",
            "kindergarten": "crèche",
            "university": "université",
            "language_school": "école de langues",
            "driving_school": "auto-école",
        },
        category_intent_aliases={
            "school": ["école", "écoles", "ecole", "ecoles", "établissement scolaire", "etablissement scolaire"],
            "kindergarten": ["crèche", "crèches", "creche", "creches", "maternelle", "maternelles"],
            "university": ["université", "universités", "universite", "universites", "faculté", "faculte", "college", "collège"],
            "language_school": ["école de langues", "ecole de langues", "centre de langues", "cours de langues"],
            "driving_school": ["auto-école", "auto-écoles", "auto ecole", "auto ecoles", "école de conduite", "ecole de conduite"],
        },
        category_score_weights={
            "school": {"population": 0.30, "density": 0.12, "purchasing_power": 0.30, "low_competition": 0.18, "osm_confidence": 0.10},
            "kindergarten": {"population": 0.26, "density": 0.28, "purchasing_power": 0.22, "low_competition": 0.14, "osm_confidence": 0.10},
            "university": {"population": 0.15, "density": 0.22, "purchasing_power": 0.34, "low_competition": 0.19, "osm_confidence": 0.10},
            "language_school": {"population": 0.12, "density": 0.20, "purchasing_power": 0.38, "low_competition": 0.20, "osm_confidence": 0.10},
            "driving_school": {"population": 0.18, "density": 0.20, "purchasing_power": 0.28, "low_competition": 0.24, "osm_confidence": 0.10},
        },
        confidence=0.65,
        score_weights={
            "population": 0.24,
            "density": 0.12,
            "purchasing_power": 0.30,
            "low_competition": 0.24,
            "osm_confidence": 0.10,
        },
        competition_thresholds_per_100k=(6.0, 28.0),
    ),
    "wellness": Sector(
        key="wellness",
        label_fr="bien-être & beauté",
        osm_filters=[
            ("shop", "hairdresser|beauty|massage|cosmetics|optician"),
            ("leisure", "fitness_centre|sports_centre|spa"),
            ("amenity", "gym|spa|public_bath"),
        ],
        categories={
            "hairdresser": ["hairdresser", "coiffure", "salon"],
            "beauty": ["beauty", "beauté", "esthetique", "cosmetics"],
            "fitness": ["fitness_centre", "gym", "sports_centre", "salle de sport"],
            "spa": ["spa", "massage", "hammam", "bain", "public_bath", "bath"],
            "optician": ["optician", "optique", "opticien"],
        },
        category_labels_fr={
            "hairdresser": "salon de coiffure",
            "beauty": "institut de beauté",
            "fitness": "salle de sport",
            "spa": "spa ou hammam",
            "optician": "opticien",
        },
        category_intent_aliases={
            "hairdresser": ["salon de coiffure", "salons de coiffure", "coiffeur", "coiffeurs", "coiffure"],
            "beauty": ["institut de beauté", "instituts de beauté", "beaute", "beauté", "esthétique", "esthetique", "cosmétiques", "cosmetiques"],
            "fitness": ["salle de sport", "salles de sport", "fitness", "gym", "gyms", "centre sportif", "club de sport"],
            "spa": ["spa", "spas", "hammam", "hammams", "massage", "massages"],
            "optician": ["opticien", "opticiens", "optique", "magasin d'optique", "magasins d'optique"],
        },
        category_score_weights={
            "hairdresser": {"population": 0.18, "density": 0.28, "purchasing_power": 0.26, "low_competition": 0.18, "osm_confidence": 0.10},
            "beauty": {"population": 0.12, "density": 0.22, "purchasing_power": 0.42, "low_competition": 0.14, "osm_confidence": 0.10},
            "fitness": {"population": 0.12, "density": 0.22, "purchasing_power": 0.38, "low_competition": 0.16, "osm_confidence": 0.12},
            "spa": {"population": 0.08, "density": 0.18, "purchasing_power": 0.48, "low_competition": 0.14, "osm_confidence": 0.12},
            "optician": {"population": 0.14, "density": 0.18, "purchasing_power": 0.42, "low_competition": 0.16, "osm_confidence": 0.10},
        },
        confidence=0.60,
        score_weights={
            "population": 0.18,
            "density": 0.18,
            "purchasing_power": 0.28,
            "low_competition": 0.22,
            "osm_confidence": 0.14,
        },
        competition_thresholds_per_100k=(6.0, 32.0),
    ),
}


def get_sector(key: str) -> Sector:
    if key not in SECTORS:
        raise KeyError(f"Unknown sector '{key}'. Available: {', '.join(SECTORS)}")
    return SECTORS[key]


def sector_keys() -> list[str]:
    return list(SECTORS)
