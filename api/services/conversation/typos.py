"""Lightweight typo tolerance for domain terms.

Misspellings ("pharmacei", "concurence", "labau") used to break category/intent
detection and fall to out-of-scope. We fuzzy-correct only tokens that are *close*
to a known domain word (high threshold) before detection. The user's ORIGINAL
text is always what gets displayed — only the internal detection sees the
corrected form. Zone names keep their own fuzzy resolver in invest_data.
"""

from __future__ import annotations

from rapidfuzz import fuzz, process

from api.services.invest_data import _normalize_text

# Canonical domain vocabulary (accent-free) that investors commonly mistype.
_VOCAB: tuple[str, ...] = (
    # medical
    "pharmacie", "clinique", "laboratoire", "labo", "analyses", "dentiste", "dentaire",
    "veterinaire", "radiologie", "imagerie", "cabinet", "hopital", "medecin", "pediatrie",
    "dermatologie", "physiotherapie",
    # non-medical sectors
    "restaurant", "cafe", "commerce", "boutique", "magasin", "supermarche", "boulangerie",
    "ecole", "creche", "universite", "fitness", "coiffure", "beaute", "hammam", "optique",
    "pharmacie",
    # analytics / intent
    "concurrence", "budget", "ouvrir", "implanter", "investir", "opportunite", "quartier",
    "score", "densite", "population", "faisabilite", "superficie", "saturation", "scoring",
    "methodologie", "couverture",
)

_VOCAB_SET = set(_VOCAB)

# Frequent misspellings that fuzzy matching can miss (start-of-word changes,
# 'ph'->'f', dropped letters). Applied as exact token replacements first.
_COMMON_TYPOS = {
    "farmacie": "pharmacie", "farmaci": "pharmacie", "pharmaci": "pharmacie",
    "pharmacei": "pharmacie", "pharamcie": "pharmacie", "pharmcie": "pharmacie",
    "klinik": "clinique", "clinic": "clinique", "kliniK": "clinique", "cliniq": "clinique",
    "laboratoir": "laboratoire", "labau": "labo", "laboratuar": "laboratoire",
    "restaurent": "restaurant", "restaurnt": "restaurant", "resto": "restaurant",
    "concurance": "concurrence", "concurence": "concurrence", "concurrance": "concurrence",
    "concurrence": "concurrence",
    "ecol": "ecole", "ecoles": "ecole", "creche": "creche",
    "denist": "dentiste", "dentit": "dentiste",
    "veterinair": "veterinaire", "radiolog": "radiologie",
    "budjet": "budget", "buget": "budget", "investire": "investir", "investisement": "investissement",
    "ouvir": "ouvrir", "ouvrr": "ouvrir", "ouvre": "ouvrir",
}

# Tokens we must never "correct" (would distort out-of-scope / common words).
_STOP = {
    "pour", "dans", "avec", "une", "un", "des", "les", "est", "que", "qui", "quel",
    "quelle", "comment", "pourquoi", "ouvre", "veux", "souhaite", "casablanca",
}


def correct_typos(message: str) -> str:
    """Return the message with close-to-domain tokens snapped to the canonical term."""
    out: list[str] = []
    for raw in message.split():
        norm = _normalize_text(raw).strip()
        # Exact common-misspelling map first (catches what fuzzy misses).
        if norm in _COMMON_TYPOS:
            out.append(_COMMON_TYPOS[norm])
            continue
        if len(norm) < 4 or norm in _VOCAB_SET or norm in _STOP:
            out.append(raw)
            continue
        match = process.extractOne(norm, _VOCAB, scorer=fuzz.ratio, score_cutoff=85)
        # Only correct genuine typos (not already exact), and not a big rewrite.
        if match and match[0] != norm and fuzz.ratio(norm, match[0]) >= 86:
            out.append(match[0])
        else:
            out.append(raw)
    return " ".join(out)
