"""Page Tournois : palmarès, top vainqueurs et durée des matchs par tournoi."""

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

from components.plotly_theme import (
    TENNIS_CLAY,
    TENNIS_GREEN,
    TENNIS_HARD,
    TENNIS_LINE,
    apply_tennis_theme,
)
from components.widgets import format_date_dd_mm_yyyy, page_info
from db.duckdb_session import create_connection

st.set_page_config(page_title="Tournois — Tennis Analytics", layout="wide")

SURF_COLORS = {"Hard": TENNIS_HARD, "Clay": TENNIS_CLAY, "Grass": TENNIS_GREEN}


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return create_connection(_ROOT)


@st.cache_data(show_spinner=False)
def _tournament_list(_root: str, circuit: str) -> list[str]:
    try:
        df = _connection().execute(
            "SELECT DISTINCT tourney_name FROM v_matches WHERE circuit = ? ORDER BY tourney_name",
            [circuit],
        ).df()
        return df["tourney_name"].tolist()
    except duckdb.Error:
        return []


@st.cache_data(show_spinner=False)
def _palmares(_root: str, tourney: str, circuit: str) -> pd.DataFrame:
    return _connection().execute(
        """
        SELECT
            CAST(tourney_date / 10000 AS INT) AS annee,
            COALESCE(NULLIF(surface, ''), 'Inconnue') AS surface,
            CASE tourney_level
                WHEN 'G' THEN 'Grand Chelem'
                WHEN 'M' THEN 'Masters / Premier'
                WHEN 'A' THEN '500'
                WHEN 'D' THEN '250'
                WHEN 'F' THEN 'Finals'
                ELSE COALESCE(tourney_level, '—')
            END AS niveau,
            winner_name AS vainqueur,
            loser_name  AS finaliste,
            score,
            minutes
        FROM v_matches
        WHERE tourney_name = ?
          AND circuit = ?
          AND round = 'F'
        ORDER BY tourney_date DESC
        """,
        [tourney, circuit],
    ).df()


@st.cache_data(show_spinner=False)
def _top_winners(_root: str, tourney: str, circuit: str) -> pd.DataFrame:
    return _connection().execute(
        """
        SELECT
            winner_name,
            COUNT(*) AS titres,
            MIN(CAST(tourney_date / 10000 AS INT)) AS premiere,
            MAX(CAST(tourney_date / 10000 AS INT)) AS derniere
        FROM v_matches
        WHERE tourney_name = ?
          AND circuit = ?
          AND round = 'F'
        GROUP BY winner_name
        ORDER BY titres DESC
        LIMIT 10
        """,
        [tourney, circuit],
    ).df()


@st.cache_data(show_spinner=False)
def _duration_by_year(_root: str, tourney: str, circuit: str) -> pd.DataFrame:
    return _connection().execute(
        """
        SELECT
            CAST(tourney_date / 10000 AS INT) AS annee,
            ROUND(AVG(minutes) FILTER (WHERE minutes > 0 AND minutes < 400), 0) AS duree_moy,
            COUNT(*) AS nb_matchs
        FROM v_matches
        WHERE tourney_name = ?
          AND circuit = ?
        GROUP BY annee
        ORDER BY annee
        """,
        [tourney, circuit],
    ).df()


@st.cache_data(show_spinner=False)
def _surface_breakdown(_root: str, tourney: str, circuit: str) -> pd.DataFrame:
    return _connection().execute(
        """
        SELECT
            COALESCE(NULLIF(surface, ''), 'Inconnue') AS surface,
            COUNT(*) AS matchs,
            ROUND(AVG(minutes) FILTER (WHERE minutes > 0 AND minutes < 400), 0) AS duree_moy,
            ROUND(AVG(w_ace + l_ace), 1) AS aces_par_match
        FROM v_matches
        WHERE tourney_name = ?
          AND circuit = ?
        GROUP BY surface
        ORDER BY matchs DESC
        """,
        [tourney, circuit],
    ).df()


# ── Sidebar ───────────────────────────────────────────────────────────────────
circuit = st.sidebar.selectbox("Circuit", ["ATP", "WTA"], key="tourn_circuit")

st.title("Tournois")
page_info(
    "Explorez l'histoire d'un tournoi : palmarès des finales, joueurs les plus titrés, "
    "évolution de la durée moyenne des matchs au fil des années et répartition par surface."
)

tournois = _tournament_list(str(_ROOT), circuit)
if not tournois:
    st.warning("Aucun tournoi disponible. Lancez l'ingestion pour construire les parquets.")
    st.stop()

tourney = st.selectbox("Sélectionner un tournoi", tournois, key="tourn_select")

# ── Section A — Palmarès ──────────────────────────────────────────────────────
st.subheader(f"Palmarès — {tourney} ({circuit})")

palmares = _palmares(str(_ROOT), tourney, circuit)

if palmares.empty:
    st.info("Aucune finale disponible pour ce tournoi dans les données.")
else:
    st.dataframe(
        palmares.rename(columns={
            "annee": "Année",
            "surface": "Surface",
            "niveau": "Niveau",
            "vainqueur": "Vainqueur",
            "finaliste": "Finaliste",
            "score": "Score",
            "minutes": "Durée (min)",
        }),
        use_container_width=True,
        hide_index=True,
    )

st.divider()

# ── Section B — Top vainqueurs ────────────────────────────────────────────────
top_w = _top_winners(str(_ROOT), tourney, circuit)

if not top_w.empty:
    st.subheader("Top vainqueurs")
    fig_top = go.Figure(go.Bar(
        x=top_w["titres"],
        y=top_w["winner_name"],
        orientation="h",
        marker_color=TENNIS_HARD,
        text=top_w["titres"],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Titres : %{x}<extra></extra>",
    ))
    fig_top.update_layout(
        title=f"Top {len(top_w)} vainqueurs — {tourney}",
        xaxis_title="Titres",
        yaxis=dict(autorange="reversed"),
        height=max(350, len(top_w) * 40),
    )
    apply_tennis_theme(fig_top)
    st.plotly_chart(fig_top, use_container_width=True)

    with st.expander("Tableau détaillé"):
        st.dataframe(
            top_w.rename(columns={
                "winner_name": "Joueur",
                "titres": "Titres",
                "premiere": "1ère victoire",
                "derniere": "Dernière victoire",
            }),
            use_container_width=True,
            hide_index=True,
        )

st.divider()

# ── Section C — Durée par année ───────────────────────────────────────────────
dur_df = _duration_by_year(str(_ROOT), tourney, circuit)

if not dur_df.empty and dur_df["duree_moy"].notna().any():
    st.subheader("Durée moyenne des matchs par année")
    fig_dur = go.Figure(go.Scatter(
        x=dur_df["annee"],
        y=dur_df["duree_moy"],
        mode="lines+markers",
        line=dict(color=TENNIS_LINE, width=2),
        marker=dict(size=6, color=TENNIS_HARD),
        name="Durée moyenne (min)",
        hovertemplate="%{x} : %{y:.0f} min<extra></extra>",
    ))
    fig_dur.update_layout(
        title=f"Durée moyenne des matchs — {tourney}",
        xaxis_title="Année",
        yaxis_title="Durée (minutes)",
        hovermode="x unified",
    )
    apply_tennis_theme(fig_dur)
    st.plotly_chart(fig_dur, use_container_width=True)

st.divider()

# ── Section D — Répartition par surface ──────────────────────────────────────
surf_df = _surface_breakdown(str(_ROOT), tourney, circuit)

if not surf_df.empty:
    st.subheader("Répartition par surface")
    surf_colors = [SURF_COLORS.get(s, TENNIS_LINE) for s in surf_df["surface"]]
    fig_surf = go.Figure(go.Bar(
        x=surf_df["surface"],
        y=surf_df["matchs"],
        marker_color=surf_colors,
        text=surf_df["matchs"],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Matchs : %{y}<extra></extra>",
    ))
    fig_surf.update_layout(
        title=f"Matchs par surface — {tourney}",
        xaxis_title="Surface",
        yaxis_title="Nombre de matchs",
    )
    apply_tennis_theme(fig_surf)
    st.plotly_chart(fig_surf, use_container_width=True)
