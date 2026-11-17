"""Fiche joueur : Elo par surface, bilan, évolution et derniers matchs."""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components._bootstrap import data_key, init_app
from components.plotly_theme import (
    LOSS_COLOR,
    SURFACE_COLORS,
    SURFACE_DASH,
    WIN_COLOR,
    apply_tennis_theme,
)
from components.queries import player_options, top_player_ids
from components.widgets import (
    circuit_selectbox,
    country_flag,
    df_styled,
    disambiguate_player_labels,
    format_date_dd_mm_yyyy,
    format_elo,
    kpi_row,
    page_header,
    player_selectbox,
    round_fr,
    section,
    surface_fr,
    to_date,
)

_ROOT, _CONNECTION = init_app(__file__)
_DATA_KEY = data_key(_ROOT)


@st.cache_data(ttl=3600, show_spinner=False)
def _identity(cache_key: str, player_id: int) -> pd.DataFrame:
    return _CONNECTION.execute(
        """
        SELECT p.name_first, p.name_last, p.ioc AS pays, p.dob, p.hand, p.height, p.circuit,
               e.elo_global, e.elo_hard, e.elo_clay, e.elo_grass, e.last_match_date,
               (SELECT arg_max(rank, ranking_date) FROM v_rankings r
                 WHERE r.player = p.player_id) AS rang_officiel
        FROM v_players p
        LEFT JOIN v_elo_latest e ON p.player_id = e.player_id
        WHERE p.player_id = ?
        LIMIT 1
        """,
        [player_id],
    ).df()


@st.cache_data(ttl=3600, show_spinner=False)
def _career_stats(cache_key: str, player_id: int) -> pd.DataFrame:
    return _CONNECTION.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wins,
            COUNT(DISTINCT tourney_id) AS tournaments,
            SUM(CASE WHEN winner_id = ? AND round = 'F' THEN 1 ELSE 0 END) AS titles,
            SUM(CASE WHEN tourney_date >= (SELECT MAX(tourney_date) // 10000 * 10000 FROM v_matches)
                     AND winner_id = ? THEN 1 ELSE 0 END) AS wins_season,
            SUM(CASE WHEN tourney_date >= (SELECT MAX(tourney_date) // 10000 * 10000 FROM v_matches)
                     THEN 1 ELSE 0 END) AS total_season,
            ROUND(AVG(CASE WHEN winner_id = ? THEN w_ace ELSE l_ace END), 1) AS avg_aces,
            ROUND(AVG(minutes) FILTER (WHERE minutes > 0 AND minutes < 400), 0) AS avg_duration
        FROM v_matches
        WHERE winner_id = ? OR loser_id = ?
        """,
        [player_id] * 6,
    ).df()


@st.cache_data(ttl=3600, show_spinner=False)
def _surface_stats(cache_key: str, player_id: int) -> pd.DataFrame:
    return _CONNECTION.execute(
        """
        SELECT surface,
               SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN loser_id  = ? THEN 1 ELSE 0 END) AS losses
        FROM v_matches
        WHERE (winner_id = ? OR loser_id = ?) AND surface IN ('Hard', 'Clay', 'Grass')
        GROUP BY surface
        ORDER BY wins + losses DESC
        """,
        [player_id] * 4,
    ).df()


@st.cache_data(ttl=3600, show_spinner=False)
def _elo_history(cache_key: str, player_id: int) -> pd.DataFrame:
    df = _CONNECTION.execute(
        """
        SELECT tourney_date, elo_global, elo_hard, elo_clay, elo_grass
        FROM v_elo_history WHERE player_id = ? ORDER BY tourney_date
        """,
        [player_id],
    ).df()
    if not df.empty:
        df["date"] = to_date(df["tourney_date"])
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def _recent_matches(cache_key: str, player_id: int, limit: int = 20) -> pd.DataFrame:
    return _CONNECTION.execute(
        """
        SELECT COALESCE(match_date, tourney_date) AS jour, tourney_name, surface, round,
               CASE WHEN winner_id = ? THEN 'Victoire' ELSE 'Défaite' END AS resultat,
               CASE WHEN winner_id = ? THEN loser_name ELSE winner_name END AS adversaire,
               CASE WHEN winner_id = ? THEN loser_ioc ELSE winner_ioc END AS adversaire_ioc,
               score
        FROM v_matches
        WHERE winner_id = ? OR loser_id = ?
        ORDER BY jour DESC, tourney_date DESC
        LIMIT ?
        """,
        [player_id] * 5 + [limit],
    ).df()


def _num(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


page_header("Joueurs", subtitle="Fiche détaillée : niveau par surface, bilan et forme récente.")
circuit = circuit_selectbox()

players = player_options(_DATA_KEY, circuit)
if players.empty:
    st.warning("Aucun joueur disponible pour ce circuit.")
    st.stop()
players = disambiguate_player_labels(players)
defaults = top_player_ids(_DATA_KEY, circuit, 1)
player_id = player_selectbox(
    "Joueur",
    players,
    key=f"joueurs_player_{circuit}",
    default_player_id=defaults[0] if defaults else None,
)
if player_id is None:
    st.stop()

identity = _identity(_DATA_KEY, player_id)
if identity.empty:
    st.error("Données introuvables pour ce joueur.")
    st.stop()
row = identity.iloc[0]
name = f"{row['name_first'] or ''} {row['name_last'] or ''}".strip()

facts = [f"{country_flag(row['pays'])} {row['pays'] or '—'}", row["circuit"]]
if _num(row["dob"]):
    facts.append(f"né(e) le {format_date_dd_mm_yyyy(int(row['dob']))}")
if row["hand"] in ("R", "L"):
    facts.append("droitier" if row["hand"] == "R" else "gaucher")
if _num(row["height"]):
    facts.append(f"{int(row['height'])} cm")
st.subheader(name, anchor=False)
st.caption(" · ".join(str(f) for f in facts))

career = _career_stats(_DATA_KEY, player_id).iloc[0]
total = int(career["total"] or 0)
wins = int(career["wins"] or 0)
season_total = int(career["total_season"] or 0)
season_wins = int(career["wins_season"] or 0)
surfaces = {"Dur": row["elo_hard"], "Terre battue": row["elo_clay"], "Gazon": row["elo_grass"]}
valid = {k: v for k, v in surfaces.items() if _num(v)}
best_surface = max(valid, key=valid.get) if valid else "—"
rank = _num(row["rang_officiel"])

kpi_row(
    [
        {
            "label": "Elo global",
            "value": format_elo(row["elo_global"]),
            "help": "Niveau estimé, mis à jour après chaque match",
        },
        {
            "label": "Meilleure surface",
            "value": best_surface,
            "delta": f"Elo {format_elo(valid.get(best_surface))}" if valid else None,
            "delta_dir": "neutral",
        },
        {
            "label": "Rang officiel",
            "value": f"n°{int(rank)}" if rank else "—",
            "help": "Dernier classement ATP/WTA connu",
        },
        {
            "label": "Saison",
            "value": f"{season_wins}–{season_total - season_wins}" if season_total else "—",
            "help": "Victoires–défaites depuis le 1er janvier",
        },
    ]
)

tab_elo, tab_surface, tab_matches, tab_career = st.tabs(
    ["Évolution Elo", "Par surface", "Derniers matchs", "Carrière"]
)

with tab_elo:
    history = _elo_history(_DATA_KEY, player_id)
    if history.empty:
        st.info("Pas encore d'historique Elo pour ce joueur.")
    else:
        fig = go.Figure()
        for col, label in (
            ("elo_global", "Global"),
            ("elo_hard", "Dur"),
            ("elo_clay", "Terre battue"),
            ("elo_grass", "Gazon"),
        ):
            fig.add_trace(
                go.Scatter(
                    x=history["date"],
                    y=history[col],
                    name=label,
                    mode="lines",
                    line=dict(
                        color=SURFACE_COLORS[label],
                        dash=SURFACE_DASH[label],
                        width=2.5 if label == "Global" else 1.6,
                    ),
                    visible=True if label == "Global" else "legendonly",
                )
            )
        fig.update_yaxes(title_text="Elo")
        st.plotly_chart(apply_tennis_theme(fig, height=380), width="stretch")
        st.caption("Cliquez sur une surface dans la légende pour l'afficher.")

with tab_surface:
    by_surface = _surface_stats(_DATA_KEY, player_id)
    if by_surface.empty:
        st.info("Aucun match sur les surfaces principales.")
    else:
        by_surface["surface_fr"] = by_surface["surface"].map(surface_fr)
        by_surface["pct"] = by_surface["wins"] / (by_surface["wins"] + by_surface["losses"])
        fig = go.Figure(
            [
                go.Bar(
                    name="Victoires",
                    x=by_surface["surface_fr"],
                    y=by_surface["wins"],
                    marker_color=WIN_COLOR,
                    text=[f"{p:.0%}" for p in by_surface["pct"]],
                    textposition="outside",
                ),
                go.Bar(
                    name="Défaites",
                    x=by_surface["surface_fr"],
                    y=by_surface["losses"],
                    marker_color=LOSS_COLOR,
                    marker_pattern_shape="/",
                ),
            ]
        )
        fig.update_layout(barmode="group", hovermode="x")
        st.plotly_chart(apply_tennis_theme(fig, height=340), width="stretch")
        st.caption("Pourcentage de victoires affiché au-dessus de chaque surface.")

with tab_matches:
    recent = _recent_matches(_DATA_KEY, player_id)
    if recent.empty:
        st.info("Aucun match.")
    else:
        df_styled(
            pd.DataFrame(
                {
                    "Date": to_date(recent["jour"]),
                    "Tournoi": recent["tourney_name"],
                    "Surface": recent["surface"].map(surface_fr),
                    "Tour": recent["round"].map(round_fr),
                    "Résultat": recent["resultat"],
                    "Adversaire": [
                        f"{country_flag(i)} {n}"
                        for i, n in zip(recent["adversaire_ioc"], recent["adversaire"], strict=True)
                    ],
                    "Score": recent["score"],
                }
            )
        )

with tab_career:
    avg_aces = _num(career["avg_aces"])
    avg_duration = _num(career["avg_duration"])
    kpi_row(
        [
            {
                "label": "Bilan depuis 2010",
                "value": f"{wins} V – {total - wins} D",
                "delta": f"{wins / total:.0%} de victoires" if total else None,
                "delta_dir": "neutral",
            },
            {"label": "Titres", "value": int(career["titles"] or 0)},
            {"label": "Tournois joués", "value": int(career["tournaments"] or 0)},
            {
                "label": "Aces par match",
                "value": f"{avg_aces:.1f}".replace(".", ",") if avg_aces is not None else "—",
                "help": "Statistiques de service disponibles jusqu'au 25/05/2026",
            },
        ]
    )
    if avg_duration:
        st.caption(f"Durée moyenne d'un match : {int(avg_duration)} min (jusqu'au 25/05/2026).")

section("Comparer avec un autre joueur", level=3)
st.page_link(
    "views/face_a_face.py", label="Ouvrir le face-à-face", icon=":material/compare_arrows:"
)
