"""Investor report generation: on-screen data + PDF export."""

from __future__ import annotations

import io
from datetime import date

import pandas as pd


def generate_investor_report(zone: str, investment_type: str,
                              areas: pd.DataFrame, score_row: dict) -> dict:
    """Build a structured report dict for display and PDF rendering."""
    area = areas[areas["area_name"] == zone]
    pop = int(area["population_est"].iloc[0]) if not area.empty else 0
    density = round(area["population_density"].iloc[0], 0) if not area.empty else 0

    inv_score = score_row.get("investment_readiness_score", 0)
    risk = score_row.get("risk_score", 0)
    comp = score_row.get("competition_level", "N/A")
    gap = score_row.get("supply_gap", 0)
    providers = score_row.get("providers_count", 0)
    data_conf = score_row.get("data_confidence", 65)

    if inv_score >= 70:
        verdict = "Strong Opportunity"
    elif inv_score >= 50:
        verdict = "Moderate Opportunity"
    else:
        verdict = "Limited Opportunity"

    reasons = []
    if gap > 60:
        reasons.append(f"Significant supply gap detected ({gap:.0f}/100).")
    if comp in ("Low", "Medium"):
        reasons.append(f"Competition is {comp.lower()}, leaving room for a new entrant.")
    if density > 15000:
        reasons.append(f"High population density ({density:,.0f}/km²) suggests strong footfall potential.")
    if providers == 0:
        reasons.append(f"No existing {investment_type.lower()} facilities mapped in this zone.")
    if not reasons:
        reasons.append("General opportunity based on composite scoring model.")

    risks = []
    if risk >= 60:
        risks.append("Elevated overall risk. Thorough field due diligence is critical.")
    if data_conf < 70:
        risks.append("Data confidence is moderate — OSM coverage may be incomplete.")
    if comp in ("High", "Saturated"):
        risks.append(f"Competition level is {comp.lower()}. New entrants face pricing and positioning challenges.")
    if pop < 80000:
        risks.append("Relatively low population base may limit patient volume.")
    if not risks:
        risks.append("Standard market entry risks apply. Field validation recommended.")

    checklist = [
        "Visit the zone and walk a 500m radius around the target location.",
        "Count existing competing facilities manually.",
        "Verify rent/lease costs for commercial medical-grade spaces.",
        "Check proximity to public transport and parking availability.",
        "Interview local residents and pharmacists about unmet needs.",
        "Verify regulatory requirements (authorisation d'exercice, conformité sanitaire).",
        "Assess availability of qualified medical staff in the area.",
        "Review AMO/CNSS reimbursement eligibility for planned services.",
    ]

    next_steps = [
        "Conduct a 2-week field observation of patient flows and competitor activity.",
        "Engage a local real estate agent specialized in medical/commercial spaces.",
        "Prepare a financial feasibility model (CAPEX, OPEX, break-even timeline).",
        "Consult a healthcare regulatory advisor for licensing requirements.",
        "Develop a competitive positioning strategy based on field findings.",
    ]

    return {
        "title": f"Investment Opportunity Report — {zone}",
        "date": date.today().isoformat(),
        "zone": zone,
        "investment_type": investment_type,
        "population": pop,
        "population_density": density,
        "verdict": verdict,
        "investment_readiness_score": round(inv_score, 1),
        "risk_score": round(risk, 1),
        "competition_level": comp,
        "supply_gap": round(gap, 1),
        "data_confidence": round(data_conf, 1),
        "providers_in_zone": providers,
        "reasons": reasons,
        "risks": risks,
        "checklist": checklist,
        "next_steps": next_steps,
    }


def export_report_pdf(report: dict) -> bytes | None:
    """Render the report dict as a PDF. Returns bytes or None on failure."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        return None

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=18,
                                  spaceAfter=12, textColor=colors.HexColor("#1a365d"))
    heading_style = ParagraphStyle("ReportH2", parent=styles["Heading2"], fontSize=13,
                                    spaceAfter=6, textColor=colors.HexColor("#2d3748"))
    body_style = ParagraphStyle("ReportBody", parent=styles["Normal"], fontSize=10,
                                 spaceAfter=4, leading=14)
    small_style = ParagraphStyle("ReportSmall", parent=styles["Normal"], fontSize=8,
                                  textColor=colors.grey)

    elements = []

    elements.append(Paragraph(report["title"], title_style))
    elements.append(Paragraph(f"Generated: {report['date']}  |  Invest Search — Medical Market Intelligence", small_style))
    elements.append(Spacer(1, 0.5 * cm))

    # Summary table
    summary_data = [
        ["Investment Type", report["investment_type"]],
        ["Zone", report["zone"]],
        ["Verdict", report["verdict"]],
        ["Investment Readiness Score", f"{report['investment_readiness_score']}/100"],
        ["Risk Score", f"{report['risk_score']}/100"],
        ["Competition Level", report["competition_level"]],
        ["Supply Gap Index", f"{report['supply_gap']}/100"],
        ["Data Confidence", f"{report['data_confidence']}%"],
        ["Population (est.)", f"{report['population']:,}"],
        ["Population Density", f"{report['population_density']:,.0f}/km²"],
        ["Existing Providers in Zone", str(report["providers_in_zone"])],
    ]
    t = Table(summary_data, colWidths=[6 * cm, 10 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf2f7")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.5 * cm))

    # Reasons
    elements.append(Paragraph("Key Opportunity Drivers", heading_style))
    for r in report["reasons"]:
        elements.append(Paragraph(f"•  {r}", body_style))
    elements.append(Spacer(1, 0.3 * cm))

    # Risks
    elements.append(Paragraph("Risk Factors", heading_style))
    for r in report["risks"]:
        elements.append(Paragraph(f"•  {r}", body_style))
    elements.append(Spacer(1, 0.3 * cm))

    # Checklist
    elements.append(Paragraph("Field Validation Checklist", heading_style))
    for i, item in enumerate(report["checklist"], 1):
        elements.append(Paragraph(f"{i}.  {item}", body_style))
    elements.append(Spacer(1, 0.3 * cm))

    # Next steps
    elements.append(Paragraph("Suggested Next Steps", heading_style))
    for i, item in enumerate(report["next_steps"], 1):
        elements.append(Paragraph(f"{i}.  {item}", body_style))
    elements.append(Spacer(1, 0.5 * cm))

    # Disclaimer
    elements.append(Paragraph(
        "<i>Disclaimer: This report is generated from publicly available data (OpenStreetMap, "
        "Ministry of Health, Casa-Stat). Scores are indicative and do not constitute financial "
        "or legal advice. Field validation, regulatory compliance checks, and professional "
        "feasibility studies are required before any investment decision.</i>",
        small_style,
    ))

    doc.build(elements)
    return buf.getvalue()
