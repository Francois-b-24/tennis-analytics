"""Page Face à Face : H2H, tableau des matchs et radar des statistiques clés."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from components._bootstrap import init_app

_ROOT, _ = init_app(__file__)

import math

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.plotly_theme import apply_tennis_theme
from components.widgets import (
    circuit_selectbox,
    format_date_dd_mm_yyyy,
    inject_global_css,
    load_player_options,
    page_info,
    player_selectbox,
)
from db.duckdb_session import create_connection


@st.cache_data(show_spinner=False)
def _player_options_circuit(_root: str, circuit: str) -> pd.DataFrame:
    """Liste joueurs avec déduplication par player_id et code pays IOC."""
    conn = _connection()
    cols = conn.execute("DESCRIBE v_players").df()["column_name"].tolist()
    pays_col = "ioc" if "ioc" in cols else ("country_code" if "country_code" in cols else "NULL")
    where_circuit = "" if circuit == "Tous" else "WHERE circuit = ?"
    sql = f"""
        SELECT player_id,
               TRIM(CONCAT(COALESCE(ANY_VALUE(name_first), ''),
                           ' ',
                           COALESCE(ANY_VALUE(name_last), ''))) AS full_name,
               ANY_VALUE({pays_col}) AS ioc
        FROM v_players
        {where_circuit}
        GROUP BY player_id
        HAVING TRIM(CONCAT(COALESCE(ANY_VALUE(name_first), ''),
                           ' ',
                           COALESCE(ANY_VALUE(name_last), ''))) <> ''
    """
    try:
        params = [] if circuit == "Tous" else [circuit]
        return conn.execute(sql, params).df()
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
inject_global_css()
st.title("Face à Face (H2H)")

circuit = circuit_selectbox(key="h2h_circuit", default="ATP")

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

page_info(
    "Comparez deux joueurs en face à face : bilan H2H global et par surface, "
    "historique de toutes leurs confrontations, radar comparatif de leur style de jeu "
    "(service, première balle, balles de break) et prédiction du favori selon l'Elo."
)

if player_a is None or player_b is None or player_a == player_b:
    st.warning("Choisissez deux joueurs distincts.")
    st.stop()

name_a = players.loc[players["player_id"] == player_a, "full_name"].iloc[0]
name_b = players.loc[players["player_id"] == player_b, "full_name"].iloc[0]

st.markdown(_favorite_message(player_a, player_b, name_a, name_b, surface_filter))

summary = _h2h_summary(str(_ROOT), player_a, player_b)
if not summary.empty:

    def _safe_int(v: object) -> int:
        try:
            f = float(v)
            return 0 if math.isnan(f) else int(f)
        except (TypeError, ValueError):
            return 0

    total = _safe_int(summary.iloc[0]["total"])
    wins_a = _safe_int(summary.iloc[0]["wins_a"])
    wins_b = _safe_int(summary.iloc[0]["wins_b"])
    st.subheader("Bilan global")
    if total == 0:
        st.info(f"Aucune confrontation trouvée entre {name_a} et {name_b}.")
    else:
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

    # ── Heatmap divergente : domination relative par surface ─────────────────
    # On ne garde que les 3 surfaces principales et on calcule le % de victoires
    # de A. Couleur divergente : >50 % rouge (A domine), <50 % bleu (B domine).
    main_surfaces = surface_df[surface_df["surface_label"].isin(["Hard", "Clay", "Grass"])].copy()
    if not main_surfaces.empty and main_surfaces["total"].sum() > 0:
        main_surfaces["pct_a"] = (
            main_surfaces["wins_a"] / main_surfaces["total"].replace(0, np.nan) * 100
        )
        main_surfaces = main_surfaces.set_index("surface_label").reindex(["Hard", "Clay", "Grass"])

        labels_x = ["Dur", "Terre battue", "Gazon"]
        z = [[main_surfaces["pct_a"].iloc[i] for i in range(3)]]
        text = [
            [
                (
                    (
                        f"{main_surfaces['wins_a'].iloc[i]:.0f}-"
                        f"{main_surfaces['wins_b'].iloc[i]:.0f}<br>"
                        f"({main_surfaces['pct_a'].iloc[i]:.0f} %)"
                    )
                    if pd.notna(main_surfaces["pct_a"].iloc[i])
                    else "—"
                )
                for i in range(3)
            ]
        ]

        fig_heat = go.Figure(
            go.Heatmap(
                z=z,
                x=labels_x,
                y=[f"Domination {name_a}"],
                text=text,
                texttemplate="%{text}",
                textfont=dict(size=14, color="#1a1a1a"),
                colorscale=[
                    [0.0, "#2E5C8A"],  # bleu : B domine
                    [0.5, "#f4f4f4"],  # équilibre
                    [1.0, "#B23A48"],  # rouge : A domine
                ],
                zmid=50,
                zmin=0,
                zmax=100,
                showscale=True,
                colorbar=dict(
                    title=f"% victoires<br>{name_a}",
                    tickvals=[0, 25, 50, 75, 100],
                    ticktext=["0 %", "25 %", "50 %", "75 %", "100 %"],
                ),
                hovertemplate="<b>%{x}</b><br>%{text}<extra></extra>",
            )
        )
        fig_heat.update_layout(
            title="Domination relative par surface",
            height=180,
            margin=dict(l=140, r=20, t=50, b=20),
        )
        apply_tennis_theme(fig_heat)
        st.plotly_chart(fig_heat, use_container_width=True)
        st.caption(
            "🔴 = surface où le premier joueur domine · 🔵 = surface où le second domine. "
            "La cellule affiche le bilan brut et le % de victoires."
        )

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
