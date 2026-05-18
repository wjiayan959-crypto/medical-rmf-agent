import pandas as pd
import streamlit as st

from database import (
    init_db,
    create_rmf_version,
    get_all_rmf_versions,
    delete_rmf_version,
    clone_rmf_version,
    save_risk_records,
    get_risk_records_by_rmf,
    update_risk_records,
    save_rmp_config,
    get_latest_rmp_config,
    rmp_config_exists,
)
from utils import validate_device_input
from llm_stages import generate_followup_questions, generate_rmf_from_answers


st.set_page_config(
    page_title="Medical RMF Agent",
    page_icon="🏥",
    layout="wide",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Metric cards */
[data-testid="stMetric"] {
    background: #f8fafc;
    border: 1px solid #dde3ec;
    border-radius: 10px;
    padding: 18px 22px 14px 22px;
}
[data-testid="stMetricLabel"] > div {
    color: #566070;
    font-size: 0.80rem;
    font-weight: 500;
}
[data-testid="stMetricValue"] > div {
    color: #1a3a5c;
    font-weight: 700;
}

/* Expander cards */
[data-testid="stExpander"] {
    border: 1px solid #dde3ec;
    border-radius: 8px;
    margin-bottom: 10px;
}

/* Dividers */
hr { border-color: #eaeef3 !important; margin: 20px 0 !important; }

/* ── Sidebar chrome ── */
[data-testid="stSidebarContent"] { padding-top: 1.0rem; }

/* Tighten the gap between radio options */
[data-testid="stSidebar"] div[role="radiogroup"] { gap: 2px; }

/* Give each nav option a pill-shaped hover target */
[data-testid="stSidebar"] div[role="radiogroup"] > label {
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 0.88rem;
    transition: background 0.12s;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────
_WIZARD_KEYS = [
    "step", "rmf_id", "device_name", "intended_use", "device_type",
    "questions", "followup_qa", "generated_df",
    "generated_raw_response", "generated_rag_context",
]

_DEFAULTS = {
    "step": 1,
    "rmf_id": None,
    "device_name": "",
    "intended_use": "",
    "device_type": "",
    "questions": [],
    "followup_qa": [],
    "generated_df": None,
    "generated_raw_response": None,
    "generated_rag_context": None,
    "hist_edit_source_id": None,
    "hist_edit_df": None,
    "hist_edit_counter": 0,
}

for _key, _val in _DEFAULTS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _val

# ── RMP constants ──────────────────────────────────────────────────────────────
_RMP_SEVERITY_LEVELS = ["Negligible", "Minor", "Serious", "Critical", "Catastrophic"]
_RMP_PROBABILITY_LEVELS = ["Frequent", "Probable", "Occasional", "Remote", "Improbable"]
_RMP_DEFAULT_MATRIX = {
    "Frequent":   {"Negligible": "MEDIUM", "Minor": "MEDIUM", "Serious": "HIGH",   "Critical": "HIGH",   "Catastrophic": "HIGH"},
    "Probable":   {"Negligible": "LOW",    "Minor": "MEDIUM", "Serious": "MEDIUM", "Critical": "HIGH",   "Catastrophic": "HIGH"},
    "Occasional": {"Negligible": "LOW",    "Minor": "LOW",    "Serious": "MEDIUM", "Critical": "MEDIUM", "Catastrophic": "HIGH"},
    "Remote":     {"Negligible": "LOW",    "Minor": "LOW",    "Serious": "LOW",    "Critical": "MEDIUM", "Catastrophic": "HIGH"},
    "Improbable": {"Negligible": "LOW",    "Minor": "LOW",    "Serious": "LOW",    "Critical": "LOW",    "Catastrophic": "MEDIUM"},
}
_RMP_CELL_COLORS = {"LOW": "#c6efce", "MEDIUM": "#ffeb9c", "HIGH": "#ffc7ce"}


def _style_risk_cell(val):
    bg = _RMP_CELL_COLORS.get(val, "#ffffff")
    return f"background-color: {bg}; color: #000000; font-weight: bold;"


def _step_bar(current: int) -> None:
    """Render a 3-step horizontal progress indicator above the wizard form."""
    labels = ["Device Info", "Follow-up Q&A", "RMF Draft"]
    cols = st.columns([4, 1, 4, 1, 4])
    for i, label in enumerate(labels):
        with cols[i * 2]:
            if current > i + 1:
                bg, border, color, prefix = "#ebf7f0", "#27ae60", "#1e8449", "✓ "
            elif current == i + 1:
                bg, border, color, prefix = "#eaf1fb", "#1a3a5c", "#1a3a5c", f"{i + 1}. "
            else:
                bg, border, color, prefix = "#f8fafc", "#dde3ec", "#95a5a6", f"{i + 1}. "
            weight = "700" if current == i + 1 else "500"
            st.markdown(
                f'<div style="text-align:center;padding:10px 6px;background:{bg};'
                f'border:2px solid {border};border-radius:8px;color:{color};'
                f'font-weight:{weight};font-size:0.88rem;">{prefix}{label}</div>',
                unsafe_allow_html=True,
            )
    for idx in [1, 3]:
        with cols[idx]:
            st.markdown(
                '<div style="text-align:center;font-size:1.2rem;padding-top:10px;'
                'color:#bdc3c7;">→</div>',
                unsafe_allow_html=True,
            )


def _dash_stat_card(icon: str, label: str, value: str, accent: str = "#3b82f6", helper: str = "") -> str:
    """Return an HTML premium metric card: icon box left, value+label right."""
    _h = (
        f'<div style="margin-top:5px;font-size:0.67rem;color:#334155;">{helper}</div>'
        if helper else ""
    )
    return (
        f'<div style="position:relative;overflow:hidden;'
        f'background:linear-gradient(145deg,#0f1724 0%,#141e2e 100%);'
        f'border:1px solid #1a2840;border-radius:16px;padding:18px;'
        f'box-shadow:0 4px 20px rgba(0,0,0,0.35);display:flex;align-items:center;gap:14px;">'
        f'<div style="position:absolute;top:0;left:0;right:0;height:2px;'
        f'background:linear-gradient(90deg,{accent}cc,{accent}22);"></div>'
        f'<div style="width:46px;height:46px;border-radius:12px;flex-shrink:0;'
        f'background:{accent}18;border:1px solid {accent}30;'
        f'display:flex;align-items:center;justify-content:center;font-size:1.25rem;">'
        f'{icon}</div>'
        f'<div style="flex:1;min-width:0;">'
        f'<div style="font-size:1.7rem;font-weight:800;color:#f1f5f9;line-height:1;'
        f'letter-spacing:-0.02em;">{value}</div>'
        f'<div style="margin-top:5px;font-size:0.68rem;font-weight:700;color:#64748b;'
        f'letter-spacing:0.06em;text-transform:uppercase;">{label}</div>'
        f'{_h}'
        f'</div>'
        f'</div>'
    )


init_db()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:

    # Brand block — logo icon + title
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;padding:2px 2px 12px;">'
        '<div style="width:34px;height:34px;border-radius:9px;flex-shrink:0;'
        'background:linear-gradient(135deg,#3b82f6,#8b5cf6);'
        'display:flex;align-items:center;justify-content:center;font-size:0.95rem;">🏥</div>'
        '<div>'
        '<div style="font-size:0.93rem;font-weight:700;letter-spacing:0.01em;line-height:1.3;">'
        'Medical RMF Agent</div>'
        '<div style="font-size:0.68rem;color:#8a9ab0;margin-top:2px;">ISO 14971 · Risk Management</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # RMP status pill — compact, colour-coded, dark-mode safe
    if rmp_config_exists():
        st.markdown(
            '<span style="'
            "background:rgba(39,174,96,0.13);color:#1a7a40;"
            "border:1px solid rgba(39,174,96,0.32);"
            "border-radius:20px;padding:3px 12px;"
            'font-size:0.73rem;font-weight:600;">'
            "● RMP Active"
            "</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span style="'
            "background:rgba(108,117,125,0.09);color:#6c757d;"
            "border:1px solid rgba(108,117,125,0.26);"
            "border-radius:20px;padding:3px 12px;"
            'font-size:0.73rem;font-weight:600;">'
            "○ RMP Not Configured"
            "</span>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    st.divider()

    # Section label
    st.markdown(
        "<div style='font-size:0.68rem;font-weight:600;color:#8a9ab0;"
        "letter-spacing:0.07em;text-transform:uppercase;margin-bottom:4px;'>"
        "Navigation</div>",
        unsafe_allow_html=True,
    )

    # Navigation options — emoji icons mapped back to plain page names so
    # the rest of the app (if page == "Dashboard": ...) stays untouched.
    _NAV_LABELS = {
        "📊  Dashboard":          "Dashboard",
        "🧾  RMP Configuration":  "RMP Configuration",
        "➕  Create New RMF":     "Create New RMF",
        "🕘  History":            "History",
    }

    _selected = st.radio(
        "nav",
        list(_NAV_LABELS.keys()),
        label_visibility="collapsed",
    )
    page = _NAV_LABELS[_selected]

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.divider()
    st.markdown(
        '<div style="font-size:0.67rem;color:#6b7280;padding:0 2px 4px;line-height:1.75;">'
        '<div style="font-size:0.63rem;font-weight:700;color:#8a9ab0;letter-spacing:0.07em;'
        'text-transform:uppercase;margin-bottom:6px;">About</div>'
        'ISO&nbsp;14971 Risk Management<br>'
        'AI-assisted RMF generation<br>'
        'DeepSeek LLM · RAG pipeline'
        '</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════════════════════
if page == "Dashboard":

    from collections import Counter as _Counter
    from datetime import datetime as _dt
    try:
        import plotly.graph_objects as _go
        _PLOTLY = True
    except ImportError:
        _PLOTLY = False

    # ── Dark theme CSS (scoped to Dashboard rerun) ───────────────────────────────
    st.markdown("""
    <style>
    .stApp,[data-testid="stAppViewContainer"]{background:#080d18!important;}
    [data-testid="stAppViewBlockContainer"]{
        max-width:1280px!important;padding:2rem 2.5rem 3rem!important;margin:0 auto!important;
    }
    [data-testid="stMetric"]{background:transparent!important;border:none!important;
        padding:0!important;box-shadow:none!important;}
    hr{border-color:rgba(255,255,255,0.07)!important;margin:20px 0!important;}
    [data-testid="stSidebar"]{background:#0a0e1a!important;border-right:1px solid #111827!important;}
    [data-testid="stPlotlyChart"]{border:1px solid #1a2840!important;border-radius:14px!important;overflow:hidden!important;box-shadow:0 4px 20px rgba(0,0,0,0.28)!important;}
    </style>
    """, unsafe_allow_html=True)

    # ── Data ──────────────────────────────────────────────────────────────────────
    versions = get_all_rmf_versions()
    rmp_active = rmp_config_exists()
    all_records = []
    for _v in versions:
        all_records.extend(get_risk_records_by_rmf(_v[0]))
    total_records = len(all_records)
    _risk_counts = _Counter(r.get("initial_risk_level", "Unknown") for r in all_records)
    _v_count = len(versions)
    _high_ct = _risk_counts.get("High", 0)
    _rmp_label = "Active" if rmp_active else "Not Set"
    _rmp_accent = "#10b981" if rmp_active else "#ef4444"

    # ── Header ────────────────────────────────────────────────────────────────────
    _today_str = _dt.now().strftime("%B %d, %Y")
    st.markdown(
        f'<div style="display:flex;align-items:flex-start;justify-content:space-between;'
        f'padding:6px 0 28px;">'
        f'<div>'
        f'<div style="font-size:1.55rem;font-weight:800;color:#f1f5f9;letter-spacing:-0.02em;">'
        f'Risk Management Dashboard</div>'
        f'<div style="font-size:0.80rem;color:#475569;margin-top:4px;">'
        f'ISO&nbsp;14971 · Medical Device Risk Management File</div>'
        f'</div>'
        f'<div style="background:#0f1724;color:#64748b;padding:7px 16px;border-radius:20px;'
        f'font-size:0.76rem;font-weight:500;border:1px solid #1a2840;white-space:nowrap;">'
        f'{_today_str}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Metric cards ─────────────────────────────────────────────────────────────
    _mc1, _mc2, _mc3, _mc4 = st.columns(4, gap="medium")
    with _mc1:
        st.markdown(
            _dash_stat_card("📁", "RMF Versions", str(_v_count), "#3b82f6",
                            f"{_v_count} file{'s' if _v_count != 1 else ''} on record"),
            unsafe_allow_html=True,
        )
    with _mc2:
        st.markdown(
            _dash_stat_card("📋", "RMP Status", _rmp_label, _rmp_accent,
                            "Risk Management Plan"),
            unsafe_allow_html=True,
        )
    with _mc3:
        st.markdown(
            _dash_stat_card("📊", "Risk Records", str(total_records), "#8b5cf6",
                            f"across {_v_count} RMF version{'s' if _v_count != 1 else ''}"),
            unsafe_allow_html=True,
        )
    with _mc4:
        st.markdown(
            _dash_stat_card("⚠️", "High-Risk Items", str(_high_ct), "#ef4444",
                            "require priority review"),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)

    # ── Workflow panel — single dark card with 4 steps ────────────────────────────
    _WF = [
        ("#3b82f6", "01", "RMP Configuration", "Define risk plan and acceptability criteria"),
        ("#10b981", "02", "Create RMF",         "AI-assisted risk table generation"),
        ("#8b5cf6", "03", "Review & Edit",       "Revise records, creates new version"),
        ("#f59e0b", "04", "History",             "View, compare, and export all versions"),
    ]
    _wf_steps_html = ""
    for _wi, (_wac, _wn, _wt, _wd) in enumerate(_WF):
        _wf_steps_html += (
            f'<div style="flex:1;background:{_wac}0c;border:1px solid {_wac}28;'
            f'border-top:2px solid {_wac};border-radius:12px;padding:16px 14px;min-height:110px;">'
            f'<div style="font-size:1.1rem;font-weight:900;color:{_wac};opacity:0.45;'
            f'font-family:monospace;">{_wn}</div>'
            f'<div style="font-size:0.83rem;font-weight:700;color:#e2e8f0;margin-top:8px;">{_wt}</div>'
            f'<div style="font-size:0.72rem;color:#64748b;margin-top:5px;line-height:1.45;">{_wd}</div>'
            f'</div>'
        )
        if _wi < 3:
            _wf_steps_html += (
                '<div style="display:flex;align-items:center;padding:0 6px;'
                'color:#1e2d45;font-size:1.4rem;font-weight:200;">›</div>'
            )
    st.markdown(
        f'<div style="background:#0f1724;border:1px solid #1a2840;border-radius:18px;'
        f'padding:22px 24px 24px;">'
        f'<div style="margin-bottom:18px;">'
        f'<div style="font-size:0.90rem;font-weight:700;color:#e2e8f0;">Recommended Workflow</div>'
        f'<div style="font-size:0.73rem;color:#475569;margin-top:3px;">'
        f'Follow these steps to generate a compliant ISO&nbsp;14971 Risk Management File</div>'
        f'</div>'
        f'<div style="display:flex;align-items:stretch;gap:8px;">{_wf_steps_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)

    # ── Analytics row — equal columns, locked shared height ──────────────────────
    # _CHART_H: total Plotly figure height (px) — both charts use this value.
    # _ACT_INNER_H: scrollable list area inside the activity card so the card
    #               outer height matches the chart cards visually.
    _CHART_H = 270
    _ACT_INNER_H = 204   # 270 - 18(pt) - 14(pb) - 22(header+gap) ≈ 216, leave ~12 slack

    _acol1, _acol2, _acol3 = st.columns(3, gap="medium")

    with _acol1:
        if versions:
            _v_dates = sorted(v[6][:10] for v in versions)
            _date_agg: dict = {}
            for _d in _v_dates:
                _date_agg[_d] = _date_agg.get(_d, 0) + 1
            _cum_dates = sorted(_date_agg.keys())
            _cum_vals, _run = [], 0
            for _d in _cum_dates:
                _run += _date_agg[_d]
                _cum_vals.append(_run)

            if _PLOTLY:
                _fig_line = _go.Figure()
                _fig_line.add_trace(_go.Scatter(
                    x=_cum_dates, y=_cum_vals, mode="lines+markers",
                    line=dict(color="#3b82f6", width=2.5),
                    marker=dict(size=8, color="#3b82f6",
                                line=dict(color="#0f1724", width=1.5)),
                    fill="tozeroy", fillcolor="rgba(59,130,246,0.09)",
                    hovertemplate="<b>%{y}</b> versions<extra></extra>",
                ))
                _fig_line.update_layout(
                    title=dict(text="RMF Versions Over Time",
                               font=dict(size=13, color="#e2e8f0"),
                               x=0.01, xanchor="left"),
                    height=_CHART_H, margin=dict(l=8, r=12, t=42, b=20),
                    paper_bgcolor="#0f1724", plot_bgcolor="#0f1724",
                    xaxis=dict(showgrid=False,
                               tickfont=dict(size=10, color="#475569"),
                               linecolor="#1a2840", showline=True),
                    yaxis=dict(showgrid=True, gridcolor="#1a2840",
                               tickfont=dict(size=10, color="#475569"),
                               dtick=1, zeroline=False),
                    showlegend=False,
                    hoverlabel=dict(bgcolor="#1e2d45", bordercolor="#3b82f6",
                                   font_size=11),
                )
                st.plotly_chart(_fig_line, use_container_width=True,
                                config={"displayModeBar": False})
            else:
                st.markdown(
                    '<div style="font-size:0.83rem;font-weight:700;color:#e2e8f0;'
                    'margin-bottom:6px;">RMF Versions Over Time</div>',
                    unsafe_allow_html=True,
                )
                st.line_chart(pd.DataFrame({"Versions": _cum_vals}, index=_cum_dates))
        else:
            st.markdown(
                f'<div style="background:#0f1724;border:1px solid #1a2840;border-radius:14px;'
                f'height:{_CHART_H}px;display:flex;flex-direction:column;align-items:center;'
                f'justify-content:center;gap:6px;">'
                f'<div style="font-size:0.83rem;font-weight:700;color:#e2e8f0;">'
                f'RMF Versions Over Time</div>'
                f'<div style="font-size:0.75rem;color:#334155;">No data yet</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    with _acol2:
        _rl_labels = ["High", "Medium", "Low"]
        _rl_colors = ["#ef4444", "#f59e0b", "#10b981"]
        _rl_values = [_risk_counts.get(k, 0) for k in _rl_labels]

        if all_records and _PLOTLY:
            _fig_donut = _go.Figure(_go.Pie(
                labels=_rl_labels,
                values=_rl_values,
                hole=0.65,
                marker=dict(
                    colors=_rl_colors,
                    line=dict(color="#080d18", width=2.5),
                ),
                textinfo="percent",
                textfont=dict(size=10, color="#f1f5f9"),
                textposition="inside",
                insidetextorientation="horizontal",
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "Count: <b>%{value}</b><br>"
                    "Share: <b>%{percent}</b>"
                    "<extra></extra>"
                ),
                pull=[0.04, 0.01, 0.01],
            ))
            _fig_donut.update_layout(
                title=dict(
                    text="Risk Level Distribution",
                    font=dict(size=13, color="#e2e8f0"),
                    x=0.02, xanchor="left",
                ),
                height=_CHART_H,
                margin=dict(l=8, r=8, t=42, b=20),
                paper_bgcolor="#0f1724",
                plot_bgcolor="#0f1724",
                showlegend=True,
                legend=dict(
                    orientation="h",
                    y=-0.04, x=0.5, xanchor="center",
                    font=dict(size=10, color="#94a3b8"),
                    bgcolor="rgba(0,0,0,0)",
                    itemsizing="constant",
                    traceorder="normal",
                ),
                annotations=[
                    dict(
                        text=f"<b>{total_records}</b>",
                        x=0.5, y=0.55,
                        font=dict(size=20, color="#f1f5f9"),
                        showarrow=False, align="center",
                    ),
                    dict(
                        text="Total",
                        x=0.5, y=0.42,
                        font=dict(size=10, color="#64748b"),
                        showarrow=False, align="center",
                    ),
                ],
                hoverlabel=dict(
                    bgcolor="#1e2d45", bordercolor="#1e2d45",
                    font_size=11, font_color="#e2e8f0",
                ),
            )
            st.plotly_chart(_fig_donut, use_container_width=True,
                            config={"displayModeBar": False})

        elif all_records:
            _fb_rows = ""
            for _rl, _rv, _rc in zip(_rl_labels, _rl_values, _rl_colors):
                _pct = _rv / total_records * 100 if total_records else 0
                _fb_rows += (
                    f'<div style="margin-bottom:10px;">'
                    f'<div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
                    f'<span style="font-size:0.76rem;color:#94a3b8;display:flex;'
                    f'align-items:center;gap:6px;">'
                    f'<span style="width:8px;height:8px;border-radius:50%;'
                    f'background:{_rc};display:inline-block;"></span>{_rl}</span>'
                    f'<span style="font-size:0.76rem;font-weight:600;color:#e2e8f0;">'
                    f'{_rv} <span style="color:#475569;font-weight:400;">({_pct:.0f}%)</span>'
                    f'</span></div>'
                    f'<div style="background:#1a2840;border-radius:4px;height:5px;">'
                    f'<div style="background:{_rc};width:{min(_pct, 100):.1f}%;'
                    f'height:100%;border-radius:4px;"></div>'
                    f'</div></div>'
                )
            st.markdown(
                f'<div style="background:#0f1724;border:1px solid #1a2840;border-radius:14px;'
                f'height:{_CHART_H}px;box-sizing:border-box;padding:18px 18px 14px;">'
                f'<div style="font-size:0.83rem;font-weight:700;color:#e2e8f0;margin-bottom:14px;">'
                f'Risk Level Distribution</div>'
                f'{_fb_rows}'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div style="background:#0f1724;border:1px solid #1a2840;border-radius:14px;'
                f'height:{_CHART_H}px;display:flex;flex-direction:column;align-items:center;'
                f'justify-content:center;gap:6px;">'
                f'<div style="font-size:0.83rem;font-weight:700;color:#e2e8f0;">'
                f'Risk Level Distribution</div>'
                f'<div style="font-size:0.75rem;color:#334155;">No records yet</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    with _acol3:
        _act_rows_html = ""
        if versions:
            for _rv in versions[:6]:
                _rv_id, _rv_nm, _, _, _rv_vr, _rv_st, _rv_at = _rv
                _rv_sc = "#10b981" if _rv_st == "Reviewed" else "#3b82f6"
                _act_rows_html += (
                    f'<div style="display:flex;align-items:flex-start;gap:9px;'
                    f'padding:7px 0;border-bottom:1px solid #12192a;">'
                    f'<div style="width:7px;height:7px;border-radius:50%;'
                    f'background:{_rv_sc};flex-shrink:0;margin-top:4px;"></div>'
                    f'<div style="flex:1;min-width:0;">'
                    f'<div style="font-size:0.77rem;font-weight:600;color:#cbd5e1;'
                    f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                    f'#{_rv_id}&nbsp;{_rv_nm}</div>'
                    f'<div style="font-size:0.67rem;color:#475569;margin-top:1px;">'
                    f'{_rv_at[:10]} · {_rv_vr}</div>'
                    f'</div>'
                    f'<span style="background:{_rv_sc}1a;color:{_rv_sc};padding:2px 7px;'
                    f'border-radius:8px;font-size:0.63rem;font-weight:600;white-space:nowrap;">'
                    f'{_rv_st}</span>'
                    f'</div>'
                )
        else:
            _act_rows_html = (
                '<div style="color:#334155;font-size:0.79rem;'
                'padding:20px 0;text-align:center;">No activity yet</div>'
            )
        st.markdown(
            f'<div style="background:#0f1724;border:1px solid #1a2840;border-radius:14px;'
            f'height:{_CHART_H}px;box-sizing:border-box;padding:18px 18px 14px;overflow:hidden;">'
            f'<div style="font-size:0.83rem;font-weight:700;color:#e2e8f0;margin-bottom:12px;">'
            f'Recent Activity</div>'
            f'<div style="height:{_ACT_INNER_H}px;overflow-y:auto;">'
            f'{_act_rows_html}'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)

    # ── All RMF Versions — card header + interactive rows ─────────────────────────
    st.markdown(
        '<div style="background:#0f1724;border:1px solid #1a2840;border-radius:16px;'
        'padding:20px 22px 4px;">'
        '<div style="font-size:0.90rem;font-weight:700;color:#e2e8f0;margin-bottom:3px;">'
        'All RMF Versions</div>'
        '<div style="font-size:0.72rem;color:#475569;margin-bottom:16px;">'
        'Complete list of generated Risk Management Files</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    if versions:
        _th = st.columns([0.5, 2.2, 3.5, 2.2, 1.6, 1.6, 1.3])
        for _tc, _tl in zip(_th, ["ID", "Device", "Intended Use", "Type", "Version", "Status", ""]):
            _tc.markdown(
                f"<span style='font-size:0.69rem;color:#475569;font-weight:700;"
                f"text-transform:uppercase;letter-spacing:0.05em;'>{_tl}</span>",
                unsafe_allow_html=True,
            )
        st.divider()
        for _tr in versions:
            _tr_id, _tr_nm, _tr_iu, _tr_tp, _tr_vr, _tr_st, _ = _tr
            _row = st.columns([0.5, 2.2, 3.5, 2.2, 1.6, 1.6, 1.3])
            _row[0].markdown(
                f"<span style='font-size:0.80rem;color:#475569;'>#{_tr_id}</span>",
                unsafe_allow_html=True,
            )
            _row[1].markdown(
                f"<span style='font-size:0.80rem;font-weight:600;color:#cbd5e1;'>{_tr_nm}</span>",
                unsafe_allow_html=True,
            )
            _row[2].markdown(
                f"<span style='font-size:0.75rem;color:#64748b;'>"
                f"{_tr_iu[:55]}{'…' if len(_tr_iu) > 55 else ''}</span>",
                unsafe_allow_html=True,
            )
            _row[3].markdown(
                f"<span style='font-size:0.75rem;color:#64748b;'>{_tr_tp}</span>",
                unsafe_allow_html=True,
            )
            _row[4].markdown(
                f"<span style='font-size:0.75rem;color:#64748b;'>{_tr_vr}</span>",
                unsafe_allow_html=True,
            )
            _tr_sc = "#10b981" if _tr_st == "Reviewed" else "#3b82f6"
            _row[5].markdown(
                f'<span style="background:{_tr_sc}1a;color:{_tr_sc};padding:2px 9px;'
                f'border-radius:10px;font-size:0.71rem;font-weight:600;">{_tr_st}</span>',
                unsafe_allow_html=True,
            )
            if _row[6].button("Delete", key=f"delete_dash_{_tr_id}"):
                delete_rmf_version(_tr_id)
                st.success(f"RMF #{_tr_id} deleted.")
                st.rerun()
    else:
        st.markdown(
            '<div style="padding:40px 0;text-align:center;">'
            '<div style="font-size:0.85rem;color:#334155;margin-bottom:4px;">'
            'No RMF versions created yet.</div>'
            '<div style="font-size:0.78rem;color:#1e293b;">'
            'Start with <b>RMP Configuration</b> in the sidebar.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# RMP Configuration
# ══════════════════════════════════════════════════════════════════════════════
elif page == "RMP Configuration":

    st.markdown("## Risk Management Plan Configuration")
    st.caption(
        "Define the scope, acceptability criteria, and team for your risk management process. "
        "All sections must be saved before creating an RMF."
    )
    st.divider()

    cfg = get_latest_rmp_config() or {}

    # ── 1. Lifecycle Scope ─────────────────────────────────────────────────────
    with st.container():
        st.markdown("#### 1. Lifecycle Scope")
        _LIFECYCLE_OPTIONS = ["Design", "Production", "Installation", "Maintenance", "Disposal"]
        lifecycle_scope = st.multiselect(
            "Select lifecycle phases covered by this plan:",
            options=_LIFECYCLE_OPTIONS,
            default=cfg.get("lifecycle_scope", _LIFECYCLE_OPTIONS),
        )

    st.divider()

    # ── 2. Risk Acceptability Criteria ────────────────────────────────────────
    with st.container():
        st.markdown("#### 2. Risk Acceptability Criteria")

        _saved_criteria = cfg.get("risk_acceptability_criteria", {})
        _criteria_index = 0 if _saved_criteria.get("type", "template") == "template" else 1

        criteria_type = st.radio(
            "Criteria definition method:",
            options=["Default matrix template", "Custom rule text"],
            index=_criteria_index,
            horizontal=True,
        )

        if criteria_type == "Default matrix template":
            _saved_matrix = _saved_criteria.get("matrix", {})
            _matrix_rows = {
                prob: {
                    sev: _saved_matrix.get(prob, {}).get(sev, _RMP_DEFAULT_MATRIX[prob][sev])
                    for sev in _RMP_SEVERITY_LEVELS
                }
                for prob in _RMP_PROBABILITY_LEVELS
            }
            _matrix_df = pd.DataFrame.from_dict(_matrix_rows, orient="index")[_RMP_SEVERITY_LEVELS]

            st.caption(
                "Rows = Probability  ·  Columns = Severity  ·  Click any cell to change its risk level."
            )
            _edited_df = st.data_editor(
                _matrix_df,
                column_config={
                    sev: st.column_config.SelectboxColumn(
                        sev, options=["LOW", "MEDIUM", "HIGH"], required=True, width="small"
                    )
                    for sev in _RMP_SEVERITY_LEVELS
                },
                hide_index=False,
                use_container_width=True,
                key="rmp_matrix_editor",
            )

            st.caption("Color preview (read-only):")
            st.dataframe(
                _edited_df.style.map(_style_risk_cell),
                use_container_width=True,
                hide_index=False,
            )

            criteria_to_save = {
                "type": "template",
                "matrix": _edited_df.to_dict(orient="index"),
            }
        else:
            _custom_text = st.text_area(
                "Custom acceptability rule:",
                value=_saved_criteria.get(
                    "content",
                    "Severity >= 3 and Probability >= 2 is unacceptable.",
                ),
                height=100,
            )
            criteria_to_save = {
                "type": "custom",
                "content": _custom_text,
            }

    st.divider()

    # ── 3. Overall Residual Risk Evaluation ───────────────────────────────────
    with st.container():
        st.markdown("#### 3. Overall Residual Risk Evaluation Method")

        residual_risk_method = st.text_area(
            "Describe the method for evaluating overall residual risk after all controls are applied:",
            value=cfg.get("residual_risk_method", ""),
            placeholder=(
                "e.g. Overall residual risk is evaluated by aggregating individual residual risks "
                "and comparing against the defined acceptability criteria. The benefit-risk ratio "
                "is documented and reviewed by the clinical team."
            ),
            height=120,
        )

        _BASIS_OPTIONS = [
            "Benefit-risk analysis",
            "Industry standards",
            "Clinical evidence",
            "Post-market surveillance data",
            "Expert judgement",
        ]
        residual_risk_basis = st.multiselect(
            "Basis for overall residual risk evaluation (select all that apply):",
            options=_BASIS_OPTIONS,
            default=cfg.get("residual_risk_basis", []),
        )

    st.divider()

    # ── 4. Verification Method Library ────────────────────────────────────────
    with st.container():
        st.markdown("#### 4. Verification Method Library")

        _STANDARD_METHODS = [
            "Design Review",
            "Unit Testing",
            "Integration Testing",
            "Usability Testing",
            "Clinical Validation",
            "Alarm Verification",
            "Electrical Safety Testing",
            "Biocompatibility Testing",
            "Software Verification",
        ]
        _saved_methods = cfg.get("verification_methods", [])
        _saved_standard = [m for m in _saved_methods if m in _STANDARD_METHODS]
        _saved_custom   = [m for m in _saved_methods if m not in _STANDARD_METHODS]

        selected_methods = st.multiselect(
            "Standard verification methods:",
            options=_STANDARD_METHODS,
            default=_saved_standard,
        )
        custom_methods_input = st.text_input(
            "Additional custom methods (comma-separated):",
            value=", ".join(_saved_custom),
            placeholder="e.g. Sterility Testing, Fatigue Testing",
        )
        _custom_methods = [m.strip() for m in custom_methods_input.split(",") if m.strip()]
        verification_methods = selected_methods + _custom_methods

    st.divider()

    # ── 5. Team Competency Declaration ────────────────────────────────────────
    with st.container():
        st.markdown("#### 5. Team Competency Declaration")

        team_members = st.text_area(
            "List team members and their responsibilities:",
            value=cfg.get("team_members", ""),
            placeholder=(
                "- Dr. Smith — Risk Manager\n"
                "- Eng. Lee — Design Engineer\n"
                "- Dr. Chen — Clinical Expert\n"
                "- Ms. Wang — Regulatory Affairs"
            ),
            height=150,
        )

    st.divider()

    save_col, _ = st.columns([2, 5])
    with save_col:
        if st.button("Save RMP Configuration", type="primary", use_container_width=True):
            save_rmp_config({
                "lifecycle_scope": lifecycle_scope,
                "risk_acceptability_criteria": criteria_to_save,
                "residual_risk_method": residual_risk_method,
                "residual_risk_basis": residual_risk_basis,
                "verification_methods": verification_methods,
                "team_members": team_members,
            })
            st.success("RMP Configuration saved successfully.", icon="✅")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Create New RMF
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Create New RMF":

    st.markdown("## Create New RMF")
    st.caption("Three-step AI-assisted risk record generation following ISO 14971.")
    st.divider()

    if not rmp_config_exists():
        st.warning(
            "Please complete and save the Risk Management Plan before creating a new RMF.",
            icon="⚠️",
        )
        st.info("Navigate to **RMP Configuration** in the sidebar to get started.")
        st.stop()

    _step_bar(st.session_state.step)
    st.markdown("")

    # ── Step 1: Device information ─────────────────────────────────────────────
    if st.session_state.step == 1:

        st.markdown("#### Step 1 — Device Information")
        st.write("Provide basic details about the medical device.")
        st.markdown("")

        device_name = st.text_input(
            "Device Name",
            value=st.session_state.device_name,
            placeholder="e.g. Wearable Sepsis Biosensor",
        )
        intended_use = st.text_area(
            "Intended Use",
            value=st.session_state.intended_use,
            placeholder="Describe the intended medical purpose of this device...",
            height=100,
        )
        device_type = st.text_input(
            "Device Type",
            value=st.session_state.device_type,
            placeholder="e.g. wearable biosensor, infusion pump, ECG monitor",
        )

        st.markdown("")
        if st.button("Generate Follow-up Questions →", type="primary"):
            errors = validate_device_input(device_name, intended_use, device_type)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                st.session_state.device_name = device_name
                st.session_state.intended_use = intended_use
                st.session_state.device_type = device_type

                with st.spinner("Stage 1 — generating follow-up questions..."):
                    try:
                        questions, rag_context, _ = generate_followup_questions(
                            device_name, intended_use, device_type
                        )
                        st.session_state.questions = questions
                        st.session_state.generated_rag_context = rag_context
                        st.session_state.step = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"Question generation failed: {e}")

    # ── Step 2: Follow-up questions ────────────────────────────────────────────
    elif st.session_state.step == 2:

        st.markdown("#### Step 2 — Follow-up Questions")
        st.markdown(
            f"Device: **{st.session_state.device_name}** &nbsp;·&nbsp; "
            f"Type: **{st.session_state.device_type}**"
        )
        st.write(
            "Answer the questions below. "
            "More detail produces a more accurate and specific RMF."
        )
        st.divider()

        answers = []
        for i, question in enumerate(st.session_state.questions):
            answer = st.text_area(
                f"Q{i + 1}: {question}", key=f"answer_{i}", height=80
            )
            answers.append(answer)

        st.divider()
        col_back, col_generate, _ = st.columns([1, 2, 4])

        with col_back:
            if st.button("← Back", use_container_width=True):
                st.session_state.step = 1
                st.rerun()

        with col_generate:
            if st.button("Generate RMF Draft →", type="primary", use_container_width=True):
                followup_qa = [
                    {"question": q, "answer": a}
                    for q, a in zip(st.session_state.questions, answers)
                ]

                with st.spinner("Stage 2 — generating RMF risk table..."):
                    try:
                        df, rag_context, raw_response = generate_rmf_from_answers(
                            st.session_state.device_name,
                            st.session_state.intended_use,
                            st.session_state.device_type,
                            followup_qa,
                        )

                        # Only write to DB after a successful LLM response
                        rmf_id = create_rmf_version(
                            st.session_state.device_name,
                            st.session_state.intended_use,
                            st.session_state.device_type,
                        )
                        save_risk_records(rmf_id, df)

                        st.session_state.rmf_id = rmf_id
                        st.session_state.followup_qa = followup_qa
                        st.session_state.generated_df = df
                        st.session_state.generated_rag_context = rag_context
                        st.session_state.generated_raw_response = raw_response
                        st.session_state.step = 3
                        st.rerun()
                    except RuntimeError as e:
                        st.error(f"RMF generation failed: {e}")

    # ── Step 3: Results ────────────────────────────────────────────────────────
    elif st.session_state.step == 3:

        st.markdown("#### Step 3 — Generated RMF Draft")

        st.success(
            f"RMF generated and saved to database (ID: {st.session_state.rmf_id}).",
            icon="✅",
        )

        st.markdown("")
        st.dataframe(st.session_state.generated_df, use_container_width=True)

        csv_data = (
            st.session_state.generated_df
            .to_csv(index=False)
            .encode("utf-8")
        )
        dl_col, _ = st.columns([2, 5])
        with dl_col:
            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name="rmf_draft.csv",
                mime="text/csv",
                use_container_width=True,
            )

        st.markdown("")
        with st.expander("View RAG Context"):
            st.json(st.session_state.generated_rag_context)

        with st.expander("View Raw LLM Response"):
            st.text(st.session_state.generated_raw_response)

        st.warning(
            "This RMF draft is AI-assisted content only. "
            "Human expert review is required before any regulatory or safety use.",
            icon="⚠️",
        )

        st.markdown("")
        if st.button("← Start New RMF"):
            for key in _WIZARD_KEYS:
                st.session_state.pop(key, None)
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# History
# ══════════════════════════════════════════════════════════════════════════════
elif page == "History":

    st.markdown("## RMF History")
    st.caption("Browse, review, and revise all saved Risk Management File versions.")
    st.divider()

    _DB_TO_DISPLAY = {
        "hazard":               "Hazard",
        "hazardous_situation":  "Hazardous Situation",
        "possible_harm":        "Possible Harm",
        "severity":             "Severity",
        "probability":          "Probability",
        "initial_risk_level":   "Initial Risk Level",
        "risk_control_measure": "Risk Control Measure",
        "residual_risk":        "Residual Risk",
        "verification_method":  "Verification Method",
        "status":               "Status",
    }
    _EDIT_COLS = list(_DB_TO_DISPLAY.values())
    _RISK_LEVEL_OPTS = ["High", "Medium", "Low"]

    versions = get_all_rmf_versions()

    if not versions:
        st.info(
            "No RMF versions found. Create one by navigating to **Create New RMF**.",
            icon="ℹ️",
        )
    else:
        for version in versions:
            rmf_id, device_name, intended_use, device_type, version_name, status, created_at = version

            _icon = "✅" if status == "Reviewed" else "📄"
            with st.expander(
                f"{_icon}  #{rmf_id} — {device_name}  ·  {version_name}  ·  {created_at}"
            ):
                meta_a, meta_b, meta_c, meta_d = st.columns(4)
                meta_a.markdown(f"**Device**\n\n{device_name}")
                meta_b.markdown(f"**Type**\n\n{device_type}")
                meta_c.markdown(f"**Version**\n\n{version_name}")
                meta_d.markdown(f"**Status**\n\n{status}")

                st.caption(f"Intended use: {intended_use}")
                st.caption(f"Created: {created_at}")

                st.divider()

                records = get_risk_records_by_rmf(rmf_id)
                if records:
                    st.markdown(f"**Risk Records — {len(records)} rows**")
                    _disp_df = (
                        pd.DataFrame(records)
                        .drop(columns=["id", "rmf_id", "created_at"], errors="ignore")
                        .rename(columns=_DB_TO_DISPLAY)
                    )
                    st.dataframe(_disp_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No risk records saved for this version.")

                st.divider()
                btn_col1, btn_col2, _ = st.columns([2, 1, 4])

                if btn_col1.button(
                    "Edit / Revise", key=f"edit_hist_{rmf_id}", use_container_width=True
                ):
                    _recs = get_risk_records_by_rmf(rmf_id)
                    if _recs:
                        _df = (
                            pd.DataFrame(_recs)
                            .drop(columns=["id", "rmf_id", "created_at"], errors="ignore")
                            .rename(columns=_DB_TO_DISPLAY)
                        )
                        _df = _df[[c for c in _EDIT_COLS if c in _df.columns]]
                    else:
                        _df = pd.DataFrame(columns=_EDIT_COLS)
                    st.session_state.hist_edit_source_id = rmf_id
                    st.session_state.hist_edit_df = _df
                    st.session_state.hist_edit_counter += 1
                    st.rerun()

                if btn_col2.button(
                    "Delete", key=f"delete_hist_{rmf_id}", use_container_width=True
                ):
                    delete_rmf_version(rmf_id)
                    if st.session_state.hist_edit_source_id == rmf_id:
                        st.session_state.hist_edit_source_id = None
                        st.session_state.hist_edit_df = None
                    st.success(f"RMF #{rmf_id} deleted.")
                    st.rerun()

    # ── Revision editor ────────────────────────────────────────────────────────
    if st.session_state.hist_edit_source_id is not None:
        src_id = st.session_state.hist_edit_source_id

        st.divider()
        st.markdown(f"#### Revising RMF #{src_id} — Edit Risk Records")
        st.info(
            "Edit cells inline, use the **+** icon to add rows, or select rows and press "
            "**Delete** to remove them. Click **Save as New Version** when done — "
            "the original version is never modified.",
            icon="✏️",
        )

        edited_df = st.data_editor(
            st.session_state.hist_edit_df,
            column_config={
                "Hazard": st.column_config.TextColumn("Hazard", width="medium"),
                "Hazardous Situation": st.column_config.TextColumn(
                    "Hazardous Situation", width="large"
                ),
                "Possible Harm": st.column_config.TextColumn("Possible Harm", width="medium"),
                "Severity": st.column_config.SelectboxColumn(
                    "Severity", options=_RISK_LEVEL_OPTS, required=True, width="small"
                ),
                "Probability": st.column_config.SelectboxColumn(
                    "Probability", options=_RISK_LEVEL_OPTS, required=True, width="small"
                ),
                "Initial Risk Level": st.column_config.SelectboxColumn(
                    "Initial Risk Level", options=_RISK_LEVEL_OPTS, required=True, width="small"
                ),
                "Risk Control Measure": st.column_config.TextColumn(
                    "Risk Control Measure", width="large"
                ),
                "Residual Risk": st.column_config.SelectboxColumn(
                    "Residual Risk", options=_RISK_LEVEL_OPTS, required=True, width="small"
                ),
                "Verification Method": st.column_config.TextColumn(
                    "Verification Method", width="medium"
                ),
                "Status": st.column_config.SelectboxColumn(
                    "Status", options=["Draft", "Reviewed", "Approved"], required=True, width="small"
                ),
            },
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"revision_editor_{src_id}_{st.session_state.hist_edit_counter}",
        )

        st.divider()
        col_save, col_cancel, _ = st.columns([2, 1, 4])

        if col_save.button("Save as New Version", type="primary", use_container_width=True):
            try:
                new_rmf_id = clone_rmf_version(src_id)
                update_risk_records(new_rmf_id, edited_df)
                st.session_state.hist_edit_source_id = None
                st.session_state.hist_edit_df = None
                st.success(
                    f"Saved as RMF #{new_rmf_id}. Original RMF #{src_id} is unchanged.",
                    icon="✅",
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Save failed: {exc}")

        if col_cancel.button("Cancel", use_container_width=True):
            st.session_state.hist_edit_source_id = None
            st.session_state.hist_edit_df = None
            st.rerun()
