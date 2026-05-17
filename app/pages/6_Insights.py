"""Page Insights : tendances long-terme aces, durée, comparaison ATP/WTA et distribution."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from components._bootstrap import init_app

_ROOT, _ = init_app(__file__)

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
from components.widgets import (
    circuit_filter_sql,
    circuit_selectbox,
    inject_global_css,
    page_info,
)
from db.duckdb_session import create_connection

st.set_page_config(page_title="Insights — Tennis Analytics", layout="wide")
inject_global_css()


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return create_connection(_ROOT)


@st.cache_data(show_spinner=False)
def _aces_df_by_year(_root: str, circuit: str) -> pd.DataFrame:
    cf = circuit_filter_sql(circuit)
    return (
        _connection()
        .execute(
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
        )
        .df()
    )


@st.cache_data(show_spinner=False)
def _duration_by_year(_root: str, circuit: str) -> pd.DataFrame:
    cf = circuit_filter_sql(circuit)
    return (
        _connection()
        .execute(
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
        )
        .df()
    )


@st.cache_data(show_spinner=False)
def _atp_wta_comparison(_root: str) -> pd.DataFrame:
    return (
        _connection()
        .execute(
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
        )
        .df()
    )


@st.cache_data(show_spinner=False)
def _duration_distribution(_root: str, circuit: str) -> pd.DataFrame:
    cf = circuit_filter_sql(circuit)
    return (
        _connection()
        .execute(
            f"""
        SELECT
            COALESCE(NULLIF(surface, ''), 'Inconnue') AS surface,
            minutes
        FROM v_matches
        WHERE minutes > 0
          AND minutes < 400
          {cf}
        """
        )
        .df()
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────
circuit = circuit_selectbox(key="ins_circuit")

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
    fig_aces.add_trace(
        go.Scatter(
            x=aces_df["annee"],
            y=aces_df["aces_par_match"],
            mode="lines+markers",
            name="Aces / match",
            line=dict(color=TENNIS_HARD, width=2),
            marker=dict(size=5),
        )
    )
    fig_aces.add_trace(
        go.Scatter(
            x=aces_df["annee"],
            y=aces_df["df_par_match"],
            mode="lines+markers",
            name="Double-fautes / match",
            line=dict(color=TENNIS_CLAY, width=2, dash="dash"),
            marker=dict(size=5),
        )
    )
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
    fig_dur.add_trace(
        go.Scatter(
            x=dur_df["annee"],
            y=dur_df["duree_moy"],
            mode="lines+markers",
            name="Durée moyenne (min)",
            line=dict(color=TENNIS_LINE, width=2),
            marker=dict(size=5),
        )
    )
    fig_dur.add_trace(
        go.Scatter(
            x=dur_df["annee"],
            y=dur_df["duree_mediane"],
            mode="lines+markers",
            name="Durée médiane (min)",
            line=dict(color=TENNIS_GREEN, width=2, dash="dot"),
            marker=dict(size=5),
        )
    )
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
        fig_box.add_trace(
            go.Box(
                y=subset,
                name=surf,
                marker_color=color,
                boxmean="sd",
                hovertemplate="<b>%{x}</b><br>%{y} min<extra></extra>",
            )
        )
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


# ── Section E — Records de séries de victoires consécutives ──────────────────
st.divider()
st.subheader("Records — plus longues séries de victoires consécutives")
page_info(
    "Algorithme classique de *gaps and islands* SQL : pour chaque joueur, on identifie "
    "les sous-séquences de victoires consécutives et on extrait les plus longues. "
    "Inclut tous les matchs ATP/WTA officiels depuis 2010."
)


@st.cache_data(show_spinner=False)
def _longest_win_streaks(_root: str, circuit: str, top_n: int = 15) -> pd.DataFrame:
    """Calcule les plus longues séries de victoires consécutives par joueur.

    Pattern gaps-and-islands :
    - Pour chaque match d'un joueur, on attribue 1 si victoire, 0 sinon.
    - On regroupe les matchs consécutifs avec même statut via
      `row_number - sum(wins)` qui reste constant durant une série de victoires.
    """
    cf = circuit_filter_sql(circuit)
    sql = f"""
        WITH player_matches AS (
            -- Tous les matchs de tous les joueurs (winner + loser unionés)
            SELECT winner_id AS player_id, tourney_date,
                   1 AS is_win,
                   winner_name AS full_name
            FROM v_matches WHERE 1=1 {cf}
            UNION ALL
            SELECT loser_id  AS player_id, tourney_date,
                   0 AS is_win,
                   loser_name AS full_name
            FROM v_matches WHERE 1=1 {cf}
        ),
        ordered AS (
            SELECT player_id, full_name, tourney_date, is_win,
                   ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY tourney_date) AS rn,
                   SUM(is_win) OVER (
                        PARTITION BY player_id ORDER BY tourney_date
                        ROWS UNBOUNDED PRECEDING
                   ) AS cum_wins
            FROM player_matches
        ),
        streaks AS (
            -- L'« île » de victoires consécutives : rn - cum_wins reste constant
            SELECT player_id, full_name, is_win,
                   (rn - cum_wins) AS grp,
                   tourney_date
            FROM ordered
            WHERE is_win = 1
        ),
        agg AS (
            SELECT player_id,
                   ANY_VALUE(full_name) AS full_name,
                   grp,
                   COUNT(*) AS streak_len,
                   MIN(tourney_date) AS start_date,
                   MAX(tourney_date) AS end_date
            FROM streaks
            GROUP BY player_id, grp
        )
        SELECT player_id, full_name, streak_len, start_date, end_date
        FROM agg
        WHERE TRIM(full_name) <> ''
        ORDER BY streak_len DESC
        LIMIT ?
    """
    try:
        return _connection().execute(sql, [top_n]).df()
    except duckdb.Error:
        return pd.DataFrame()


streaks_df = _longest_win_streaks(str(_ROOT), circuit, top_n=15)

if not streaks_df.empty:
    streaks_display = streaks_df.copy()
    streaks_display["Période"] = (
        streaks_display["start_date"].map(
            lambda d: pd.to_datetime(str(int(d)), format="%Y%m%d").strftime("%d/%m/%Y")
        )
        + " → "
        + streaks_display["end_date"].map(
            lambda d: pd.to_datetime(str(int(d)), format="%Y%m%d").strftime("%d/%m/%Y")
        )
    )
    streaks_display = streaks_display[["full_name", "streak_len", "Période"]].rename(
        columns={"full_name": "Joueur", "streak_len": "Série"}
    )
    streaks_display.insert(0, "Rang", range(1, len(streaks_display) + 1))

    col1, col2 = st.columns([1, 1])
    with col1:
        st.dataframe(streaks_display, use_container_width=True, hide_index=True)
    with col2:
        fig_streaks = go.Figure(
            go.Bar(
                x=streaks_df.head(10)["streak_len"][::-1],
                y=streaks_df.head(10)["full_name"][::-1],
                orientation="h",
                marker_color=TENNIS_GREEN,
                text=streaks_df.head(10)["streak_len"][::-1],
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>%{x} victoires consécutives<extra></extra>",
            )
        )
        fig_streaks.update_layout(
            title="Top 10 plus longues séries",
            xaxis_title="Nombre de victoires consécutives",
            yaxis_title=None,
            height=420,
            margin=dict(l=10, r=40),
        )
        apply_tennis_theme(fig_streaks)
        st.plotly_chart(fig_streaks, use_container_width=True)
else:
    st.info("Données de séries indisponibles.")
