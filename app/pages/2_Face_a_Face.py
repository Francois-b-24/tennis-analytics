"""Page Face à Face : H2H, tableau des matchs et radar des statistiques clés."""

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
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.plotly_theme import apply_tennis_theme
from components.widgets import (
    format_date_dd_mm_yyyy,
    load_player_options,
    player_selectbox,
)
from db.duckdb_session import create_connection


@st.cache_data(show_spinner=False)
def _player_options_circuit(_root: str, circuit: str) -> pd.DataFrame:
    conn = _connection()
    if circuit == "Tous":
        return load_player_options(conn)
    try:
        df = conn.execute(
            """
            SELECT pn.player_id, pn.full_name
            FROM v_player_names pn
            JOIN v_players p USING (player_id)
            WHERE p.circuit = ?
              AND TRIM(pn.full_name) <> ''
            ORDER BY pn.full_name
            """,
            [circuit],
        ).df()
        return df.drop_duplicates(subset=["full_name"])
    except duckdb.Error:
        return load_player_options(conn)


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return create_connection(_ROOT)


@st.cache_data(show_spinner=False)
def _h2h_matches(_root: str, player_a: int, player_b: int) -> pd.DataFrame:
    connection = _connection()
    sql = """
    SELECT
        tourney_name,
        tourney_date,
        surface,
        round,
        winner_name,
        loser_name,
        score,
        minutes,
        winner_id,
        loser_id,
        w_ace, w_df, w_svpt, w_1stIn, w_1stWon, w_bpSaved, w_bpFaced,
        l_ace, l_df, l_svpt, l_1stIn, l_1stWon, l_bpSaved, l_bpFaced
    FROM v_matches
    WHERE (winner_id = ? AND loser_id = ?)
       OR (winner_id = ? AND loser_id = ?)
    ORDER BY tourney_date DESC;
    """
    return connection.execute(sql, [player_a, player_b, player_b, player_a]).df()


@st.cache_data(show_spinner=False)
def _h2h_summary(_root: str, player_a: int, player_b: int) -> pd.DataFrame:
    connection = _connection()
    sql = """
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wins_a,
        SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wins_b
    FROM v_matches
    WHERE (winner_id = ? AND loser_id = ?)
       OR (winner_id = ? AND loser_id = ?);
    """
    return connection.execute(
        sql, [player_a, player_b, player_a, player_b, player_b, player_a]
    ).df()


@st.cache_data(show_spinner=False)
def _h2h_surface(_root: str, player_a: int, player_b: int) -> pd.DataFrame:
    connection = _connection()
    sql = """
    SELECT
        COALESCE(NULLIF(CAST(surface AS VARCHAR), ''), 'Inconnue') AS surface_label,
        COUNT(*) AS total,
        SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wins_a,
        SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wins_b
    FROM v_matches
    WHERE (winner_id = ? AND loser_id = ?)
       OR (winner_id = ? AND loser_id = ?)
    GROUP BY 1
    ORDER BY total DESC;
    """
    return connection.execute(
        sql, [player_a, player_b, player_a, player_b, player_b, player_a]
    ).df()


def _profile_from_matches(frame: pd.DataFrame, player_id: int) -> dict[str, float]:
    """Calcule des ratios moyens pour le radar à partir des lignes H2H."""
    required = [
        "w_ace",
        "w_df",
        "w_svpt",
        "w_1stIn",
        "w_1stWon",
        "w_bpSaved",
        "w_bpFaced",
        "l_ace",
        "l_df",
        "l_svpt",
        "l_1stIn",
        "l_1stWon",
        "l_bpSaved",
        "l_bpFaced",
    ]
    if any(column not in frame.columns for column in required):
        return {
            "ace_rate": 0.0,
            "df_rate": 0.0,
            "first_in_rate": 0.0,
            "bp_saved_rate": 0.0,
            "first_won_rate": 0.0,
        }

    def safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
        return num.astype(float) / den.replace({0: np.nan}).astype(float)

    mask_w = frame["winner_id"] == player_id
    mask_l = frame["loser_id"] == player_id
    ace = pd.concat(
        [
            safe_div(frame.loc[mask_w, "w_ace"], frame.loc[mask_w, "w_svpt"]),
            safe_div(frame.loc[mask_l, "l_ace"], frame.loc[mask_l, "l_svpt"]),
        ]
    )
    df_rate = pd.concat(
        [
            safe_div(frame.loc[mask_w, "w_df"], frame.loc[mask_w, "w_svpt"]),
            safe_div(frame.loc[mask_l, "l_df"], frame.loc[mask_l, "l_svpt"]),
        ]
    )
    first_in = pd.concat(
        [
            safe_div(frame.loc[mask_w, "w_1stIn"], frame.loc[mask_w, "w_svpt"]),
            safe_div(frame.loc[mask_l, "l_1stIn"], frame.loc[mask_l, "l_svpt"]),
        ]
    )
    bp_saved = pd.concat(
        [
            safe_div(frame.loc[mask_w, "w_bpSaved"], frame.loc[mask_w, "w_bpFaced"]),
            safe_div(frame.loc[mask_l, "l_bpSaved"], frame.loc[mask_l, "l_bpFaced"]),
        ]
    )
    first_won = pd.concat(
        [
            safe_div(frame.loc[mask_w, "w_1stWon"], frame.loc[mask_w, "w_1stIn"]),
            safe_div(frame.loc[mask_l, "l_1stWon"], frame.loc[mask_l, "l_1stIn"]),
        ]
    )

    def mean_clean(series: pd.Series) -> float:
        value = float(series.replace([np.inf, -np.inf], np.nan).dropna().mean())
        return float(np.nan_to_num(value))

    return {
        "ace_rate": mean_clean(ace),
        "df_rate": mean_clean(df_rate),
        "first_in_rate": mean_clean(first_in),
        "bp_saved_rate": mean_clean(bp_saved),
        "first_won_rate": mean_clean(first_won),
    }


@st.cache_data(show_spinner=False)
def _elo_row(_root: str, player_id: int) -> pd.DataFrame:
    connection = _connection()
    try:
        return connection.execute(
            "SELECT * FROM v_elo_latest WHERE player_id = ? LIMIT 1;",
            [player_id],
        ).df()
    except duckdb.Error:
        return pd.DataFrame()


def _favorite_message(
    player_a: int,
    player_b: int,
    name_a: str,
    name_b: str,
    surface_choice: str,
) -> str:
    elo_a = _elo_row(str(_ROOT), player_a)
    elo_b = _elo_row(str(_ROOT), player_b)
    if elo_a.empty or elo_b.empty:
        return (
            "Elo indisponible : recalculez les ratings "
            "(`uv run python -m transformation.build_elo`)."
        )

    surf_col = {
        "Dur": "elo_hard",
        "Terre battue": "elo_clay",
        "Gazon": "elo_grass",
        "Global": "elo_global",
    }.get(surface_choice, "elo_global")

    rating_a = float(elo_a.iloc[0].get(surf_col, elo_a.iloc[0]["elo_global"]))
    rating_b = float(elo_b.iloc[0].get(surf_col, elo_b.iloc[0]["elo_global"]))
    diff = rating_a - rating_b
    leader = name_a if diff >= 0 else name_b
    return (
        f"Favori ({surface_choice.lower()}) : **{leader}** "
        f"(écart Elo `{surf_col}` ≈ {abs(diff):.1f} pts)."
    )


st.set_page_config(page_title="Face à Face — Tennis Analytics", layout="wide")
st.title("Face à Face (H2H)")

circuit = st.sidebar.selectbox("Circuit", ["ATP", "WTA", "Tous"], key="h2h_circuit")

connection = _connection()
players = _player_options_circuit(str(_ROOT), circuit)
if players.empty:
    st.warning("Aucun joueur disponible pour ce circuit.")
    st.stop()

col_left, col_right = st.columns(2)
with col_left:
    player_a = player_selectbox("Joueur A", players, key="ffa")
with col_right:
    player_b = player_selectbox("Joueur B", players, key="ffb")

surface_filter = st.selectbox(
    "Surface de référence pour le favori Elo",
    ["Global", "Dur", "Terre battue", "Gazon"],
    index=0,
)

if player_a is None or player_b is None or player_a == player_b:
    st.warning("Choisissez deux joueurs distincts.")
    st.stop()

name_a = players.loc[players["player_id"] == player_a, "full_name"].iloc[0]
name_b = players.loc[players["player_id"] == player_b, "full_name"].iloc[0]

st.markdown(_favorite_message(player_a, player_b, name_a, name_b, surface_filter))

summary = _h2h_summary(str(_ROOT), player_a, player_b)
if not summary.empty:
    total = int(summary.iloc[0]["total"])
    wins_a = int(summary.iloc[0]["wins_a"])
    wins_b = int(summary.iloc[0]["wins_b"])
    st.subheader("Bilan global")
    st.write(
        f"{name_a} mène **{wins_a}** à **{wins_b}** sur **{total}** "
        "rencontres officielles indexées."
    )

surface_df = _h2h_surface(str(_ROOT), player_a, player_b)
if not surface_df.empty:
    st.subheader("Bilan par surface")
    display = surface_df.rename(
        columns={
            "surface_label": "Surface",
            "total": "Matchs",
            "wins_a": f"Victoires {name_a}",
            "wins_b": f"Victoires {name_b}",
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)

matches_df = _h2h_matches(str(_ROOT), player_a, player_b)
st.subheader("Historique des matchs")
if matches_df.empty:
    st.info("Pas de confrontations dans le jeu de données filtré.")
else:
    display_matches = matches_df.copy()
    display_matches["Date"] = display_matches["tourney_date"].map(format_date_dd_mm_yyyy)
    display_matches = display_matches.rename(
        columns={
            "tourney_name": "Tournoi",
            "surface": "Surface",
            "round": "Tour",
            "winner_name": "Vainqueur",
            "loser_name": "Perdant",
            "score": "Score",
            "minutes": "Durée (min)",
        }
    )
    st.dataframe(
        display_matches[
            [
                "Date",
                "Tournoi",
                "Surface",
                "Tour",
                "Vainqueur",
                "Perdant",
                "Score",
                "Durée (min)",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

st.subheader("Radar des statistiques clés (moyennes H2H)")
prof_a = _profile_from_matches(matches_df, player_a)
prof_b = _profile_from_matches(matches_df, player_b)

categories = [
    "Aces / pt service",
    "Double fautes / pt",
    "1re balle in / pt",
    "Balles de break sauvées",
    "Pts remportés sur 1re balle",
]
fig = go.Figure()
fig.add_trace(
    go.Scatterpolar(
        r=[
            prof_a["ace_rate"],
            prof_a["df_rate"],
            prof_a["first_in_rate"],
            prof_a["bp_saved_rate"],
            prof_a["first_won_rate"],
            prof_a["ace_rate"],
        ],
        theta=[*categories, categories[0]],
        fill="toself",
        name=name_a,
    )
)
fig.add_trace(
    go.Scatterpolar(
        r=[
            prof_b["ace_rate"],
            prof_b["df_rate"],
            prof_b["first_in_rate"],
            prof_b["bp_saved_rate"],
            prof_b["first_won_rate"],
            prof_b["ace_rate"],
        ],
        theta=[*categories, categories[0]],
        fill="toself",
        name=name_b,
    )
)
fig.update_layout(
    polar=dict(radialaxis=dict(visible=True, tickformat=".0%")),
    showlegend=True,
    title="Comparaison de style (moyennes conditionnelles sur l'H2H)",
)
apply_tennis_theme(fig)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Les ratios du radar sont des moyennes empiriques sur les matchs H2H disponibles ; "
    "certaines années peuvent manquer de statistiques détaillées dans les CSV Sackmann."
)
