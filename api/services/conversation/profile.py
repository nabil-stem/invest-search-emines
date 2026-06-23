"""Structured investor profile + context-aware extraction.

The profile is the conversational memory's *structured* half: it accumulates the
investor's budget / sector / zone / objective across turns so a short follow-up
("Sidi Moumen", "compare avec Maarif", "et pour un restaurant ?") is interpreted
in context instead of as a brand-new question.

Extraction reuses the project's existing, battle-tested detectors
(`_detected_category`, `_sector_from_question`, `_zones_from_question`,
`consulting.parse_budget`) rather than re-implementing them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from api.services import consulting
from api.services.invest_data import (
    SECTORS,
    _detected_category,
    _normalize_text,
    _sector_category_from_question,
    _sector_from_question,
    _zones_from_question,
)

# Words that signal the user wants the SYSTEM to find/rank the zone (so a zone is
# not a required input — it is the answer).
_OPEN_ENDED_SIGNALS = (
    "ou ouvrir", "ou implanter", "quelle zone", "quel quartier", "quels quartiers",
    "meilleure zone", "meilleur quartier", "faible concurrence", "faible couverture",
    "sous equipe", "rapport", "recommand", "conseill", "classement", "top ",
    "ou est", "ou sont",
)

# Declarative intent ("I want / I have …") — when the user states a project but
# does not say *where* and does not ask the system to find it, we clarify.
_DECLARATIVE_SIGNALS = (
    "je veux", "je souhaite", "j ai", "jai", "je compte", "je pense", "je voudrais",
    "i want", "i have", "j aimerais",
)

_COMPARISON_SIGNALS = ("compare", "comparer", "comparaison", "versus", " vs ", "oppose")

_RESET_SIGNALS = (
    "nouvelle discussion", "nouvelle conversation", "recommence", "reset",
    "efface tout", "reinitialise", "new chat", "restart",
)


@dataclass
class InvestorProfile:
    budget: float | None = None
    sector: str | None = None            # "medical" | food | retail | education | wellness
    business_type: str | None = None     # medical category key (e.g. "Pharmacy") or sector key
    zone: str | None = None
    city: str = "Casablanca"
    objective: str | None = None         # "ouverture" | "comparaison"
    constraints: list = field(default_factory=list)
    risk_preference: str | None = None
    comparison_zones: list = field(default_factory=list)
    requested_output: str | None = None  # "rapport" | "carte"

    @classmethod
    def from_dict(cls, data: dict | None) -> "InvestorProfile":
        data = data or {}
        known = {f for f in cls.__dataclass_fields__}  # noqa: SLF001
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict:
        return asdict(self)

    def has_any_field(self) -> bool:
        return any([
            self.budget, self.sector, self.business_type, self.zone,
            self.comparison_zones, self.objective,
        ])


def is_reset(message: str) -> bool:
    norm = _normalize_text(message)
    return any(sig in norm for sig in _RESET_SIGNALS)


def is_open_ended(message: str, history: list[dict] | None = None) -> bool:
    """True when the user asks the system to find/rank the zone (no zone needed)."""
    norm = _normalize_text(message)
    return any(sig in norm for sig in _OPEN_ENDED_SIGNALS)


def _is_declarative(message: str) -> bool:
    norm = _normalize_text(message)
    return any(sig in norm for sig in _DECLARATIVE_SIGNALS)


def update_profile(profile: InvestorProfile, message: str) -> InvestorProfile:
    """Merge fields extracted from `message` into `profile` (context-aware)."""
    norm = _normalize_text(message)

    budget = consulting.parse_budget(message)
    if budget is not None:
        profile.budget = budget

    category = _detected_category(message)      # medical category or None
    sector_category = _sector_category_from_question(message)
    sector = sector_category[0] if sector_category else _sector_from_question(message)
    if category:
        profile.sector = "medical"
        profile.business_type = category
    elif sector:
        profile.sector = sector
        profile.business_type = sector_category[1] if sector_category else sector

    zones = _zones_from_question(message)
    is_comparison = any(sig in f" {norm} " for sig in _COMPARISON_SIGNALS)
    if is_comparison:
        profile.objective = "comparaison"
        if not profile.zone and zones:
            profile.zone = zones[0]
            zones = zones[1:]
        for z in zones:
            if z != profile.zone and z not in profile.comparison_zones:
                profile.comparison_zones.append(z)
    elif zones:
        # Bare zone mention(s): the first becomes/updates the focus zone.
        profile.zone = zones[0]
        if len(zones) > 1:
            profile.objective = "comparaison"
            profile.comparison_zones = [z for z in zones[1:] if z != zones[0]]

    if profile.objective != "comparaison" and any(
        w in norm for w in ("ouvrir", "ouverture", "implanter", "implantation", "lancer", "ouvre")
    ):
        profile.objective = "ouverture"

    if "rapport" in norm or "report" in norm:
        profile.requested_output = "rapport"
    elif "carte" in norm or norm.strip() == "map" or " map " in f" {norm} ":
        profile.requested_output = "carte"

    if "faible risque" in norm or "peu de risque" in norm or "prudent" in norm:
        profile.risk_preference = "faible"
    elif "fort potentiel" in norm or "agressif" in norm:
        profile.risk_preference = "eleve"

    return profile


def business_type_fr(profile: InvestorProfile) -> str:
    """Human label for the establishment type."""
    from api.services.invest_data import CATEGORY_DISPLAY_FR

    if profile.business_type is None:
        return "un établissement"
    if profile.sector == "medical":
        label = CATEGORY_DISPLAY_FR.get(profile.business_type, profile.business_type).lower()
        return f"un(e) {label}"
    # non-medical sector
    sector = SECTORS.get(profile.sector or "")
    label = (
        sector.category_labels_fr.get(profile.business_type, profile.business_type)
        if sector else profile.business_type
    )
    return f"un projet {label}"
