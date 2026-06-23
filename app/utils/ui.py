"""UI design system: CSS, metric cards, badges, section containers, sidebar branding."""

import pandas as pd
import streamlit as st

# --- Design tokens ---
PRIMARY = "#0f172a"
PRIMARY_600 = "#1e3a5f"
ACCENT = "#2563eb"
ACCENT_LIGHT = "#3b82f6"
SUCCESS = "#059669"
WARNING = "#d97706"
DANGER = "#dc2626"
SURFACE = "#ffffff"
SURFACE_ALT = "#f8fafc"
BORDER = "#e2e8f0"
BORDER_LIGHT = "#f1f5f9"
TEXT = "#0f172a"
TEXT_SECONDARY = "#64748b"
TEXT_MUTED = "#94a3b8"
RADIUS = "6px"
RADIUS_LG = "10px"

GLOBAL_CSS = """
<style>
/* ── Reset & base ────────────────────────────────────── */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    max-width: 1200px;
}
[data-testid="stAppViewContainer"] {
    background: #f8fafc;
}

/* ── Sidebar ─────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #0f172a;
    border-right: 1px solid #1e293b;
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 0.5rem;
}
[data-testid="stSidebar"] * {
    color: #cbd5e1 !important;
}
[data-testid="stSidebar"] hr {
    border-color: #1e293b !important;
    margin: 0.4rem 0 !important;
}
[data-testid="stSidebar"] .stRadio > div {
    gap: 0 !important;
}
[data-testid="stSidebar"] .stRadio label {
    font-size: 0.82rem !important;
    padding: 0.35rem 0.8rem !important;
    margin: 0 !important;
    border-radius: 5px;
    transition: all 0.15s ease;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(59, 130, 246, 0.1) !important;
    color: #93c5fd !important;
}
[data-testid="stSidebar"] .stRadio label[data-checked="true"],
[data-testid="stSidebar"] .stRadio [data-baseweb="radio"] input:checked ~ div {
    color: #60a5fa !important;
}

/* ── Typography ──────────────────────────────────────── */
h1 {
    color: #0f172a !important;
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    margin-bottom: 0.25rem !important;
    line-height: 1.3 !important;
}
h2 {
    color: #1e293b !important;
    font-size: 1.1rem !important;
    font-weight: 600 !important;
    margin-bottom: 0.25rem !important;
}
h3 {
    color: #334155 !important;
    font-size: 0.95rem !important;
    font-weight: 600 !important;
}

/* ── Metric cards ────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 12px 16px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
[data-testid="stMetric"] label {
    color: #64748b !important;
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: #0f172a !important;
    font-weight: 700 !important;
    font-size: 1.25rem !important;
}
[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    font-size: 0.75rem !important;
}

/* ── Dataframes ──────────────────────────────────────── */
.stDataFrame {
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #e2e8f0;
}
[data-testid="stDataFrame"] > div {
    border-radius: 8px;
}

/* ── Buttons ─────────────────────────────────────────── */
.stButton > button {
    border-radius: 6px !important;
    font-weight: 500 !important;
    font-size: 0.82rem !important;
    padding: 0.35rem 1rem !important;
    border: 1px solid #e2e8f0 !important;
    transition: all 0.15s ease;
}
.stButton > button:hover {
    border-color: #cbd5e1 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.stButton > button[kind="primary"] {
    background: #2563eb !important;
    color: white !important;
    border-color: #2563eb !important;
}
.stButton > button[kind="primary"]:hover {
    background: #1d4ed8 !important;
}

/* ── Expanders ───────────────────────────────────────── */
.streamlit-expanderHeader {
    font-weight: 600;
    font-size: 0.88rem;
    color: #334155;
    background: #f8fafc;
    border-radius: 6px;
}

/* ── Selectboxes, inputs ─────────────────────────────── */
[data-baseweb="select"],
[data-baseweb="input"] {
    border-radius: 6px !important;
}
.stSelectbox label,
.stMultiSelect label,
.stSlider label,
.stTextInput label {
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    color: #475569 !important;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}

/* ── Tabs ────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 1px solid #e2e8f0;
}
.stTabs [data-baseweb="tab"] {
    font-size: 0.82rem;
    font-weight: 500;
    padding: 0.5rem 1rem;
}

/* ── Chat messages ───────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.5rem;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03);
}
[data-testid="stChatMessage"][data-testid*="user"] {
    background: #f0f9ff;
    border-color: #bae6fd;
}

/* ── Download buttons ────────────────────────────────── */
.stDownloadButton > button {
    border-radius: 6px !important;
    font-size: 0.8rem !important;
    border: 1px solid #e2e8f0 !important;
    background: white !important;
}

/* ── Dividers ────────────────────────────────────────── */
hr {
    border-color: #e2e8f0 !important;
    margin: 0.75rem 0 !important;
}

/* ── Chat input ──────────────────────────────────────── */
[data-testid="stChatInput"] {
    border-color: #e2e8f0 !important;
    border-radius: 10px !important;
}
[data-testid="stChatInput"] textarea {
    font-size: 0.88rem !important;
}

/* ── Info/warning/success boxes ──────────────────────── */
[data-testid="stAlert"] {
    border-radius: 8px;
    font-size: 0.85rem;
    padding: 0.6rem 1rem;
}

/* ── Checkboxes ──────────────────────────────────────── */
.stCheckbox label {
    font-size: 0.85rem !important;
}

/* ── Captions ────────────────────────────────────────── */
.stCaption, [data-testid="stCaption"] {
    font-size: 0.75rem !important;
    color: #94a3b8 !important;
}

/* ── Blockquotes ─────────────────────────────────────── */
blockquote {
    border-left: 3px solid #2563eb !important;
    background: #f0f9ff !important;
    padding: 0.6rem 1rem !important;
    border-radius: 0 6px 6px 0 !important;
    margin: 0.5rem 0 !important;
    font-size: 0.88rem !important;
    color: #1e293b !important;
}
</style>
"""


def inject_css():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def render_sidebar():
    with st.sidebar:
        st.markdown(
            "<div style='text-align:center; padding: 0.6rem 0 0.15rem 0;'>"
            "<span style='font-size:1.15rem; font-weight:700; color:#60a5fa; "
            "letter-spacing:0.06em;'>INVEST</span>"
            "<span style='font-size:1.15rem; font-weight:300; color:#94a3b8; "
            "letter-spacing:0.02em;'> SEARCH</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='text-align:center; font-size:0.65rem; color:#64748b; "
            "margin-top:-0.3rem; letter-spacing:0.05em; text-transform:uppercase;'>"
            "Medical Market Intelligence</p>",
            unsafe_allow_html=True,
        )
        st.markdown("---")


def render_footer():
    with st.sidebar:
        st.markdown("---")
        st.markdown(
            "<p style='font-size:0.62rem; color:#475569; text-align:center; "
            "line-height:1.4;'>"
            "Data: OSM + Official sources<br/>"
            "Invest Search 2026</p>",
            unsafe_allow_html=True,
        )


def page_header(title: str, subtitle: str = ""):
    st.markdown(
        f"<h1 style='margin-bottom:0.1rem'>{title}</h1>",
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(
            f"<p style='color:#64748b; font-size:0.82rem; margin-top:0; "
            f"margin-bottom:0.75rem;'>{subtitle}</p>",
            unsafe_allow_html=True,
        )


def section_header(title: str, subtitle: str = ""):
    st.markdown(
        f"<div style='margin: 0.75rem 0 0.4rem 0;'>"
        f"<h2 style='margin:0; padding:0;'>{title}</h2>"
        + (f"<p style='color:#94a3b8; font-size:0.75rem; margin:0;'>{subtitle}</p>" if subtitle else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def card_container(content_html: str, padding: str = "1rem"):
    st.markdown(
        f"<div style='background:#fff; border:1px solid #e2e8f0; border-radius:8px; "
        f"padding:{padding}; margin-bottom:0.5rem; "
        f"box-shadow:0 1px 2px rgba(0,0,0,0.04);'>{content_html}</div>",
        unsafe_allow_html=True,
    )


def stat_card(label: str, value: str, subtitle: str = "", accent: str = ACCENT):
    st.markdown(
        f"<div style='background:#fff; border:1px solid #e2e8f0; border-radius:8px; "
        f"padding:14px 16px; box-shadow:0 1px 2px rgba(0,0,0,0.04);'>"
        f"<div style='font-size:0.68rem; font-weight:500; color:#64748b; "
        f"text-transform:uppercase; letter-spacing:0.04em; margin-bottom:4px;'>{label}</div>"
        f"<div style='font-size:1.3rem; font-weight:700; color:{accent}; "
        f"line-height:1.2;'>{value}</div>"
        + (f"<div style='font-size:0.7rem; color:#94a3b8; margin-top:2px;'>{subtitle}</div>" if subtitle else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def badge(text: str, level: str = "info") -> str:
    colors = {
        "success": ("#dcfce7", "#166534"),
        "warning": ("#fef3c7", "#92400e"),
        "danger": ("#fee2e2", "#991b1b"),
        "info": ("#dbeafe", "#1e40af"),
        "neutral": ("#f1f5f9", "#475569"),
    }
    bg, fg = colors.get(level, colors["info"])
    return (
        f"<span style='background:{bg}; color:{fg}; padding:2px 8px; "
        f"border-radius:4px; font-size:0.72rem; font-weight:600; "
        f"letter-spacing:0.02em;'>{text}</span>"
    )


def competition_badge(level: str) -> str:
    mapping = {"Low": "success", "Medium": "warning", "High": "danger", "Saturated": "danger"}
    return badge(level, mapping.get(level, "neutral"))


def score_color(score: float) -> str:
    if score >= 70:
        return SUCCESS
    if score >= 50:
        return WARNING
    return DANGER


def styled_dataframe(df: pd.DataFrame, score_col: str | None = None):
    if df.empty:
        st.info("No data to display.")
        return
    if score_col and score_col in df.columns:
        try:
            st.dataframe(
                df.style.background_gradient(subset=[score_col], cmap="RdYlGn"),
                use_container_width=True,
                hide_index=True,
            )
            return
        except (ImportError, ValueError):
            pass
    st.dataframe(df, use_container_width=True, hide_index=True)


def no_data_warning(context: str = ""):
    msg = "No data available."
    if context:
        msg += f" {context}"
    msg += " Run the data pipeline first: `01_collect_osm.py` through `05_compute_scores.py`."
    st.warning(msg)


def empty_state(icon: str, title: str, description: str = ""):
    st.markdown(
        f"<div style='text-align:center; padding:2rem 1rem; color:#94a3b8;'>"
        f"<div style='font-size:2rem; margin-bottom:0.5rem;'>{icon}</div>"
        f"<div style='font-size:0.95rem; font-weight:600; color:#64748b;'>{title}</div>"
        + (f"<div style='font-size:0.8rem; margin-top:0.25rem;'>{description}</div>" if description else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def chip(text: str, active: bool = False) -> str:
    if active:
        bg, fg, border = "#dbeafe", "#1e40af", "#93c5fd"
    else:
        bg, fg, border = "#f8fafc", "#475569", "#e2e8f0"
    return (
        f"<span style='display:inline-block; background:{bg}; color:{fg}; "
        f"border:1px solid {border}; padding:4px 12px; border-radius:16px; "
        f"font-size:0.75rem; font-weight:500; cursor:pointer; "
        f"transition:all 0.15s ease;'>{text}</span>"
    )


def info_panel(items: list[tuple[str, str]]):
    html = "<div style='display:flex; flex-wrap:wrap; gap:10px;'>"
    for label, value in items:
        html += (
            f"<div style='background:#f8fafc; border:1px solid #e2e8f0; "
            f"border-radius:6px; padding:6px 12px; font-size:0.75rem;'>"
            f"<span style='color:#94a3b8;'>{label}:</span> "
            f"<span style='color:#0f172a; font-weight:600;'>{value}</span></div>"
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)
