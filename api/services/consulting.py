"""Budget-aware consulting layer for Invest Search.

Turns the platform from a "where" tool into a "where + can I afford it + what
should I do" advisor. Given an investor's stated budget, it estimates whether a
given establishment type is feasible, how much runway is left for operations,
and — when the budget doesn't fit — which establishment types *do* fit.

IMPORTANT: the cost figures are **indicative planning ranges** for Casablanca
(turnkey CAPEX: pas-de-porte/local, fit-out, equipment, licensing, initial
working capital; plus a rough monthly OPEX). They are not quotes and must be
validated with real suppliers, landlords and the relevant authorities. This
module never gives a definitive financial recommendation — it frames scenarios.

When a zone is known, the API applies an OPEX multiplier from local rent proxies
(`rent_commercial_med` when available, otherwise purchasing-power and density
signals from `area_indicators.csv`) so runway varies by district.

All amounts are in Moroccan Dirham (MAD / DH).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Cost model (indicative, MAD). capex = (low, typical, high); opex_month rough.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CostProfile:
    capex_low: float
    capex_typical: float
    capex_high: float
    opex_month: float
    drivers: str  # main cost drivers, for the consultative explanation


# Medical categories — keys match app/utils/scoring.py INVESTMENT_CATEGORIES.
CATEGORY_COSTS: dict[str, CostProfile] = {
    "Pharmacy": CostProfile(900_000, 1_600_000, 3_000_000, 45_000,
                            "droit au bail / transfert de licence, stock initial, agencement"),
    "Medical Analysis Laboratory": CostProfile(1_200_000, 2_500_000, 5_000_000, 70_000,
                            "automates d'analyse, accréditation, personnel qualifié"),
    "Radiology Center": CostProfile(3_000_000, 6_000_000, 15_000_000, 120_000,
                            "équipement d'imagerie (scanner/IRM), local technique, radioprotection"),
    "Dental Clinic": CostProfile(500_000, 900_000, 1_800_000, 40_000,
                            "fauteuils dentaires, radiologie, stérilisation"),
    "Veterinary Clinic": CostProfile(300_000, 550_000, 1_000_000, 30_000,
                            "bloc de soins, imagerie, hospitalisation animale"),
    "General Doctor Cabinet": CostProfile(200_000, 350_000, 700_000, 25_000,
                            "aménagement cabinet, mobilier médical de base"),
    "Pediatric Cabinet": CostProfile(200_000, 350_000, 700_000, 25_000,
                            "aménagement cabinet, équipement pédiatrique"),
    "Dermatology Cabinet": CostProfile(350_000, 600_000, 1_200_000, 35_000,
                            "équipement laser/esthétique, agencement"),
    "Physiotherapy Center": CostProfile(250_000, 450_000, 900_000, 30_000,
                            "plateau de rééducation, appareils, espace"),
    "Small Private Clinic": CostProfile(3_000_000, 7_000_000, 20_000_000, 200_000,
                            "blocs, hospitalisation, équipe médicale, autorisations"),
    "Emergency Care Center": CostProfile(6_000_000, 12_000_000, 30_000_000, 350_000,
                            "plateau technique 24/7, équipe, équipement lourd"),
}

# Non-medical sectors — keys match data_sources/sectors.py.
SECTOR_COSTS: dict[str, CostProfile] = {
    "food": CostProfile(300_000, 800_000, 3_000_000, 50_000,
                        "pas-de-porte, cuisine/agencement, licence, fonds de roulement"),
    "retail": CostProfile(200_000, 500_000, 1_500_000, 35_000,
                        "local commercial, stock initial, agencement vitrine"),
    "education": CostProfile(500_000, 1_200_000, 8_000_000, 60_000,
                        "mise aux normes, autorisation académique, équipement pédagogique"),
    "wellness": CostProfile(200_000, 600_000, 3_000_000, 35_000,
                        "équipement (sport/esthétique), agencement, personnel"),
}

SECTOR_LABELS = {
    "food": "restauration", "retail": "commerce de détail",
    "education": "éducation", "wellness": "bien-être & beauté",
}


def format_mad(amount: float) -> str:
    """Human-friendly MAD: 1 600 000 -> '1,6 M DH', 350000 -> '350 k DH'."""
    amount = float(amount)
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f} M DH".replace(".0 M", " M")
    if amount >= 1_000:
        return f"{amount / 1_000:.0f} k DH"
    return f"{amount:.0f} DH"


_NUM_RE = re.compile(
    r"(\d[\d\s.,]*)\s*(m(?:illions?)?|k|mille)?\s*(dh|dhs|mad|dirhams?|dirham)?",
    re.IGNORECASE,
)


def parse_budget(text: str) -> float | None:
    """Extract a budget amount in MAD from free French/English text.

    Handles: '500000 dh', '500 000 DH', '1 million de dirhams', '1,5M',
    '200k mad', '2 millions'. Requires either a currency token or a
    million/k multiplier near the number to avoid grabbing random digits.
    """
    low = text.lower()
    if not any(tok in low for tok in ("dh", "mad", "dirham", "budget", "million", "k ", "k.", "investir", "capital", "enveloppe")):
        return None

    best: float | None = None
    for m in _NUM_RE.finditer(low):
        raw, mult, cur = m.group(1), m.group(2) or "", m.group(3) or ""
        digits = raw.replace(" ", "").replace(".", "").replace(",", ".")
        # Drop a trailing '.' that came from a thousands separator like "500."
        digits = digits.rstrip(".")
        if not re.search(r"\d", digits):
            continue
        try:
            value = float(digits)
        except ValueError:
            continue
        mult = mult.lower()
        if mult.startswith("m"):
            value *= 1_000_000
        elif mult in ("k", "mille"):
            value *= 1_000
        # Only accept if there's a currency or a multiplier (else it's noise).
        if not (cur or mult):
            continue
        # Plausible business budget band.
        if 10_000 <= value <= 500_000_000:
            best = value if best is None else max(best, value)
    return best


def _verdict(budget: float, p: CostProfile) -> str:
    if budget < p.capex_low:
        return "insufficient"
    if budget < p.capex_typical:
        return "tight"
    if budget < p.capex_high:
        return "comfortable"
    return "ample"


def assess(key: str, budget: float, is_sector: bool, opex_multiplier: float = 1.0) -> dict | None:
    """Assess a budget against one establishment type. Returns a structured dict."""
    profile = (SECTOR_COSTS if is_sector else CATEGORY_COSTS).get(key)
    if profile is None:
        return None

    opex_multiplier = max(0.75, min(1.45, float(opex_multiplier or 1.0)))
    adjusted_opex = round(profile.opex_month * opex_multiplier)
    verdict = _verdict(budget, profile)
    coverage = round(budget / profile.capex_typical, 2) if profile.capex_typical else 0.0
    # Runway = months of OPEX covered by what's left after a typical setup.
    leftover = budget - profile.capex_typical
    runway = int(max(0, leftover) // adjusted_opex) if adjusted_opex else 0
    # Indicative payback pressure: turnkey CAPEX divided by an estimated monthly
    # contribution margin. This is a planning proxy, not a forecast.
    contribution_proxy = max(adjusted_opex * 0.35, 1)
    payback_months = round(profile.capex_typical / contribution_proxy, 1)

    return {
        "key": key,
        "is_sector": is_sector,
        "verdict": verdict,
        "capex_low": profile.capex_low,
        "capex_typical": profile.capex_typical,
        "capex_high": profile.capex_high,
        "opex_month": adjusted_opex,
        "base_opex_month": profile.opex_month,
        "opex_multiplier": round(opex_multiplier, 2),
        "drivers": profile.drivers,
        "budget": budget,
        "coverage_of_typical": coverage,
        "runway_months": runway,
        "payback_months": payback_months,
    }


def affordable_options(budget: float, limit: int = 6) -> list[dict]:
    """Establishment types whose *typical* setup cost fits the budget, cheapest
    first — used to advise when the requested type doesn't fit."""
    options = []
    for key, p in CATEGORY_COSTS.items():
        if p.capex_typical <= budget:
            options.append({"key": key, "is_sector": False, "label": key, "capex_typical": p.capex_typical})
    for key, p in SECTOR_COSTS.items():
        if p.capex_typical <= budget:
            options.append({"key": key, "is_sector": True, "label": SECTOR_LABELS.get(key, key), "capex_typical": p.capex_typical})
    options.sort(key=lambda o: o["capex_typical"])
    return options[:limit]


VERDICT_FR = {
    "insufficient": "budget insuffisant pour un projet standard",
    "tight": "budget serré — projet possible en version optimisée",
    "comfortable": "budget confortable pour un projet standard",
    "ample": "budget large — permet une version premium ou multi-sites",
}
