"""Invest Search — Medical Market Intelligence Platform for Casablanca.

11-page professional dashboard: Executive Overview, Market Map, Opportunity Finder,
Competition Radar, Best Location Simulator, Zone Comparison, Facility Database,
Investor Report, Data Quality, Chatbot Assistant, Settings.
"""

from pathlib import Path

import folium
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from folium.plugins import HeatMap, MarkerCluster
from streamlit_folium import st_folium

from utils.data_loader import (
    load_area_indicators, load_facilities, load_opportunities,
    load_specialty_supply, get_zone_names,
)
from utils.scoring import (
    INVESTMENT_CATEGORIES, best_categories_for_zone, competition_level_label,
    compute_competition_radius, compute_opportunity_scores,
    compute_saturation_score, get_nearest_competitors, haversine_km,
)
from utils.reporting import export_report_pdf, generate_investor_report
from utils.ui import (
    DANGER, WARNING,
    badge, competition_badge, inject_css, no_data_warning,
    render_footer, render_sidebar, styled_dataframe,
    page_header, section_header, stat_card, card_container,
    empty_state, info_panel, score_color,
)
from utils.chatbot import process as chatbot_process, get_mode_label

st.set_page_config(
    page_title="Invest Search",
    layout="wide", page_icon="IS", initial_sidebar_state="expanded",
)
inject_css()

PLOTLY_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, system-ui, sans-serif", size=12, color="#334155"),
    margin=dict(l=0, r=0, t=36, b=0),
    title_font=dict(size=13, color="#1e293b"),
    coloraxis_colorbar=dict(thickness=12),
)

CAT_COLORS = {
    "hospital": "#dc2626", "clinic": "#2563eb", "pharmacy": "#059669",
    "doctor": "#ea580c", "dentist": "#7c3aed", "laboratory": "#1d4ed8",
    "radiology": "#0891b2", "health_center": "#16a34a",
    "veterinary": "#6b7280", "unknown": "#94a3b8",
}
CAT_COLORS_FOLIUM = {
    "hospital": "red", "clinic": "blue", "pharmacy": "green",
    "doctor": "orange", "dentist": "purple", "laboratory": "darkblue",
    "radiology": "cadetblue", "health_center": "darkgreen",
    "veterinary": "gray", "unknown": "lightgray",
}


# ═══════════════════════════════════════════════════════════════════════════
# Page 1 — Executive Overview
# ═══════════════════════════════════════════════════════════════════════════

def page_executive_overview():
    page_header("Executive Overview", "Casablanca medical market at a glance")
    fac = load_facilities()
    areas = load_area_indicators()
    if fac.empty:
        no_data_warning(); return

    total = len(fac)

    r1 = st.columns(5)
    with r1[0]:
        stat_card("Total Facilities", f"{total:,}", f"{fac['district'].nunique()} districts")
    with r1[1]:
        stat_card("Pharmacies", f"{(fac['category']=='pharmacy').sum():,}")
    with r1[2]:
        stat_card("Clinics & Hospitals", f"{(fac['category'].isin(['clinic','hospital'])).sum():,}")
    with r1[3]:
        stat_card("Doctors", f"{(fac['category']=='doctor').sum():,}")
    with r1[4]:
        avg_conf = round(fac["confidence_score"].mean() * 100, 0) if "confidence_score" in fac.columns else 0
        stat_card("Data Confidence", f"{avg_conf}%", "avg. across all records")

    st.markdown("")

    if not areas.empty:
        top_opp = areas.nlargest(1, "investment_score")["area_name"].iloc[0]
        top_sat = areas.nsmallest(1, "investment_score")["area_name"].iloc[0]
        high_conf = (fac["confidence_score"] >= 0.7).sum()

        st.markdown(
            f"> **{total:,}** facilities mapped across **{fac['district'].nunique()}** districts. "
            f"**{top_opp}** ranks highest for new investment. **{top_sat}** is most competitive. "
            f"{high_conf/total*100:.0f}% records have confidence >= 0.70."
        )

        left, right = st.columns(2)
        with left:
            section_header("Top Opportunity Zones", "Highest investment readiness scores")
            t5 = areas.nlargest(5, "investment_score")[["area_name", "investment_score", "undersupply_index", "population_est"]].reset_index(drop=True)
            t5.columns = ["Zone", "Readiness", "Supply Gap", "Population"]
            styled_dataframe(t5, "Readiness")
        with right:
            section_header("Most Competitive Zones", "Lowest investment readiness scores")
            s5 = areas.nsmallest(5, "investment_score")[["area_name", "investment_score", "medical_facilities_count", "population_est"]].reset_index(drop=True)
            s5.columns = ["Zone", "Readiness", "Facilities", "Population"]
            styled_dataframe(s5, "Readiness")

        left, right = st.columns(2)
        with left:
            cc = fac["category"].value_counts().reset_index()
            cc.columns = ["Category", "Count"]
            fig = px.bar(cc, x="Category", y="Count", color="Category", color_discrete_map=CAT_COLORS,
                         title="Supply by Category")
            fig.update_layout(**PLOTLY_LAYOUT, showlegend=False, height=340)
            st.plotly_chart(fig, use_container_width=True)
        with right:
            fig = px.bar(areas.sort_values("investment_score", ascending=True),
                         x="investment_score", y="area_name", orientation="h",
                         color="investment_score", color_continuous_scale="RdYlGn",
                         title="Investment Readiness by District")
            fig.update_layout(**PLOTLY_LAYOUT, height=340)
            st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# Page 2 — Market Map
# ═══════════════════════════════════════════════════════════════════════════

def page_market_map():
    page_header("Market Map", "Interactive map of all medical facilities")
    fac = load_facilities()
    if fac.empty:
        no_data_warning(); return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        cats = st.multiselect("Category", sorted(fac["category"].unique()),
                              default=sorted(fac["category"].unique()), key="mm_cat")
    with c2:
        sources = sorted(fac["source"].dropna().unique()) if "source" in fac.columns else []
        src_sel = st.multiselect("Source", sources, default=sources, key="mm_src")
    with c3:
        conf_min = st.slider("Min confidence", 0.0, 1.0, 0.0, 0.05, key="mm_conf")
    with c4:
        all_dist = sorted(fac["district"].unique())
        dist_sel = st.multiselect("District", all_dist, key="mm_dist")

    f = fac[fac["category"].isin(cats) & (fac["confidence_score"] >= conf_min)]
    if src_sel:
        f = f[f["source"].isin(src_sel)]
    if dist_sel:
        f = f[f["district"].isin(dist_sel)]

    col_map, col_side = st.columns([5, 1])
    with col_side:
        show_heat = st.checkbox("Heatmap", key="mm_heat")
        st.markdown(f"<div style='font-size:0.8rem; font-weight:600; color:#0f172a; "
                    f"margin:0.5rem 0 0.25rem 0;'>{len(f):,} facilities</div>",
                    unsafe_allow_html=True)
        for cat, color in CAT_COLORS.items():
            if cat in cats:
                st.markdown(
                    f"<div style='display:flex; align-items:center; gap:6px; "
                    f"font-size:0.72rem; color:#475569; margin:1px 0;'>"
                    f"<span style='width:8px; height:8px; border-radius:2px; "
                    f"background:{color}; flex-shrink:0;'></span>"
                    f"{cat.replace('_', ' ').title()}</div>",
                    unsafe_allow_html=True,
                )

    with col_map:
        m = folium.Map(location=[33.57, -7.59], zoom_start=12, tiles="CartoDB positron")
        if show_heat:
            pts = f[["lat", "lon"]].dropna().values.tolist()
            if pts:
                HeatMap(pts, radius=18, blur=15, max_zoom=15).add_to(m)
        else:
            cluster = MarkerCluster()
            for _, row in f.iterrows():
                if pd.notna(row["lat"]) and pd.notna(row["lon"]):
                    cat = row.get("category", "unknown")
                    popup = (f"<div style='font-family:system-ui; font-size:12px; line-height:1.5;'>"
                             f"<b>{row.get('name') or 'Unnamed'}</b><br>"
                             f"{cat} &middot; {row.get('district', '-')}<br>"
                             f"<span style='color:#64748b'>Confidence: {row.get('confidence_score', '-')}</span>"
                             f"</div>")
                    folium.Marker(
                        [row["lat"], row["lon"]],
                        popup=folium.Popup(popup, max_width=240),
                        icon=folium.Icon(color=CAT_COLORS_FOLIUM.get(cat, "gray"), icon="plus", prefix="fa"),
                    ).add_to(cluster)
            cluster.add_to(m)
        st_folium(m, width=None, height=520)

    with st.expander("View raw data"):
        st.dataframe(f, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════
# Page 3 — Opportunity Finder
# ═══════════════════════════════════════════════════════════════════════════

def page_opportunity_finder():
    page_header("Opportunity Finder", "Scored investment recommendations by zone and category")
    areas = load_area_indicators()
    spec = load_specialty_supply()
    if areas.empty:
        no_data_warning(); return

    c1, c2 = st.columns(2)
    with c1:
        inv_type = st.selectbox("Investment category", list(INVESTMENT_CATEGORIES.keys()))
    with c2:
        zones = get_zone_names(areas)
        zone_filter = st.selectbox("Zone filter", ["All Casablanca"] + zones)

    scores = compute_opportunity_scores(areas, spec, inv_type)
    if scores.empty:
        st.warning("Could not compute scores."); return

    if zone_filter != "All Casablanca":
        scores = scores[scores["area_name"] == zone_filter]

    display = scores[["area_name", "investment_readiness_score", "supply_gap", "competition_level",
                       "risk_score", "providers_count"]].copy()
    display.columns = ["Zone", "Readiness", "Supply Gap", "Competition", "Risk", "Providers"]
    styled_dataframe(display, "Readiness")

    st.caption(f"Weights: " + " / ".join(f"{k} {v:.0%}" for k, v in INVESTMENT_CATEGORIES[inv_type]["weights"].items()))

    left, right = st.columns(2)
    with left:
        fig = px.bar(scores.head(10), x="investment_readiness_score", y="area_name",
                     orientation="h", color="investment_readiness_score",
                     color_continuous_scale="RdYlGn",
                     title=f"Investment Readiness - {inv_type}")
        fig.update_layout(**PLOTLY_LAYOUT, height=360, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)
    with right:
        if not spec.empty:
            cat_key = INVESTMENT_CATEGORIES[inv_type]["data_category"]
            cat_spec = spec[spec["specialty"] == cat_key]
            if not cat_spec.empty:
                fig = px.bar(cat_spec.sort_values("providers_per_100k"),
                             x="providers_per_100k", y="area_name", orientation="h",
                             title=f"{cat_key.title()} per 100k by Zone",
                             color="providers_per_100k", color_continuous_scale="RdYlGn_r")
                fig.update_layout(**PLOTLY_LAYOUT, height=360, yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig, use_container_width=True)

    if not spec.empty:
        section_header("Supply Density Matrix", "Providers per 100k - lower = more opportunity")
        pivot = spec.pivot_table(index="area_name", columns="specialty", values="providers_per_100k", fill_value=0)
        fig = px.imshow(pivot, text_auto=".0f", color_continuous_scale="RdYlGn_r",
                        title="")
        fig.update_layout(**PLOTLY_LAYOUT, height=480)
        st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# Page 4 — Competition Radar
# ═══════════════════════════════════════════════════════════════════════════

def page_competition_radar():
    page_header("Competition Radar", "Analyze competitive density around any location")
    fac = load_facilities()
    areas = load_area_indicators()
    if fac.empty:
        no_data_warning(); return

    mode = st.radio("Analysis target", ["Facility", "Zone"], horizontal=True)

    if mode == "Facility":
        named = fac[fac["name"].notna() & (fac["name"] != "")].copy()
        if named.empty:
            st.warning("No named facilities."); return
        named["label"] = named["name"] + " (" + named["category"] + ", " + named["district"] + ")"
        sel = st.selectbox("Select facility", named["label"].sort_values().tolist())
        row = named[named["label"] == sel].iloc[0]
        center_lat, center_lon, category = row["lat"], row["lon"], row["category"]
        if pd.isna(center_lat) or pd.isna(center_lon):
            st.error("No coordinates."); return
    else:
        zones = get_zone_names(areas)
        if not zones:
            st.warning("No zone data."); return
        c1, c2 = st.columns(2)
        with c1:
            zone = st.selectbox("Zone", zones)
        with c2:
            category = st.selectbox("Category", sorted(fac["category"].unique()))
        zf = fac[fac["district"] == zone].dropna(subset=["lat", "lon"])
        if zf.empty:
            center_lat, center_lon = 33.57, -7.59
        else:
            center_lat, center_lon = zf["lat"].mean(), zf["lon"].mean()

    comp = compute_competition_radius(fac, center_lat, center_lon, category)
    sat = compute_saturation_score(comp, category)
    level = competition_level_label(sat)

    st.markdown("")
    cols = st.columns(6)
    with cols[0]:
        stat_card("Saturation", f"{sat}/100", "", score_color(100 - sat))
    with cols[1]:
        st.markdown(f"<div style='padding-top:12px;'>{competition_badge(level)}</div>", unsafe_allow_html=True)
    for i, (radius, data) in enumerate(comp.items()):
        with cols[i + 2]:
            stat_card(f"Within {radius}", str(data['same_category']),
                      f"{data['all_facilities']} total nearby")

    count_1km = comp.get("1 km", {}).get("same_category", 0)
    st.markdown(
        f"> **{level}** competition for **{category}** — "
        f"**{count_1km}** similar facilities within 1 km. "
        + ("Field validation recommended." if sat < 50 else "Strong differentiation required.")
    )

    nearest = get_nearest_competitors(fac, center_lat, center_lon, category, n=10)
    if not nearest.empty:
        section_header("Nearest Competitors")
        nearest["distance_km"] = nearest["distance_km"].round(2)
        st.dataframe(nearest, use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    with left:
        labels = list(comp.keys())
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=[comp[r]["same_category"] for r in labels], theta=labels,
            fill="toself", name=f"Same ({category})",
            line=dict(color="#2563eb"),
        ))
        fig.add_trace(go.Scatterpolar(
            r=[comp[r]["all_facilities"] for r in labels], theta=labels,
            fill="toself", name="All facilities",
            line=dict(color="#94a3b8"),
        ))
        fig.update_layout(**PLOTLY_LAYOUT, polar=dict(radialaxis=dict(visible=True)),
                          title="Competition Radius", height=380, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        m = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles="CartoDB positron")
        folium.Marker([center_lat, center_lon],
                      icon=folium.Icon(color="red", icon="crosshairs", prefix="fa")).add_to(m)
        folium.Circle([center_lat, center_lon], radius=1000,
                      color="#2563eb", fill=False, weight=2).add_to(m)
        folium.Circle([center_lat, center_lon], radius=3000,
                      color="#94a3b8", fill=False, weight=1, dash_array="5").add_to(m)
        nearby = fac.dropna(subset=["lat", "lon"])
        for _, r in nearby.iterrows():
            d = haversine_km(center_lat, center_lon, r["lat"], r["lon"])
            if d <= 3:
                folium.CircleMarker(
                    [r["lat"], r["lon"]], radius=4,
                    color=CAT_COLORS.get(r["category"], "#94a3b8"),
                    fill=True, fill_opacity=0.7,
                    popup=f"{r.get('name', '?')} ({r['category']})",
                ).add_to(m)
        st_folium(m, width=None, height=380)


# ═══════════════════════════════════════════════════════════════════════════
# Page 5 — Best Location Simulator
# ═══════════════════════════════════════════════════════════════════════════

def page_best_location():
    page_header("Best Location Simulator", "Find the best investment category for any zone")
    areas = load_area_indicators()
    spec = load_specialty_supply()
    if areas.empty:
        no_data_warning(); return

    zone = st.selectbox("Select a zone", get_zone_names(areas))
    rankings = best_categories_for_zone(zone, areas, spec)
    if not rankings:
        st.warning("Cannot compute recommendations."); return

    zr = areas[areas["area_name"] == zone]
    if not zr.empty:
        z = zr.iloc[0]
        info_panel([
            ("Population", f"{int(z['population_est']):,}"),
            ("Density", f"{z['population_density']:,.0f}/km²"),
            ("Facilities", str(int(z['medical_facilities_count']))),
            ("Purchasing Power", f"{z.get('purchasing_power_proxy', 50):.0f}/100"),
        ])

    st.markdown("")
    rec = [r for r in rankings if r["recommended"]]
    not_rec = [r for r in rankings if not r["recommended"]]

    section_header("Recommended", f"{len(rec)} categories meet the threshold")
    if rec:
        for r in rec:
            col_name, col_score, col_risk, col_comp, col_gap = st.columns([2.5, 1, 1, 1, 1])
            col_name.markdown(f"**{r['category']}**")
            col_score.markdown(f"<span style='color:{score_color(r['investment_readiness_score'])}; "
                               f"font-weight:700;'>{r['investment_readiness_score']}</span>",
                               unsafe_allow_html=True)
            col_risk.markdown(f"Risk: {r['risk_score']}")
            col_comp.markdown(competition_badge(r["competition_level"]), unsafe_allow_html=True)
            col_gap.markdown(f"Gap: {r['supply_gap']}")
            st.markdown("<hr style='margin:0.25rem 0; border-color:#f1f5f9;'>", unsafe_allow_html=True)
    else:
        empty_state("--", "No recommended categories", "All categories fall below the readiness threshold for this zone.")

    if not_rec:
        with st.expander(f"Not recommended ({len(not_rec)})"):
            for r in not_rec:
                reason = "high risk" if r["risk_score"] >= 65 else "low readiness"
                st.markdown(f"- **{r['category']}** — Score {r['investment_readiness_score']}, "
                            f"Risk {r['risk_score']}, {r['competition_level']} ({reason})")


# ═══════════════════════════════════════════════════════════════════════════
# Page 6 — Zone Comparison
# ═══════════════════════════════════════════════════════════════════════════

def page_zone_comparison():
    page_header("Zone Comparison", "Side-by-side district analysis")
    areas = load_area_indicators()
    spec = load_specialty_supply()
    if areas.empty:
        no_data_warning(); return

    selected = st.multiselect("Select 2-3 zones to compare", get_zone_names(areas), max_selections=3)
    if len(selected) < 2:
        empty_state("--", "Select at least 2 zones", "Choose districts from the dropdown above to compare them.")
        return

    subset = areas[areas["area_name"].isin(selected)].set_index("area_name")
    metrics = {
        "Population": "population_est", "Density (/km²)": "population_density",
        "Facilities": "medical_facilities_count", "Per 100k": "facilities_per_100k",
        "Pharmacies": "pharmacy_count", "Clinics": "clinic_count",
        "Labs": "laboratory_count", "Nearest Hospital (km)": "nearest_hospital_km",
        "Supply Gap": "undersupply_index", "Readiness Score": "investment_score",
        "Purchasing Power": "purchasing_power_proxy",
    }

    rows = []
    for label, col in metrics.items():
        if col not in subset.columns:
            continue
        row = {"Metric": label}
        for z in selected:
            v = subset.loc[z, col] if z in subset.index else "-"
            row[z] = f"{v:,.1f}" if isinstance(v, float) else f"{int(v):,}" if isinstance(v, (int, np.integer)) else str(v)
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    with left:
        section_header("Best Category per Zone")
        for z in selected:
            top = next((r for r in best_categories_for_zone(z, areas, spec) if r["recommended"]), None)
            if top:
                st.markdown(f"**{z}:** {top['category']} "
                            f"(Score {top['investment_readiness_score']}, Risk {top['risk_score']})")
            else:
                st.markdown(f"**{z}:** No strong recommendation")

    with right:
        radar_cols = [c for c in ["demand_index", "undersupply_index", "accessibility_index",
                                   "low_competition_index", "investment_score"]
                      if c in subset.columns]
        if radar_cols:
            fig = go.Figure()
            colors = ["#2563eb", "#059669", "#ea580c"]
            for i, z in enumerate(selected):
                vals = [subset.loc[z, c] for c in radar_cols] + [subset.loc[z, radar_cols[0]]]
                fig.add_trace(go.Scatterpolar(
                    r=vals, theta=radar_cols + [radar_cols[0]],
                    fill="toself", name=z,
                    line=dict(color=colors[i % len(colors)]),
                ))
            fig.update_layout(**PLOTLY_LAYOUT, polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                              title="Zone Profile", height=380)
            st.plotly_chart(fig, use_container_width=True)

    if "investment_score" in subset.columns:
        section_header("Insights")
        by_score = subset["investment_score"].sort_values(ascending=False)
        st.markdown(f"- **Best readiness:** {by_score.index[0]} ({by_score.iloc[0]:.1f})")
        if "medical_facilities_count" in subset.columns:
            by_fac = subset["medical_facilities_count"].sort_values()
            st.markdown(f"- **Lowest competition:** {by_fac.index[0]} ({int(by_fac.iloc[0])} facilities)")
        if "undersupply_index" in subset.columns:
            by_gap = subset["undersupply_index"].sort_values(ascending=False)
            st.markdown(f"- **Largest supply gap:** {by_gap.index[0]} ({by_gap.iloc[0]:.1f})")


# ═══════════════════════════════════════════════════════════════════════════
# Page 7 — Facility Database
# ═══════════════════════════════════════════════════════════════════════════

def page_facility_database():
    page_header("Facility Database", f"Browse and export facility records")
    fac = load_facilities()
    if fac.empty:
        no_data_warning(); return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        search = st.text_input("Search name", key="db_search", placeholder="e.g. pharmacie")
    with c2:
        cat_filter = st.multiselect("Category", sorted(fac["category"].unique()), key="db_cat")
    with c3:
        zone_filter = st.multiselect("Zone", sorted(fac["district"].unique()), key="db_zone")
    with c4:
        dup_only = st.checkbox("Duplicate suspects only", key="db_dup")

    f = fac.copy()
    if search:
        f = f[f["name"].str.contains(search, case=False, na=False)]
    if cat_filter:
        f = f[f["category"].isin(cat_filter)]
    if zone_filter:
        f = f[f["district"].isin(zone_filter)]
    if dup_only and "is_duplicate_suspect" in f.columns:
        f = f[f["is_duplicate_suspect"] == True]

    info_panel([
        ("Matching", f"{len(f):,} facilities"),
        ("Sources", str(f["source"].nunique()) if "source" in f.columns else "-"),
        ("Avg. Confidence", f"{f['confidence_score'].mean():.2f}" if not f.empty else "-"),
    ])
    st.markdown("")

    display_cols = [c for c in ["name", "category", "district", "sector", "lat", "lon",
                                 "phone", "source", "confidence_score", "is_verified"] if c in f.columns]
    st.dataframe(f[display_cols].head(500), use_container_width=True, hide_index=True)

    csv = f.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("Export CSV", data=csv, file_name="invest_search_facilities.csv", mime="text/csv")

    if not f.empty:
        with st.expander("Facility detail"):
            named = f[f["name"].notna() & (f["name"] != "")]
            if not named.empty:
                sel = st.selectbox("Select", named["name"].head(100).tolist(), key="db_detail")
                detail = named[named["name"] == sel].iloc[0]
                cols_to_show = [c for c in detail.index if pd.notna(detail[c]) and str(detail[c]).strip()]
                for col in cols_to_show:
                    st.markdown(f"**{col}:** {detail[col]}")


# ═══════════════════════════════════════════════════════════════════════════
# Page 8 — Investor Report
# ═══════════════════════════════════════════════════════════════════════════

def page_investor_report():
    page_header("Investor Report", "Generate a professional investment analysis")
    areas = load_area_indicators()
    spec = load_specialty_supply()
    if areas.empty:
        no_data_warning(); return

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        zone = st.selectbox("Zone", get_zone_names(areas), key="rpt_zone")
    with c2:
        inv_type = st.selectbox("Investment category", list(INVESTMENT_CATEGORIES.keys()), key="rpt_inv")
    with c3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        generate = st.button("Generate Report", type="primary", use_container_width=True)

    if generate:
        scores = compute_opportunity_scores(areas, spec, inv_type)
        row = scores[scores["area_name"] == zone]
        if row.empty:
            st.error("Cannot compute scores."); return
        report = generate_investor_report(zone, inv_type, areas, row.iloc[0].to_dict())

        st.markdown("")
        vmap = {"Strong Opportunity": "success", "Moderate Opportunity": "warning", "Limited Opportunity": "danger"}
        st.markdown(
            f"<div style='display:flex; align-items:center; gap:12px; margin-bottom:0.5rem;'>"
            f"<span style='font-size:1.1rem; font-weight:700; color:#0f172a;'>{report['title']}</span>"
            f" {badge(report['verdict'], vmap.get(report['verdict'], 'info'))}"
            f"</div>"
            f"<div style='font-size:0.72rem; color:#94a3b8;'>Generated {report['date']}</div>",
            unsafe_allow_html=True,
        )

        st.markdown("")
        mc = st.columns(5)
        with mc[0]:
            stat_card("Readiness", f"{report['investment_readiness_score']}/100", "",
                      score_color(report['investment_readiness_score']))
        with mc[1]:
            stat_card("Risk", f"{report['risk_score']}/100")
        with mc[2]:
            st.markdown(f"<div style='padding-top:8px;'>{competition_badge(report['competition_level'])}</div>",
                        unsafe_allow_html=True)
        with mc[3]:
            stat_card("Supply Gap", f"{report['supply_gap']}/100")
        with mc[4]:
            stat_card("Population", f"{report['population']:,}")

        st.markdown("")
        left, right = st.columns(2)
        with left:
            section_header("Key Drivers")
            for r in report["reasons"]:
                st.markdown(f"- {r}")
            section_header("Risk Factors")
            for r in report["risks"]:
                st.markdown(f"- {r}")
        with right:
            section_header("Field Validation Checklist")
            for i, item in enumerate(report["checklist"], 1):
                st.checkbox(item, key=f"rpt_chk_{i}")

        section_header("Next Steps")
        for i, item in enumerate(report["next_steps"], 1):
            st.markdown(f"{i}. {item}")

        st.caption("Scores are indicative. Field validation and professional feasibility studies required.")

        pdf = export_report_pdf(report)
        if pdf:
            st.download_button("Download PDF Report", data=pdf,
                               file_name=f"invest_search_{zone.lower().replace(' ', '_')}.pdf",
                               mime="application/pdf")


# ═══════════════════════════════════════════════════════════════════════════
# Page 9 — Data Quality
# ═══════════════════════════════════════════════════════════════════════════

def page_data_quality():
    page_header("Data Quality", "Confidence scores, coverage gaps, and verification status")
    fac = load_facilities()
    if fac.empty:
        no_data_warning(); return

    total = len(fac)
    geo = fac["lat"].notna() & fac["lon"].notna()
    named = fac["name"].notna() & (fac["name"] != "")
    known = fac["district"] != "Unknown"
    low = (fac["confidence_score"] < 0.5).sum()

    r1 = st.columns(4)
    with r1[0]:
        stat_card("Geocoded", f"{geo.sum():,}/{total:,}", f"{geo.mean()*100:.0f}%")
    with r1[1]:
        stat_card("Named", f"{named.sum():,}/{total:,}", f"{named.mean()*100:.0f}%")
    with r1[2]:
        stat_card("District Assigned", f"{known.sum():,}/{total:,}", f"{known.mean()*100:.0f}%")
    with r1[3]:
        stat_card("Low Confidence", f"{low:,}", "score < 0.50", DANGER if low > 50 else WARNING)

    st.markdown("")

    left, right = st.columns(2)
    with left:
        section_header("Missing Values")
        key_cols = ["name", "category", "district", "lat", "lon", "phone", "address", "source"]
        miss = {c: int(fac[c].isna().sum() + (fac[c] == "").sum()) if c in fac.columns else total for c in key_cols}
        mdf = pd.DataFrame({"Column": miss.keys(), "Missing": miss.values()})
        mdf["Coverage"] = ((1 - mdf["Missing"] / total) * 100).round(1).astype(str) + "%"
        st.dataframe(mdf, use_container_width=True, hide_index=True)
    with right:
        section_header("Sources")
        if "source" in fac.columns:
            src = fac["source"].value_counts().reset_index()
            src.columns = ["Source", "Count"]
            fig = px.pie(src, values="Count", names="Source",
                         color_discrete_sequence=["#2563eb", "#059669", "#ea580c", "#7c3aed"])
            fig.update_layout(**PLOTLY_LAYOUT, height=280)
            st.plotly_chart(fig, use_container_width=True)

    section_header("Confidence Distribution")
    fig = px.histogram(fac, x="confidence_score", nbins=20,
                       color_discrete_sequence=["#2563eb"])
    fig.update_layout(**PLOTLY_LAYOUT, height=280)
    st.plotly_chart(fig, use_container_width=True)

    review = fac[(fac["confidence_score"] < 0.5) | (~named) | (fac["district"] == "Unknown")]
    if not review.empty:
        section_header("Flagged for Review", f"{len(review):,} facilities need attention")
        dcols = [c for c in ["id", "name", "category", "district", "lat", "lon",
                              "confidence_score", "source"] if c in review.columns]
        st.dataframe(review[dcols].head(100), use_container_width=True, hide_index=True)

    with st.expander("Improvement recommendations"):
        st.markdown(
            "- Add verified facilities via `data/manual/manual_verified_facilities.csv`\n"
            "- Import official Ministry of Health data when available\n"
            "- Set `GOOGLE_PLACES_API_KEY` in `.env` to enrich ratings and contacts\n"
            "- Run reverse geocoding for facilities with Unknown district\n"
            "- Cross-reference with ANAM provider lists when accessible"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Page 10 — Chatbot Assistant
# ═══════════════════════════════════════════════════════════════════════════

def page_chatbot():
    page_header("Chatbot Assistant", "Ask questions about investment opportunities")

    fac = load_facilities()
    areas = load_area_indicators()

    sidebar_col, chat_col = st.columns([1, 3])

    with sidebar_col:
        card_container(
            f"<div style='font-size:0.7rem; text-transform:uppercase; color:#94a3b8; "
            f"letter-spacing:0.05em; font-weight:600; margin-bottom:8px;'>Session Info</div>"
            f"<div style='font-size:0.78rem; color:#475569; line-height:1.8;'>"
            f"<b>Mode:</b> {get_mode_label()}<br>"
            f"<b>Facilities:</b> {len(fac):,}<br>"
            f"<b>Districts:</b> {len(areas)}<br>"
            f"<b>Confidence:</b> {fac['confidence_score'].mean()*100:.0f}% avg<br>"
            f"<b>Source:</b> OSM + Official"
            f"</div>",
            padding="14px 16px",
        )

        st.markdown("")
        st.markdown("<div style='font-size:0.7rem; text-transform:uppercase; color:#94a3b8; "
                    "letter-spacing:0.05em; font-weight:600; margin-bottom:6px;'>Quick Prompts</div>",
                    unsafe_allow_html=True)

        quick = [
            ("Where to open a pharmacy?", "qp_0"),
            ("Compare Maarif vs Ain Chock", "qp_1"),
            ("Low-competition zones", "qp_2"),
            ("Investor summary: Sidi Moumen", "qp_3"),
            ("Data quality report", "qp_4"),
        ]
        for prompt_text, key in quick:
            if st.button(prompt_text, key=key, use_container_width=True):
                if "chat_history" not in st.session_state:
                    st.session_state.chat_history = []
                st.session_state.chat_history.append({"role": "user", "content": prompt_text})
                resp = chatbot_process(prompt_text)
                st.session_state.chat_history.append({"role": "assistant", "content": resp})
                st.rerun()

    with chat_col:
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        if not st.session_state.chat_history:
            st.markdown(
                "<div style='text-align:center; padding:3rem 1rem; color:#94a3b8;'>"
                "<div style='font-size:1.5rem; margin-bottom:0.5rem;'>IS</div>"
                "<div style='font-size:0.88rem; font-weight:500; color:#64748b;'>"
                "Invest Search Assistant</div>"
                "<div style='font-size:0.78rem; margin-top:0.25rem;'>"
                "Ask about zones, competition, opportunities, or data quality.</div>"
                "</div>",
                unsafe_allow_html=True,
            )

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"], avatar="IS" if msg["role"] == "assistant" else None):
                st.markdown(msg["content"])

        user_input = st.chat_input("Ask about medical investment in Casablanca...")
        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)
            resp = chatbot_process(user_input)
            st.session_state.chat_history.append({"role": "assistant", "content": resp})
            with st.chat_message("assistant", avatar="IS"):
                st.markdown(resp)

        if st.session_state.chat_history:
            export = "\n\n".join(f"**{m['role'].upper()}:** {m['content']}" for m in st.session_state.chat_history)
            st.download_button("Export chat", data=export,
                               file_name="invest_search_chat.md", mime="text/markdown")


# ═══════════════════════════════════════════════════════════════════════════
# Page 11 — Settings
# ═══════════════════════════════════════════════════════════════════════════

def page_settings():
    page_header("Settings", "Data sources, configuration, and pipeline status")

    import os
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from data_sources import google_places_optional, manual_import

    section_header("Data Sources")
    sources = [
        {"Source": "OpenStreetMap / Overpass", "Type": "Public API", "Status": "Active",
         "Confidence": "0.65-0.80", "Records": len(load_facilities())},
        {"Source": "Ministry of Health", "Type": "Official", "Status": "Manual",
         "Confidence": "0.90-1.00", "Records": "-"},
        {"Source": "Casa-Stat / E-Data", "Type": "Institutional", "Status": "Manual",
         "Confidence": "0.80-0.90", "Records": "-"},
        {"Source": "HCP Demographics", "Type": "Official", "Status": "Manual",
         "Confidence": "0.90-1.00", "Records": "-"},
        {"Source": "Google Places API", "Type": "Commercial",
         "Status": "Active" if google_places_optional.is_available() else "Not configured",
         "Confidence": "0.70-0.85", "Records": "-"},
    ]
    st.dataframe(pd.DataFrame(sources), use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    with left:
        section_header("Manual Data Files")
        available = manual_import.list_available()
        for fname, exists in available.items():
            status = badge("Found", "success") if exists else badge("Missing", "neutral")
            st.markdown(f"{status} `{fname}`", unsafe_allow_html=True)

    with right:
        section_header("LLM Configuration")
        provider = os.environ.get("LLM_PROVIDER", "none")
        has_key = bool(os.environ.get("LLM_API_KEY", "").strip())
        if provider != "none" and has_key:
            st.markdown(f"{badge('Connected', 'success')} Provider: **{provider}**", unsafe_allow_html=True)
        else:
            st.markdown(f"{badge('Local mode', 'neutral')} Set `LLM_PROVIDER` and `LLM_API_KEY` in `.env` to enable.",
                        unsafe_allow_html=True)

    section_header("Refresh Pipeline")
    st.code(
        "python scripts/01_collect_osm.py\n"
        "python scripts/02_collect_official_sources.py\n"
        "python scripts/03_clean_normalize.py\n"
        "python scripts/05_compute_scores.py\n"
        "python scripts/06_export_geojson.py",
        language="bash",
    )
    st.caption("After running, reload the dashboard to see updated data.")


# ═══════════════════════════════════════════════════════════════════════════
# Navigation
# ═══════════════════════════════════════════════════════════════════════════

PAGE_CONFIG = {
    "Executive Overview": ("overview", page_executive_overview),
    "Market Map": ("map", page_market_map),
    "Opportunity Finder": ("opportunity", page_opportunity_finder),
    "Competition Radar": ("competition", page_competition_radar),
    "Best Location": ("location", page_best_location),
    "Zone Comparison": ("comparison", page_zone_comparison),
    "Facility Database": ("database", page_facility_database),
    "Investor Report": ("report", page_investor_report),
    "Data Quality": ("quality", page_data_quality),
    "Chatbot": ("chatbot", page_chatbot),
    "Settings": ("settings", page_settings),
}


def main():
    render_sidebar()

    with st.sidebar:
        selection = st.radio("", list(PAGE_CONFIG.keys()), label_visibility="collapsed")

    render_footer()
    _, page_fn = PAGE_CONFIG[selection]
    page_fn()


if __name__ == "__main__":
    main()
