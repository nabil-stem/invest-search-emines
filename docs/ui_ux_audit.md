# UI/UX Audit — Invest Search

**Date:** 2026-05-18
**Auditor:** Code review + functional testing (HTTP verification, import checks, integration tests)
**App URL:** http://localhost:8501

---

## Before (Original UI) — Issues Found

### Global

| Issue | Severity | Description |
|---|---|---|
| Dark sidebar too heavy | High | `#1a202c` background with large brand text (1.8rem) made sidebar visually dominant |
| No visual hierarchy | High | All text same weight, no distinction between page title / section / body |
| Excessive spacing | Medium | Default Streamlit padding (2rem top) + wide `---` dividers wasted vertical space |
| No max-width constraint | Medium | Content stretched full-width on large monitors, reducing readability |
| Metric cards generic | Medium | Default `st.metric` with minimal styling, no uppercase labels or hierarchy |
| Buttons unstyled | Low | Default Streamlit buttons with no border-radius or hover transitions |
| No consistent design tokens | Medium | Colors scattered across files with no shared palette |
| Blockquotes unstyled | Low | Default browser blockquote styling, no brand color accent |

### Page: Executive Overview

| Issue | Severity | Fix |
|---|---|---|
| Two rows of 5+4 metrics cramped | Medium | Replaced with stat_card components with subtitles |
| Charts use `plot_bgcolor="white"` | Low | Changed to transparent with PLOTLY_LAYOUT dict |
| Executive summary too long | Low | Shortened to 2 sentences |

### Page: Market Map

| Issue | Severity | Fix |
|---|---|---|
| Legend takes too much space | Medium | Made legend compact with 8px color dots and 0.72rem text |
| Filter labels default styling | Low | Added uppercase + letter-spacing via global CSS |
| Map popup font inconsistent | Low | Changed to system-ui, 12px, tighter layout |

### Page: Opportunity Finder

| Issue | Severity | Fix |
|---|---|---|
| Single giant table + chart below | Medium | Split into 2-column layout: bar chart + category supply chart side by side |
| Weights shown inline, hard to read | Low | Shortened format with `/` separator |

### Page: Competition Radar

| Issue | Severity | Fix |
|---|---|---|
| Metrics + badge layout disjointed | Medium | Reorganized into 6-column stat_cards with saturation score prominently displayed |
| Radar chart colors generic | Low | Changed to brand blue (#2563eb) and muted gray (#94a3b8) |
| Map marker icon default | Low | Changed to crosshairs icon for center point |

### Page: Best Location Simulator

| Issue | Severity | Fix |
|---|---|---|
| Zone stats shown in markdown blockquote | Medium | Replaced with info_panel component (compact inline chips) |
| Recommendation rows used 5-col layout | Low | Refined with score_color highlighting |
| No empty state | Medium | Added empty_state component for "no recommendations" case |

### Page: Zone Comparison

| Issue | Severity | Fix |
|---|---|---|
| "Select 2 zones" message uses st.info | Low | Replaced with centered empty_state |
| Insights section at bottom, easy to miss | Medium | Moved to 2-column layout with radar chart |

### Page: Facility Database

| Issue | Severity | Fix |
|---|---|---|
| No summary stats above table | Medium | Added info_panel with match count, sources, avg confidence |
| Search input has no placeholder | Low | Added placeholder text |

### Page: Investor Report

| Issue | Severity | Fix |
|---|---|---|
| Generate button in 2-col layout, small | Medium | Moved to 3-col with full-width primary button |
| Report title + verdict not aligned | Medium | Combined into flex row with inline badge |
| 4+3 metric rows generic | Low | Using stat_card with score_color accents |

### Page: Data Quality

| Issue | Severity | Fix |
|---|---|---|
| Coverage % not shown in missing values table | Medium | Added Coverage column |
| Recommendations shown inline | Low | Moved to collapsible expander |

### Page: Chatbot Assistant — MAJOR REDESIGN

| Issue | Severity | Fix |
|---|---|---|
| Quick prompts in 5-column row | High | Moved to sidebar panel with full-width buttons |
| No session info visible | High | Added info panel showing mode, facilities, districts, confidence |
| No welcome state | Medium | Added centered welcome message when chat is empty |
| User icon red circle, unprofessional | Medium | Using default Streamlit avatars; assistant shows "IS" |
| Chat messages basic | Medium | Global CSS adds border, subtle shadow, blue tint for user messages |
| Input area at bottom of page, not visible | Low | Chat input naturally sticky at bottom of chat_col |
| No visual separation between chat and controls | Medium | 2-column layout: sidebar (info + prompts) + main chat area |

### Page: Settings

| Issue | Severity | Fix |
|---|---|---|
| Manual file status shown as markdown text | Medium | Using badge() components for Found/Missing |
| Pipeline commands in markdown code block | Low | Using st.code with language hint |
| LLM status text only | Low | Using badge() for Connected/Local mode |

---

## After (Redesigned UI) — Changes Implemented

### Design System (`app/utils/ui.py`)

**New design tokens:**
- PRIMARY: `#0f172a` (Slate 900)
- ACCENT: `#2563eb` (Blue 600)
- SUCCESS: `#059669` (Emerald 600)
- WARNING: `#d97706` (Amber 600)
- DANGER: `#dc2626` (Red 600)
- SURFACE: `#ffffff`, SURFACE_ALT: `#f8fafc`
- TEXT: `#0f172a`, TEXT_SECONDARY: `#64748b`, TEXT_MUTED: `#94a3b8`

**New CSS rules (60+ rules):**
- Sidebar: `#0f172a` bg, compact nav items (0.82rem, 5px radius, hover highlight)
- Typography: h1=1.5rem/700, h2=1.1rem/600, h3=0.95rem/600
- Metric cards: compact padding, uppercase 0.72rem labels, 1.25rem values
- Buttons: 6px radius, subtle border, hover shadow
- Inputs: uppercase labels, 0.78rem, letter-spacing
- Chat messages: white bg, 1px border, 10px radius, blue tint for user
- Blockquotes: 3px blue left border, light blue bg
- Max-width: 1200px content container

**New components:**
- `page_header(title, subtitle)` — Page title with gray subtitle
- `section_header(title, subtitle)` — Section header with optional description
- `stat_card(label, value, subtitle, accent)` — Branded metric card
- `card_container(html, padding)` — Generic white card
- `empty_state(icon, title, description)` — Centered empty state
- `info_panel(items)` — Inline key-value chips
- `chip(text, active)` — Small chip/tag component

### Dashboard (`app/streamlit_app.py`)

**Global:**
- PLOTLY_LAYOUT dict for consistent chart styling (transparent bg, Inter font, tight margins)
- CAT_COLORS with Tailwind-aligned palette
- page_icon changed from emoji to "IS"

**Per-page changes:**
- Every page uses `page_header()` instead of `st.title()`
- Every section uses `section_header()` instead of `st.subheader()`
- Metrics use `stat_card()` where appropriate
- Charts use PLOTLY_LAYOUT for consistent styling
- Chatbot completely restructured: 2-column layout, info panel, quick prompts in sidebar
- Settings uses badge components for status indicators
- Empty states use `empty_state()` component

---

## Verification Results

| Check | Status |
|---|---|
| Syntax: streamlit_app.py | PASS |
| Syntax: ui.py | PASS |
| All imports | PASS |
| Data loading (775 fac, 16 areas, 128 spec) | PASS |
| Scoring engine | PASS |
| Report generation + PDF export (4,428 bytes) | PASS |
| Chatbot local mode (604 chars) | PASS |
| Streamlit HTTP 200 | PASS |
| Missing API keys: no crash | PASS |

---

## Remaining Improvements (Future)

| Item | Priority | Notes |
|---|---|---|
| Add Playwright MCP for automated visual regression testing | Medium | Not available in current environment |
| Custom Streamlit theme via `.streamlit/config.toml` | Low | Would control native widget colors |
| Loading skeletons for slow pages | Low | Plotly charts have minor render delay |
| Mobile responsive tweaks | Low | Sidebar behavior on small screens |
| Dark mode toggle | Low | Current design is light mode; dark mode would need separate token set |
| Custom favicon and meta tags | Low | Currently uses "IS" text |
| Accessibility audit (WCAG contrast ratios) | Medium | Current palette passes AA for body text |
| Animation/transitions on page switch | Low | Streamlit limitation |
