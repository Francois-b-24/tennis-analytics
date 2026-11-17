"""Résultats : tableau d'un tournoi récent tour par tour, et palmarès de la saison."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components._bootstrap import data_key, init_app
from components.queries import recent_tournaments, season_champions, tournament_matches
from components.widgets import (
    PROVISIONAL_NOTE,
    circuit_selectbox,
    country_flag,
    df_styled,
    format_date_long,
    level_fr,
    mark_provisional,
    page_header,
    round_fr,
    section,
    surface_fr,
    to_date,
)

_ROOT, _CONNECTION = init_app(__file__)
_DATA_KEY = data_key(_ROOT)

circuit = circuit_selectbox()

page_header(
    "Résultats",
    subtitle="Les tournois des dernières semaines, tour par tour, et les vainqueurs de la saison.",
)

tournaments = recent_tournaments(_DATA_KEY, circuit, 40)
if tournaments.empty:
    st.info("Aucun tournoi récent pour ce circuit.")
    st.stop()


def _label(row: pd.Series) -> str:
    state = "terminé" if isinstance(row["vainqueur"], str) else "en cours"
    return f"{row['tourney_name']} ({row['circuit']}) · {format_date_long(int(row['debut']))} · {state}"


labels = {row["tourney_id"]: _label(row) for _, row in tournaments.iterrows()}
tourney_id = st.selectbox(
    "Tournoi",
    list(labels),
    format_func=labels.get,
    key="resultats_tournoi",
    help="Tapez pour rechercher",
)
info = tournaments.loc[tournaments["tourney_id"] == tourney_id].iloc[0]

champion = info["vainqueur"] if isinstance(info["vainqueur"], str) else None
if champion:
    st.markdown(
        f":material/emoji_events: **{champion}** remporte le tournoi "
        f"(bat {info['finaliste']}, {info['score_finale']})."
    )
else:
    st.markdown(
        f":material/schedule: **En cours** · dernier tour joué : {round_fr(info['dernier_tour'])}."
    )
st.markdown(
    " ".join(
        [
            f":gray-badge[{level_fr(info['tourney_level'])}]",
            f":gray-badge[{surface_fr(info['surface'])}]",
            f":gray-badge[{int(info['matchs'])} matchs]",
        ]
    )
)
if info["provisoires"]:
    st.info(
        f"{int(info['provisoires'])} résultats sont provisoires (source ESPN) : ils seront "
        "confirmés à la prochaine publication de tennis-data.co.uk.",
        icon=":material/bolt:",
    )

matches = tournament_matches(_DATA_KEY, tourney_id)
section("Tableau", level=3)
if matches.empty:
    st.info("Aucun match pour ce tournoi.")
else:
    table = pd.DataFrame(
        {
            "Tour": matches["round"].map(round_fr),
            "Date": to_date(matches["jour"]),
            "Vainqueur": [
                f"{country_flag(i)} {n}"
                for i, n in zip(matches["winner_ioc"], matches["winner_name"], strict=True)
            ],
            "Battu(e)": [
                f"{country_flag(i)} {n}"
                for i, n in zip(matches["loser_ioc"], matches["loser_name"], strict=True)
            ],
            "Score": mark_provisional(matches["score"], matches["source"]),
        }
    )
    df_styled(table, height=min(35 * (len(table) + 1) + 3, 560))
    if (matches["source"] == "espn").any():
        st.caption(PROVISIONAL_NOTE)

# ── Palmarès de la saison ───────────────────────────────────────────────────
latest_year = int(tournaments["debut"].max()) // 10000
section(
    f"Vainqueurs {latest_year}",
    caption="Tournois du circuit principal (hors Coupe Davis et BJK Cup).",
)
champions = season_champions(_DATA_KEY, circuit, latest_year)
if champions.empty:
    st.info("Aucun tournoi terminé cette saison.")
else:
    df_styled(
        pd.DataFrame(
            {
                "Début": to_date(champions["debut"]),
                "Tournoi": champions["tourney_name"],
                "Circuit": champions["circuit"],
                "Catégorie": champions["tourney_level"].map(level_fr),
                "Surface": champions["surface"].map(surface_fr),
                "Vainqueur": [
                    f"{country_flag(i)} {n}"
                    for i, n in zip(champions["winner_ioc"], champions["vainqueur"], strict=True)
                ],
                "Finaliste": champions["finaliste"],
                "Score": champions["score"],
            }
        ),
        height=420,
    )
