"""Page Tournois : palmarès, top vainqueurs et durée des matchs par tournoi."""

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

from components.plotly_theme import (
    TENNIS_CLAY,
    TENNIS_GREEN,
    TENNIS_HARD,
    TENNIS_LINE,
    apply_tennis_theme,
)
from components.queries import tournaments_for_circuit
from components.widgets import (
    circuit_selectbox,
    df_styled,
    inject_global_css,
    kpi_row,
    page_header,
    section,
)
from db.duckdb_session import create_connection

st.set_page_config(page_title="Tournois — Tennis Analytics", layout="wide")
inject_global_css()

SURF_COLORS = {"Hard": TENNIS_HARD, "Clay": TENNIS_CLAY, "Grass": TENNIS_GREEN}


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return create_connection(_ROOT)


@st.cache_data(show_spinner=False)
def _palmares(_root: str, tourney: str, circuit: str) -> pd.DataFrame:
    return (
        _connection()
        .execute(
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
        )
        .df()
    )


@st.cache_data(show_spinner=False)
def _top_winners(_root: str, tourney: str, circuit: str) -> pd.DataFrame:
    return (
        _connection()
        .execute(
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
        )
        .df()
    )


@st.cache_data(show_spinner=False)
def _duration_by_year(_root: str, tourney: str, circuit: str) -> pd.DataFrame:
    return (
        _connection()
        .execute(
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
        )
        .df()
    )


@st.cache_data(show_spinner=False)
def _surface_breakdown(_root: str, tourney: str, circuit: str) -> pd.DataFrame:
    return (
        _connection()
        .execute(
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
        )
        .df()
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────
circuit = circuit_selectbox(key="tourn_circuit", include_all=False, default="ATP")

page_header(
    "Tournois",
    subtitle=(
        "Histoire d'un tournoi : palmarès des finales, joueurs les plus titrés, "
        "évolution de la durée moyenne des matchs et répartition par surface."
    ),
    icon="🏆",
)

tournois = tournaments_for_circuit(str(_ROOT), circuit)
if not tournois:
    st.warning("Aucun tournoi disponible. Lancez l'ingestion pour construire les parquets.")
    st.stop()

tourney = st.selectbox(
    "Sélectionner un tournoi",
    tournois,
    key="tourn_select",
    help="💡 Tapez pour filtrer",
    placeholder="Choisir un tournoi…",
)

# ── Section A — Palmarès ──────────────────────────────────────────────────────
section(f"Palmarès — {tourney} ({circuit})", level=3)

palmares = _palmares(str(_ROOT), tourney, circuit)

if palmares.empty:
    st.info("Aucune finale disponible pour ce tournoi dans les données.")
else:
    df_styled(
        palmares.rename(
            columns={
                "annee": "Année",
                "surface": "Surface",
                "niveau": "Niveau",
                "vainqueur": "Vainqueur",
                "finaliste": "Finaliste",
                "score": "Score",
                "minutes": "Durée (min)",
            }
        )
    )

# ── Section B — Top vainqueurs ────────────────────────────────────────────────
top_w = _top_winners(str(_ROOT), tourney, circuit)

if not top_w.empty:
    section("Top vainqueurs", level=3, divider_before=True)
    fig_top = go.Figure(
        go.Bar(
            x=top_w["titres"],
            y=top_w["winner_name"],
            orientation="h",
            marker_color=TENNIS_HARD,
            text=top_w["titres"],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Titres : %{x}<extra></extra>",
        )
    )
    fig_top.update_layout(
        title=f"Top {len(top_w)} vainqueurs — {tourney}",
        xaxis_title="Titres",
        yaxis=dict(autorange="reversed"),
        height=max(350, len(top_w) * 40),
    )
    apply_tennis_theme(fig_top)
    st.plotly_chart(fig_top, use_container_width=True)

    with st.expander("Tableau détaillé"):
        df_styled(
            top_w.rename(
                columns={
                    "winner_name": "Joueur",
                    "titres": "Titres",
                    "premiere": "1ère victoire",
                    "derniere": "Dernière victoire",
                }
            )
        )

# ── Section C — Durée par année ───────────────────────────────────────────────
dur_df = _duration_by_year(str(_ROOT), tourney, circuit)

if not dur_df.empty and dur_df["duree_moy"].notna().any():
    section("Durée moyenne des matchs par année", level=3, divider_before=True)
    fig_dur = go.Figure(
        go.Scatter(
            x=dur_df["annee"],
            y=dur_df["duree_moy"],
            mode="lines+markers",
            line=dict(color=TENNIS_LINE, width=2),
            marker=dict(size=6, color=TENNIS_HARD),
            name="Durée moyenne (min)",
            hovertemplate="%{x} : %{y:.0f} min<extra></extra>",
        )
    )
    fig_dur.update_layout(
        title=f"Durée moyenne des matchs — {tourney}",
        xaxis_title="Année",
        yaxis_title="Durée (minutes)",
        hovermode="x unified",
    )
    apply_tennis_theme(fig_dur)
    st.plotly_chart(fig_dur, use_container_width=True)

# ── Section D — Répartition par surface ──────────────────────────────────────
surf_df = _surface_breakdown(str(_ROOT), tourney, circuit)

if not surf_df.empty:
    section("Répartition par surface", level=3, divider_before=True)
    surf_colors = [SURF_COLORS.get(s, TENNIS_LINE) for s in surf_df["surface"]]
    fig_surf = go.Figure(
        go.Bar(
            x=surf_df["surface"],
            y=surf_df["matchs"],
            marker_color=surf_colors,
            text=surf_df["matchs"],
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Matchs : %{y}<extra></extra>",
        )
    )
    fig_surf.update_layout(
        title=f"Matchs par surface — {tourney}",
        xaxis_title="Surface",
        yaxis_title="Nombre de matchs",
    )
    apply_tennis_theme(fig_surf)
    st.plotly_chart(fig_surf, use_container_width=True)


# ── Section E — Parcours d'un joueur dans une édition ───────────────────────
section("Parcours d'un joueur dans une édition", level=3, divider_before=True)
st.caption(
    "Sélectionnez une année puis un joueur ayant disputé cette édition : tous "
    "ses matchs round par round (R128 → finale)."
)

ROUND_ORDER = {
    "Q1": -3,
    "Q2": -2,
    "Q3": -1,
    "RR": 0,
    "R128": 1,
    "R64": 2,
    "R32": 3,
    "R16": 4,
    "QF": 5,
    "SF": 6,
    "BR": 6,  # bronze match (rare)
    "F": 7,
    "W": 8,  # gagnant final, parfois noté ainsi
}


@st.cache_data(show_spinner=False)
def _editions(_root: str, tourney: str, circuit: str) -> list[int]:
    """Liste des années où le tournoi a été disputé."""
    sql = """
        SELECT DISTINCT CAST(tourney_date / 10000 AS INT) AS annee
        FROM v_matches
        WHERE tourney_name = ? AND circuit = ?
        ORDER BY annee DESC
    """
    try:
        df = _connection().execute(sql, [tourney, circuit]).df()
        return [int(a) for a in df["annee"].tolist()]
    except duckdb.Error:
        return []


@st.cache_data(show_spinner=False)
def _edition_participants(_root: str, tourney: str, circuit: str, year: int) -> pd.DataFrame:
    """Liste des joueurs ayant disputé une édition donnée (W ou L)."""
    sql = """
        SELECT player_id, full_name FROM (
            SELECT winner_id AS player_id, winner_name AS full_name
            FROM v_matches
            WHERE tourney_name = ? AND circuit = ?
              AND CAST(tourney_date / 10000 AS INT) = ?
            UNION
            SELECT loser_id, loser_name
            FROM v_matches
            WHERE tourney_name = ? AND circuit = ?
              AND CAST(tourney_date / 10000 AS INT) = ?
        )
        WHERE TRIM(full_name) <> ''
        ORDER BY full_name
    """
    try:
        return (
            _connection()
            .execute(sql, [tourney, circuit, year, tourney, circuit, year])
            .df()
            .drop_duplicates(subset=["player_id"])
        )
    except duckdb.Error:
        return pd.DataFrame(columns=["player_id", "full_name"])


@st.cache_data(show_spinner=False)
def _player_run(_root: str, tourney: str, circuit: str, year: int, player_id: int) -> pd.DataFrame:
    """Tous les matchs d'un joueur dans une édition, triés par round."""
    sql = """
        SELECT
            tourney_date,
            round,
            CASE WHEN winner_id = ? THEN 'V' ELSE 'D' END AS resultat,
            CASE WHEN winner_id = ? THEN loser_name  ELSE winner_name END AS adversaire,
            CASE WHEN winner_id = ? THEN loser_id    ELSE winner_id    END AS opponent_id,
            score,
            minutes,
            surface
        FROM v_matches
        WHERE tourney_name = ?
          AND circuit = ?
          AND CAST(tourney_date / 10000 AS INT) = ?
          AND (winner_id = ? OR loser_id = ?)
    """
    try:
        df = (
            _connection()
            .execute(
                sql, [player_id, player_id, player_id, tourney, circuit, year, player_id, player_id]
            )
            .df()
        )
    except duckdb.Error:
        return pd.DataFrame()
    if df.empty:
        return df
    df["round_order"] = df["round"].map(lambda r: ROUND_ORDER.get(str(r), 99))
    return df.sort_values("round_order").reset_index(drop=True)


editions = _editions(str(_ROOT), tourney, circuit)
if not editions:
    st.info("Aucune édition disponible pour ce tournoi.")
else:
    edcol, plcol = st.columns([1, 2])
    with edcol:
        year_choice = st.selectbox("Année", editions, key="tourn_run_year")
    participants = _edition_participants(str(_ROOT), tourney, circuit, year_choice)
    if participants.empty:
        st.info("Aucun participant trouvé pour cette édition.")
    else:
        labels_map = dict(zip(participants["full_name"], participants["player_id"], strict=False))
        with plcol:
            player_label = st.selectbox(
                "Joueur",
                list(labels_map.keys()),
                key="tourn_run_player",
                help="💡 Tapez pour rechercher",
                placeholder="Rechercher un joueur…",
            )
        player_id = int(labels_map[player_label])
        run = _player_run(str(_ROOT), tourney, circuit, year_choice, player_id)

        if run.empty:
            st.info(f"{player_label} n'a pas disputé cette édition.")
        else:
            # Résumé : nb matchs, victoires, round atteint
            n_wins = int((run["resultat"] == "V").sum())
            n_matches = len(run)
            final_round = run.iloc[-1]["round"]
            outcome = (
                "🏆 Champion"
                if (final_round == "F" and run.iloc[-1]["resultat"] == "V")
                else (
                    "🥈 Finaliste"
                    if (final_round == "F" and run.iloc[-1]["resultat"] == "D")
                    else f"Éliminé en {final_round}"
                )
            )

            kpi_row(
                [
                    {"label": "Matchs joués", "value": str(n_matches), "icon": "🎾"},
                    {"label": "Victoires", "value": f"{n_wins} / {n_matches}", "icon": "🏆"},
                    {"label": "Résultat", "value": outcome, "icon": "🥇"},
                ]
            )

            # Tableau du parcours
            display_run = run.copy()
            display_run["Durée"] = display_run["minutes"].map(
                lambda m: f"{int(m)} min" if pd.notna(m) else "—"
            )
            display_run = display_run.rename(
                columns={
                    "round": "Tour",
                    "resultat": "V/D",
                    "adversaire": "Adversaire",
                    "score": "Score",
                    "surface": "Surface",
                }
            )[["Tour", "V/D", "Adversaire", "Score", "Durée", "Surface"]]
            df_styled(display_run)
