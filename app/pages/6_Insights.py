"""Page Insights : tendances long-terme aces, durée, comparaison ATP/WTA et distribution."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parents[1]
_ROOT = Path(__file__).resolve().parents[2]

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")
os.environ.setdefault("ROOT_PATH", str(_ROOT))

if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from components.plotly_theme import (
    TENNIS_CLAY,
    TENNIS_GREEN,
    TENNIS_HARD,
    TENNIS_LINE,
    apply_tennis_theme,
)
from components.widgets import circuit_filter_sql, page_info
from db.duckdb_session import create_connection

st.set_page_config(page_title="Insights — Tennis Analytics", layout="wide")


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return create_connection(_ROOT)


@st.cache_data(show_spinner=False)
def _aces_df_by_year(_root: str, circuit: str) -> pd.DataFrame:
    cf = circuit_filter_sql(circuit)
    return _connection().execute(
        f"""
        SELECT
            CAST(tourney_date / 10000 AS INT) AS annee,
            ROUND(AVG(w_ace + l_ace), 2) AS aces_par_match,
            ROUND(AVG(w_df  + l_df),  2) AS df_par_match,
            COUNT(*) AS nb_matchs
        FROM v_matches
        WHERE w_ace IS NOT NULL
          AND l_ace IS NOT NULL
          {cf}
        GROUP BY annee
        ORDER BY annee
        """
    ).df()


@st.cache_data(show_spinner=False)
def _duration_by_year(_root: str, circuit: str) -> pd.DataFrame:
    cf = circuit_filter_sql(circuit)
    return _connection().execute(
        f"""
        SELECT
            CAST(tourney_date / 10000 AS INT) AS annee,
            ROUND(AVG(minutes) FILTER (WHERE minutes > 0 AND minutes < 400), 0) AS duree_moy,
            ROUND(
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY minutes)
                FILTER (WHERE minutes > 0 AND minutes < 400),
                0
            ) AS duree_mediane,
            COUNT(*) FILTER (WHERE minutes > 0 AND minutes < 400) AS nb_matchs
        FROM v_matches
        WHERE 1=1
          {cf}
        GROUP BY annee
        ORDER BY annee
        """
    ).df()


@st.cache_data(show_spinner=False)
def _atp_wta_comparison(_root: str) -> pd.DataFrame:
    return _connection().execute(
        """
        SELECT
            circuit,
            CAST(tourney_date / 10000 AS INT) AS annee,
            ROUND(AVG(w_ace + l_ace), 2) AS aces_par_match,
            ROUND(AVG(minutes) FILTER (WHERE minutes > 0 AND minutes < 400), 0) AS duree_moy,
            ROUND(AVG(w_bpFaced + l_bpFaced), 2) AS bp_par_match
        FROM v_matches
        WHERE w_ace IS NOT NULL
          AND circuit IN ('ATP', 'WTA')
        GROUP BY circuit, annee
        ORDER BY annee, circuit
        """
    ).df()


@st.cache_data(show_spinner=False)
def _duration_distribution(_root: str, circuit: str) -> pd.DataFrame:
    cf = circuit_filter_sql(circuit)
    return _connection().execute(
        f"""
        SELECT
            COALESCE(NULLIF(surface, ''), 'Inconnue') AS surface,
            minutes
        FROM v_matches
        WHERE minutes > 0
          AND minutes < 400
          {cf}
        """
    ).df()


# ── Sidebar ───────────────────────────────────────────────────────────────────
circuit = st.sidebar.selectbox("Circuit", ["Tous", "ATP", "WTA"], key="ins_circuit")

st.title("Insights")
page_info(
    "Tendances long-terme sur 15 ans de tennis professionnel : "
    "évolution du nombre d'aces et de double-fautes, durée des matchs dans le temps, "
    "comparaison des circuits ATP et WTA, et distribution des durées par surface."
)
st.caption("Données ATP/WTA 2010–2026.")

# ── Section A — Aces et double-fautes ────────────────────────────────────────
st.subheader("Aces et double-fautes par match (par année)")

aces_df = _aces_df_by_year(str(_ROOT), circuit)

if not aces_df.empty:
    fig_aces = go.Figure()
    fig_aces.add_trace(go.Scatter(
        x=aces_df["annee"],
        y=aces_df["aces_par_match"],
        mode="lines+markers",
        name="Aces / match",
        line=dict(color=TENNIS_HARD, width=2),
        marker=dict(size=5),
    ))
    fig_aces.add_trace(go.Scatter(
        x=aces_df["annee"],
        y=aces_df["df_par_match"],
        mode="lines+markers",
        name="Double-fautes / match",
        line=dict(color=TENNIS_CLAY, width=2, dash="dash"),
        marker=dict(size=5),
    ))
    fig_aces.update_layout(
        title="Évolution des aces et double-fautes",
        xaxis_title="Année",
        yaxis_title="Nombre moyen par match",
        hovermode="x unified",
    )
    apply_tennis_theme(fig_aces)
    st.plotly_chart(fig_aces, use_container_width=True)
else:
    st.info("Données indisponibles pour les aces.")

st.divider()

# ── Section B — Durée des matchs ─────────────────────────────────────────────
st.subheader("Durée des matchs par année")

dur_df = _duration_by_year(str(_ROOT), circuit)

if not dur_df.empty and dur_df["duree_moy"].notna().any():
    fig_dur = go.Figure()
    fig_dur.add_trace(go.Scatter(
        x=dur_df["annee"],
        y=dur_df["duree_moy"],
        mode="lines+markers",
        name="Durée moyenne (min)",
        line=dict(color=TENNIS_LINE, width=2),
        marker=dict(size=5),
    ))
    fig_dur.add_trace(go.Scatter(
        x=dur_df["annee"],
        y=dur_df["duree_mediane"],
        mode="lines+markers",
        name="Durée médiane (min)",
        line=dict(color=TENNIS_GREEN, width=2, dash="dot"),
        marker=dict(size=5),
    ))
    fig_dur.update_layout(
        title="Durée des matchs dans le temps",
        xaxis_title="Année",
        yaxis_title="Durée (minutes)",
        hovermode="x unified",
    )
    apply_tennis_theme(fig_dur)
    st.plotly_chart(fig_dur, use_container_width=True)
else:
    st.info("Données de durée indisponibles.")

st.divider()

# ── Section C — Comparaison ATP vs WTA ───────────────────────────────────────
st.subheader("Comparaison ATP vs WTA")

cmp_df = _atp_wta_comparison(str(_ROOT))

if not cmp_df.empty:
    fig_cmp = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        subplot_titles=("Aces / match", "Durée moyenne (min)", "Break points / match"),
        vertical_spacing=0.08,
    )

    metrics = [
        ("aces_par_match", 1),
        ("duree_moy", 2),
        ("bp_par_match", 3),
    ]
    circuit_colors = {"ATP": TENNIS_HARD, "WTA": TENNIS_CLAY}

    for circuit_name, grp in cmp_df.groupby("circuit"):
        color = circuit_colors.get(str(circuit_name), TENNIS_LINE)
        for metric, row in metrics:
            fig_cmp.add_trace(
                go.Scatter(
                    x=grp["annee"],
                    y=grp[metric],
                    mode="lines+markers",
                    name=str(circuit_name),
                    line=dict(color=color, width=2),
                    marker=dict(size=4),
                    showlegend=(row == 1),
                    legendgroup=str(circuit_name),
                ),
                row=row,
                col=1,
            )

    fig_cmp.update_layout(
        height=700,
        title_text="ATP vs WTA — Tendances comparées",
        hovermode="x unified",
    )
    apply_tennis_theme(fig_cmp)
    st.plotly_chart(fig_cmp, use_container_width=True)
else:
    st.info("Données de comparaison ATP/WTA indisponibles.")

st.divider()

# ── Section D — Distribution de la durée par surface ─────────────────────────
st.subheader("Distribution de la durée des matchs par surface")

dist_df = _duration_distribution(str(_ROOT), circuit)

if not dist_df.empty:
    SURF_COLORS = {"Hard": TENNIS_HARD, "Clay": TENNIS_CLAY, "Grass": TENNIS_GREEN}

    fig_box = go.Figure()
    for surf in dist_df["surface"].unique():
        subset = dist_df[dist_df["surface"] == surf]["minutes"]
        color = SURF_COLORS.get(surf, TENNIS_LINE)
        fig_box.add_trace(go.Box(
            y=subset,
            name=surf,
            marker_color=color,
            boxmean="sd",
            hovertemplate="<b>%{x}</b><br>%{y} min<extra></extra>",
        ))
    fig_box.update_layout(
        title="Distribution de la durée des matchs par surface",
        xaxis_title="Surface",
        yaxis_title="Durée (minutes)",
        showlegend=True,
    )
    apply_tennis_theme(fig_box)
    st.plotly_chart(fig_box, use_container_width=True)
else:
    st.info("Données de durée par surface indisponibles.")
