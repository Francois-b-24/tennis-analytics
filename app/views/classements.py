"""Classements Elo (global ou par surface) — absorbe l'ancienne page « Top 20 »."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components._bootstrap import data_key, init_app
from components.queries import elo_ranking
from components.widgets import (
    circuit_selectbox,
    country_flag,
    df_styled,
    format_date_long,
    page_header,
    section,
    to_date,
)

_ROOT, _CONNECTION = init_app(__file__)
_DATA_KEY = data_key(_ROOT)

SURFACES = {
    "Global": "elo_global",
    "Dur": "elo_hard",
    "Terre battue": "elo_clay",
    "Gazon": "elo_grass",
}

circuit = circuit_selectbox()

page_header(
    "Classements Elo",
    subtitle=(
        "Le rating Elo évolue après chaque match selon la force de l'adversaire : "
        "il mesure le niveau réel plus finement que le classement officiel."
    ),
)

controls = st.columns([4, 2, 2], vertical_alignment="bottom")
surface_label = controls[0].segmented_control(
    "Surface",
    list(SURFACES),
    default="Global",
    required=True,
    key="classement_surface",
)
top_n = controls[1].selectbox("Joueurs affichés", [10, 20, 50, 100], index=1, key="classement_top")
include_inactive = controls[2].toggle(
    "Inclure les inactifs",
    value=False,
    help="Par défaut, seuls les joueurs ayant joué dans les 12 derniers mois sont classés.",
)
surface_col = SURFACES[surface_label or "Global"]

circuits = ["ATP", "WTA"] if circuit == "Tous" else [circuit]
tabs = st.tabs(circuits) if len(circuits) > 1 else [st.container()]
for tab, circ in zip(tabs, circuits, strict=True):
    with tab:
        ranking = elo_ranking(_DATA_KEY, circ, surface_col, top_n, include_inactive)
        if ranking.empty:
            st.info("Classement indisponible.")
            continue
        table = pd.DataFrame(
            {
                "Rang": ranking["rang"],
                "Joueur": [
                    f"{country_flag(i)} {n}"
                    for i, n in zip(ranking["ioc"], ranking["joueur"], strict=True)
                ],
                "Elo global": ranking["elo_global"],
                "Elo dur": ranking["elo_hard"],
                "Elo terre": ranking["elo_clay"],
                "Elo gazon": ranking["elo_grass"],
                "Forme": ranking["forme"],
                "Classement officiel": ranking["rang_officiel"].astype("Int64"),
                "Dernier match": to_date(ranking["last_match_date"]),
            }
        )
        df_styled(
            table,
            height=min(38 * (len(table) + 1), 760),
            column_config={
                "Forme": st.column_config.TextColumn(
                    help="5 derniers matchs, du plus ancien au plus récent (V/D)"
                ),
                "Classement officiel": st.column_config.NumberColumn(
                    format="%d", help="Classement ATP/WTA le plus récent (top 150 via ESPN)"
                ),
            },
        )
        leader = ranking.iloc[0]
        st.caption(
            f"N°1 {circ} ({surface_label.lower()}) : {leader['joueur']}, "
            f"{int(leader[surface_col])} points Elo · dernier match le "
            f"{format_date_long(int(leader['last_match_date']))}."
        )

section("Comprendre le classement", level=3)
st.markdown(
    "Repères actuels (joueurs actifs, ATP comme WTA) : environ **1 500** au 200e rang, "
    "**1 650** au 50e, **1 750** au 20e, **1 800** au 10e ; au-delà de **1 950**, seuls "
    "les tout meilleurs. Un joueur qui ne joue plus garde son dernier rating, d'où le "
    "filtre sur les 12 derniers mois."
)
st.page_link(
    "views/methodologie.py", label="Méthode de calcul détaillée", icon=":material/menu_book:"
)
