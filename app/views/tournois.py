"""Tournois : palmarès, joueurs les plus titrés et parcours d'un joueur par édition."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components._bootstrap import data_key, init_app
from components.plotly_theme import ACCENT, apply_tennis_theme
from components.queries import ROUND_ORDER_SQL, tournaments_for_circuit
from components.widgets import (
    circuit_selectbox,
    country_flag,
    df_styled,
    kpi_row,
    level_fr,
    page_header,
    round_fr,
    section,
    surface_fr,
)

_ROOT, _CONNECTION = init_app(__file__)
_DATA_KEY = data_key(_ROOT)


@st.cache_data(ttl=3600, show_spinner=False)
def _finals(cache_key: str, tourney: str, circuit: str) -> pd.DataFrame:
    return _CONNECTION.execute(
        """
        SELECT CAST(tourney_date // 10000 AS INT) AS annee, surface, tourney_level,
               winner_name AS vainqueur, winner_ioc, loser_name AS finaliste, score
        FROM v_matches
        WHERE tourney_name = ? AND circuit = ? AND round = 'F'
        ORDER BY tourney_date DESC
        """,
        [tourney, circuit],
    ).df()


@st.cache_data(ttl=3600, show_spinner=False)
def _default_tournament(cache_key: str, circuit: str) -> str | None:
    row = _CONNECTION.execute(
        """
        SELECT tourney_name FROM v_matches
        WHERE circuit = ? AND tourney_level = 'G' AND round = 'F'
        ORDER BY tourney_date DESC LIMIT 1
        """,
        [circuit],
    ).fetchone()
    return row[0] if row else None


@st.cache_data(ttl=3600, show_spinner=False)
def _duration_by_year(cache_key: str, tourney: str, circuit: str) -> pd.DataFrame:
    return _CONNECTION.execute(
        """
        SELECT CAST(tourney_date // 10000 AS INT) AS annee,
               ROUND(AVG(minutes) FILTER (WHERE minutes > 0 AND minutes < 400)) AS duree_moy,
               ROUND(AVG(w_ace + l_ace), 1) AS aces
        FROM v_matches
        WHERE tourney_name = ? AND circuit = ?
        GROUP BY annee HAVING COUNT(minutes) > 0
        ORDER BY annee
        """,
        [tourney, circuit],
    ).df()


@st.cache_data(ttl=3600, show_spinner=False)
def _participants(cache_key: str, tourney: str, circuit: str, year: int) -> pd.DataFrame:
    return _CONNECTION.execute(
        """
        SELECT DISTINCT player_id, full_name FROM (
            SELECT winner_id AS player_id, winner_name AS full_name, tourney_name, circuit,
                   tourney_date FROM v_matches
            UNION ALL
            SELECT loser_id, loser_name, tourney_name, circuit, tourney_date FROM v_matches
        )
        WHERE tourney_name = ? AND circuit = ? AND tourney_date // 10000 = ?
          AND TRIM(full_name) <> ''
        ORDER BY full_name
        """,
        [tourney, circuit, year],
    ).df()


@st.cache_data(ttl=3600, show_spinner=False)
def _player_run(
    cache_key: str, tourney: str, circuit: str, year: int, player_id: int
) -> pd.DataFrame:
    return _CONNECTION.execute(
        f"""
        SELECT round,
               CASE WHEN winner_id = ? THEN 'Victoire' ELSE 'Défaite' END AS resultat,
               CASE WHEN winner_id = ? THEN loser_name ELSE winner_name END AS adversaire,
               score
        FROM v_matches
        WHERE tourney_name = ? AND circuit = ? AND tourney_date // 10000 = ?
          AND (winner_id = ? OR loser_id = ?)
        ORDER BY {ROUND_ORDER_SQL}
        """,
        [player_id, player_id, tourney, circuit, year, player_id, player_id],
    ).df()


circuit = circuit_selectbox(include_all=False)
page_header("Tournois", subtitle="L'histoire de chaque tournoi depuis 2010.")
if st.session_state.get("circuit") == "Tous":
    st.caption(
        "Circuit affiché : ATP. Choisissez WTA dans la barre latérale pour les tournois féminins."
    )

names = tournaments_for_circuit(_DATA_KEY, circuit)
if not names:
    st.info("Aucun tournoi pour ce circuit.")
    st.stop()
default = _default_tournament(_DATA_KEY, circuit)
tourney = st.selectbox(
    "Tournoi",
    names,
    index=names.index(default) if default in names else 0,
    key=f"tournoi_{circuit}",
    help="Tapez pour rechercher",
)

finals = _finals(_DATA_KEY, tourney, circuit)
if finals.empty:
    st.info("Aucune finale enregistrée pour ce tournoi.")
    st.stop()

titles = finals.groupby("vainqueur").size().sort_values(ascending=False)
last = finals.iloc[0]
kpi_row(
    [
        {
            "label": "Dernier vainqueur",
            "value": last["vainqueur"],
            "delta": str(last["annee"]),
            "delta_dir": "neutral",
        },
        {
            "label": "Le plus titré",
            "value": titles.index[0],
            "delta": f"{titles.iloc[0]} titre(s)",
            "delta_dir": "neutral",
        },
        {"label": "Catégorie", "value": level_fr(last["tourney_level"])},
        {"label": "Surface", "value": surface_fr(last["surface"])},
    ],
    columns=2,
)

tab_finals, tab_titles, tab_trends, tab_run = st.tabs(
    ["Palmarès", "Les plus titrés", "Évolution", "Parcours d'un joueur"]
)

with tab_finals:
    df_styled(
        pd.DataFrame(
            {
                "Année": finals["annee"],
                "Vainqueur": [
                    f"{country_flag(i)} {n}"
                    for i, n in zip(finals["winner_ioc"], finals["vainqueur"], strict=True)
                ],
                "Finaliste": finals["finaliste"],
                "Score": finals["score"],
            }
        ),
        height=min(38 * (len(finals) + 1), 560),
    )

with tab_titles:
    top = titles.head(10).sort_values()
    fig = go.Figure(
        go.Bar(
            x=top.values,
            y=top.index,
            orientation="h",
            marker_color=ACCENT,
            text=top.values,
            textposition="outside",
        )
    )
    fig.update_xaxes(title_text="Titres", dtick=1)
    fig.update_layout(hovermode="y")
    st.plotly_chart(apply_tennis_theme(fig, height=60 + 32 * len(top)), width="stretch")

with tab_trends:
    durations = _duration_by_year(_DATA_KEY, tourney, circuit)
    if durations.empty:
        st.info("Pas de statistiques de durée pour ce tournoi.")
    else:
        metric = st.segmented_control(
            "Indicateur",
            ["Durée moyenne (min)", "Aces par match"],
            default="Durée moyenne (min)",
            required=True,
            key="tournoi_metric",
        )
        col = "duree_moy" if metric.startswith("Durée") else "aces"
        fig = go.Figure(
            go.Scatter(
                x=durations["annee"],
                y=durations[col],
                mode="lines+markers",
                line=dict(color=ACCENT, width=2.5),
                name=metric,
            )
        )
        fig.update_yaxes(title_text=metric)
        st.plotly_chart(apply_tennis_theme(fig, height=320), width="stretch")
        st.caption("Statistiques détaillées disponibles jusqu'au 25/05/2026.")

with tab_run:
    years = finals["annee"].tolist()
    col_year, col_player = st.columns([1, 2])
    year = col_year.selectbox("Édition", years, key=f"run_year_{circuit}")
    entrants = _participants(_DATA_KEY, tourney, circuit, int(year))
    if entrants.empty:
        st.info("Aucun participant pour cette édition.")
    else:
        champion = finals.loc[finals["annee"] == year, "vainqueur"]
        names_list = entrants["full_name"].tolist()
        default_idx = (
            names_list.index(champion.iloc[0])
            if not champion.empty and champion.iloc[0] in names_list
            else 0
        )
        chosen = col_player.selectbox(
            "Joueur", names_list, index=default_idx, key=f"run_player_{circuit}"
        )
        pid = int(entrants.loc[entrants["full_name"] == chosen, "player_id"].iloc[0])
        run = _player_run(_DATA_KEY, tourney, circuit, int(year), pid)
        section(f"{chosen} à {tourney} {year}", level=3)
        df_styled(
            pd.DataFrame(
                {
                    "Tour": run["round"].map(round_fr),
                    "Résultat": run["resultat"],
                    "Adversaire": run["adversaire"],
                    "Score": run["score"],
                }
            )
        )
