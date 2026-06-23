"""Chatbot assistant: local deterministic mode + optional LLM mode.

Local mode uses pandas queries and template answers — always works.
LLM mode sends a compact data summary to an API if configured.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

# ── Data access (imported lazily to avoid circular deps at module level) ──

_facilities: pd.DataFrame | None = None
_areas: pd.DataFrame | None = None
_spec: pd.DataFrame | None = None


def _load_data():
    global _facilities, _areas, _spec
    try:
        from utils.data_loader import load_facilities, load_area_indicators, load_specialty_supply
    except ImportError:
        from app.utils.data_loader import load_facilities, load_area_indicators, load_specialty_supply
    _facilities = load_facilities()
    _areas = load_area_indicators()
    _spec = load_specialty_supply()


def _fac() -> pd.DataFrame:
    if _facilities is None:
        _load_data()
    return _facilities


def _areas_df() -> pd.DataFrame:
    if _areas is None:
        _load_data()
    return _areas


def _spec_df() -> pd.DataFrame:
    if _spec is None:
        _load_data()
    return _spec


# ── Chatbot tool functions ───────────────────────────────────────────────

def get_top_opportunities(category: str | None = None, zone: str | None = None, n: int = 5) -> str:
    try:
        from utils.scoring import compute_opportunity_scores, INVESTMENT_CATEGORIES
    except ImportError:
        from app.utils.scoring import compute_opportunity_scores, INVESTMENT_CATEGORIES
    areas = _areas_df()
    spec = _spec_df()
    if areas.empty:
        return "No area data available. Please run the data pipeline first."

    inv_type = None
    if category:
        cat_lower = category.lower()
        for name in INVESTMENT_CATEGORIES:
            if cat_lower in name.lower():
                inv_type = name
                break
    if not inv_type:
        inv_type = "Pharmacy"

    scores = compute_opportunity_scores(areas, spec, inv_type)
    if zone:
        scores = scores[scores["area_name"].str.lower() == zone.lower()]
    top = scores.head(n)
    if top.empty:
        return f"No opportunity data found for {inv_type}" + (f" in {zone}" if zone else "") + "."

    lines = [f"**Top {len(top)} zones for {inv_type}:**\n"]
    for _, r in top.iterrows():
        lines.append(
            f"- **{r['area_name']}** — Investment Readiness: {r['investment_readiness_score']:.1f}/100, "
            f"Risk: {r['risk_score']:.1f}, Competition: {r['competition_level']}, "
            f"Supply Gap: {r['supply_gap']:.0f}/100"
        )
    lines.append("\n*Field validation is required before any investment decision.*")
    return "\n".join(lines)


def compare_zones(zones: list[str], category: str | None = None) -> str:
    areas = _areas_df()
    if areas.empty:
        return "No area data available."

    found = areas[areas["area_name"].str.lower().isin([z.lower() for z in zones])]
    if found.empty:
        return f"Zones not found: {', '.join(zones)}. Available: {', '.join(areas['area_name'].tolist())}."

    lines = [f"**Comparison: {' vs '.join(found['area_name'].tolist())}**\n"]
    lines.append("| Metric | " + " | ".join(found["area_name"]) + " |")
    lines.append("|---|" + "---|" * len(found) + "")

    metrics = [
        ("Population", "population_est", "{:,.0f}"),
        ("Density (/km²)", "population_density", "{:,.0f}"),
        ("Facilities", "medical_facilities_count", "{:.0f}"),
        ("Per 100k", "facilities_per_100k", "{:.1f}"),
        ("Supply Gap", "undersupply_index", "{:.1f}"),
        ("Readiness Score", "investment_score", "{:.1f}"),
    ]
    for label, col, fmt in metrics:
        if col in found.columns:
            vals = [fmt.format(found[found["area_name"] == z][col].iloc[0])
                    if z in found["area_name"].values else "—"
                    for z in found["area_name"]]
            lines.append(f"| {label} | " + " | ".join(vals) + " |")
    return "\n".join(lines)


def explain_zone_opportunity(zone: str, category: str | None = None) -> str:
    areas = _areas_df()
    fac = _fac()
    if areas.empty:
        return "No data available."

    row = areas[areas["area_name"].str.lower() == zone.lower()]
    if row.empty:
        return f"Zone '{zone}' not found. Available zones: {', '.join(areas['area_name'].tolist())}."

    z = row.iloc[0]
    pop = int(z.get("population_est", 0))
    density = z.get("population_density", 0)
    total = int(z.get("medical_facilities_count", 0))
    score = z.get("investment_score", 0)
    gap = z.get("undersupply_index", 0)

    zone_fac = fac[fac["district"].str.lower() == zone.lower()] if not fac.empty else pd.DataFrame()
    cats = zone_fac["category"].value_counts().to_dict() if not zone_fac.empty else {}

    lines = [f"**{z['area_name']}** — Investment Analysis\n"]
    lines.append(f"- Population: ~{pop:,}")
    lines.append(f"- Density: {density:,.0f}/km²")
    lines.append(f"- Total mapped facilities: {total}")
    if cats:
        lines.append(f"- Breakdown: " + ", ".join(f"{v} {k}" for k, v in cats.items()))
    lines.append(f"- Investment Readiness Score: {score:.1f}/100")
    lines.append(f"- Supply Gap Index: {gap:.1f}/100")

    if score >= 65:
        lines.append(f"\n{z['area_name']} shows **strong investment potential**. "
                      f"The supply gap of {gap:.0f}/100 suggests unmet demand.")
    elif score >= 45:
        lines.append(f"\n{z['area_name']} shows **moderate opportunity**. "
                      f"Competition is present but gaps exist in specific categories.")
    else:
        lines.append(f"\n{z['area_name']} has **limited opportunity** based on current data. "
                      f"The market appears relatively served.")
    lines.append("\n*Data confidence is moderate (OSM-based). Field validation is essential.*")
    return "\n".join(lines)


def get_competition_summary(zone: str, category: str | None = None) -> str:
    fac = _fac()
    if fac.empty:
        return "No facility data available."

    zone_fac = fac[fac["district"].str.lower() == zone.lower()]
    if zone_fac.empty:
        return f"No facilities found in '{zone}'."

    total = len(zone_fac)
    cats = zone_fac["category"].value_counts()
    lines = [f"**Competition in {zone}:** {total} facilities\n"]
    for cat, count in cats.items():
        lines.append(f"- {cat}: {count}")

    if total > 50:
        lines.append(f"\nThis zone has **high facility density**. New entrants need strong differentiation.")
    elif total > 20:
        lines.append(f"\nModerate competition. Opportunities exist in under-represented categories.")
    else:
        lines.append(f"\nLow competition. Most categories have growth potential.")
    return "\n".join(lines)


def get_data_quality_summary() -> str:
    fac = _fac()
    if fac.empty:
        return "No facility data loaded."

    total = len(fac)
    geocoded = (fac["lat"].notna() & fac["lon"].notna()).sum()
    named = (fac["name"].notna() & (fac["name"] != "")).sum()
    low_conf = (fac["confidence_score"] < 0.5).sum()
    unknown_dist = (fac["district"] == "Unknown").sum()

    return (
        f"**Data Quality Summary**\n\n"
        f"- Total facilities: {total:,}\n"
        f"- Geocoded: {geocoded:,} ({geocoded/total*100:.0f}%)\n"
        f"- Named: {named:,} ({named/total*100:.0f}%)\n"
        f"- Low confidence (<0.50): {low_conf:,}\n"
        f"- Unknown district: {unknown_dist:,}\n"
        f"- Primary source: OpenStreetMap\n\n"
        f"*OSM coverage varies by neighborhood. Official data is aggregated at province level. "
        f"Field validation is required for investment decisions.*"
    )


def generate_investor_summary(zone: str, category: str | None = None) -> str:
    result = explain_zone_opportunity(zone, category)
    if category:
        result += "\n\n" + get_top_opportunities(category, zone, n=3)
    return result


def search_facilities(query: str, category: str | None = None, zone: str | None = None) -> str:
    fac = _fac()
    if fac.empty:
        return "No facility data available."

    mask = fac["name"].str.contains(query, case=False, na=False)
    if category:
        mask &= fac["category"].str.lower() == category.lower()
    if zone:
        mask &= fac["district"].str.lower() == zone.lower()

    results = fac[mask].head(10)
    if results.empty:
        return f"No facilities found matching '{query}'."

    lines = [f"**Search results for '{query}'** ({len(results)} shown):\n"]
    for _, r in results.iterrows():
        lines.append(f"- **{r.get('name', 'Unnamed')}** — {r['category']}, {r['district']}, "
                      f"confidence: {r['confidence_score']:.2f}")
    return "\n".join(lines)


# ── Intent detection and routing (local mode) ───────────────────────────

INTENT_PATTERNS = [
    (r"(?:best|top|where).+(?:open|invest|start).+(?:pharmacy|pharmacie)", "top_pharmacy"),
    (r"(?:best|top|where).+(?:open|invest|start).+(?:lab|laboratory|laboratoire)", "top_lab"),
    (r"(?:best|top|where).+(?:open|invest|start).+(?:radiol|imagerie)", "top_radiology"),
    (r"(?:best|top|where).+(?:open|invest|start).+(?:dent|dentist)", "top_dentist"),
    (r"(?:best|top|where).+(?:open|invest|start).+(?:clinic|clinique)", "top_clinic"),
    (r"(?:best|top|where).+(?:open|invest|start)", "top_generic"),
    (r"(?:top|best)\s*(?:\d+)?\s*(?:zone|area|district)", "top_zones"),
    (r"(?:compare|vs|versus)\s+(\w[\w\s']*?)\s+(?:and|vs|versus|,|&)\s+(\w[\w\s']*)", "compare"),
    (r"(?:why|explain|about|tell me about)\s+(.+?)(?:\s+(?:for|is|good|opportunity))?$", "explain"),
    (r"(?:competition|competitor|saturated|saturation)\s+(?:in\s+)?(.+)", "competition"),
    (r"(?:data quality|missing data|what.+missing|quality)", "data_quality"),
    (r"(?:search|find|look for)\s+(.+)", "search"),
    (r"(?:investor|investment|report|summary)\s+(?:for\s+)?(.+)", "investor_summary"),
    (r"low.+competition", "low_competition"),
]


def _extract_zone(text: str) -> str | None:
    areas = _areas_df()
    if areas.empty:
        return None
    for zone in areas["area_name"].tolist():
        if zone.lower() in text.lower():
            return zone
    return None


def process_local(user_input: str) -> str:
    """Process a user message using local deterministic mode."""
    text = user_input.strip()
    if not text:
        return "Please enter a question about medical investment opportunities in Casablanca."

    text_lower = text.lower()

    # Pattern matching
    for pattern, intent in INTENT_PATTERNS:
        m = re.search(pattern, text_lower)
        if m:
            if intent == "top_pharmacy":
                return get_top_opportunities("pharmacy")
            elif intent == "top_lab":
                return get_top_opportunities("laboratory")
            elif intent == "top_radiology":
                return get_top_opportunities("radiology")
            elif intent == "top_dentist":
                return get_top_opportunities("dental")
            elif intent == "top_clinic":
                return get_top_opportunities("clinic")
            elif intent == "top_generic":
                return get_top_opportunities()
            elif intent == "top_zones":
                return get_top_opportunities(n=5)
            elif intent == "compare":
                z1, z2 = m.group(1).strip(), m.group(2).strip()
                return compare_zones([z1, z2])
            elif intent == "explain":
                zone_text = m.group(1).strip() if m.lastindex else text
                zone = _extract_zone(zone_text)
                if zone:
                    return explain_zone_opportunity(zone)
                return explain_zone_opportunity(zone_text)
            elif intent == "competition":
                zone_text = m.group(1).strip()
                zone = _extract_zone(zone_text) or zone_text
                return get_competition_summary(zone)
            elif intent == "data_quality":
                return get_data_quality_summary()
            elif intent == "search":
                query = m.group(1).strip()
                return search_facilities(query)
            elif intent == "investor_summary":
                zone_text = m.group(1).strip()
                zone = _extract_zone(zone_text) or zone_text
                return generate_investor_summary(zone)
            elif intent == "low_competition":
                areas = _areas_df()
                if not areas.empty and "low_competition_index" in areas.columns:
                    top = areas.nlargest(5, "low_competition_index")
                    lines = ["**Zones with lowest competition:**\n"]
                    for _, r in top.iterrows():
                        lines.append(f"- **{r['area_name']}** — {int(r.get('medical_facilities_count', 0))} "
                                      f"facilities, score {r.get('investment_score', 0):.1f}")
                    return "\n".join(lines)
                return "No competition data available."

    # Fallback: try zone detection
    zone = _extract_zone(text)
    if zone:
        return explain_zone_opportunity(zone)

    return (
        "I can help you with medical investment analysis for Casablanca. Try asking:\n\n"
        "- *Where should I open a pharmacy?*\n"
        "- *Compare Maarif and Ain Chock*\n"
        "- *Why is Sidi Moumen a good opportunity?*\n"
        "- *Show zones with low competition*\n"
        "- *What data is missing?*\n"
        "- *Generate investor summary for Anfa*\n"
        "- *Search for clinique*\n"
    )


# ── Optional LLM mode ───────────────────────────────────────────────────

def _get_llm_config() -> dict | None:
    provider = os.environ.get("LLM_PROVIDER", "none").lower()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if provider == "none" or not api_key:
        return None
    return {"provider": provider, "api_key": api_key}


def _build_context_summary() -> str:
    """Build a compact data summary for LLM context (not the full dataset)."""
    areas = _areas_df()
    fac = _fac()
    if areas.empty:
        return "No data loaded."

    lines = [
        f"Casablanca medical data: {len(fac)} facilities across {len(areas)} districts.",
        "Districts (name, population, facilities, investment_score):"
    ]
    for _, r in areas.iterrows():
        lines.append(f"  {r['area_name']}: pop={int(r.get('population_est',0)):,}, "
                      f"fac={int(r.get('medical_facilities_count',0))}, "
                      f"score={r.get('investment_score',0):.1f}")

    cats = fac["category"].value_counts()
    lines.append(f"\nCategory totals: " + ", ".join(f"{k}={v}" for k, v in cats.items()))
    return "\n".join(lines)


def process_llm(user_input: str) -> str | None:
    """Try LLM-based answer. Returns None if LLM is not configured or fails."""
    cfg = _get_llm_config()
    if cfg is None:
        return None

    context = _build_context_summary()
    system_prompt = (
        "You are Invest Search, a medical market intelligence assistant for Casablanca. "
        "Answer using only the data provided. Be concise, professional, and business-oriented. "
        "Always mention when field validation is required. Never invent exact numbers. "
        "Use terms: Investment Readiness, Supply Gap, Competitive Landscape, Data Confidence.\n\n"
        f"DATA CONTEXT:\n{context}"
    )

    try:
        if cfg["provider"] == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=cfg["api_key"])
            msg = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_input}],
            )
            return msg.content[0].text

        elif cfg["provider"] == "openai":
            import openai
            client = openai.OpenAI(api_key=cfg["api_key"])
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1024,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
            )
            return resp.choices[0].message.content

    except Exception as e:
        return f"LLM error: {e}. Falling back to local mode."

    return None


def process(user_input: str) -> str:
    """Main entry point: try LLM, fallback to local."""
    llm_result = process_llm(user_input)
    if llm_result:
        return llm_result
    return process_local(user_input)


def get_mode_label() -> str:
    cfg = _get_llm_config()
    if cfg:
        return f"LLM mode ({cfg['provider']})"
    return "Local analysis mode"
