"""Accueil : l'actualité du circuit en un coup d'œil (tournois, résultats, top Elo)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from components._bootstrap import data_key, init_app
from components.queries import elo_ranking, recent_results, recent_tournaments
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


page_header(
    "Tennis Analytics",
    subtitle="Résultats ATP et WTA, classements Elo par surface et analyses depuis 2010.",
)
circuit = circuit_selectbox()

# ── Tournois récents ────────────────────────────────────────────────────────
section("À la une", caption="Les derniers tournois, terminés ou en cours.")
tournaments = recent_tournaments(_DATA_KEY, circuit, 6)
if tournaments.empty:
    st.info("Aucun tournoi récent.")
else:
    cols = st.columns(3)
    for i, t in enumerate(tournaments.itertuples(index=False)):
        with cols[i % 3].container(border=True):
            st.markdown(f"**{t.tourney_name}** · {t.circuit}")
            st.caption(f"{level_fr(t.tourney_level)} · {surface_fr(t.surface)}")
            if isinstance(t.vainqueur, str) and t.vainqueur:
                st.markdown(f":material/emoji_events: **{t.vainqueur}**")
                st.caption(f"bat {t.finaliste} · {t.score_finale}")
            else:
                st.markdown(":material/schedule: **En cours**")
                st.caption(f"Dernier tour joué : {round_fr(t.dernier_tour)}")
            if t.provisoires:
                st.badge("Résultats provisoires", icon=":material/bolt:", color="orange")

# ── Derniers résultats ───────────────────────────────────────────────────────
section("Derniers résultats")
results = recent_results(_DATA_KEY, circuit, 12)
if results.empty:
    st.info("Aucun résultat.")
else:
    table = pd.DataFrame(
        {
            "Date": to_date(results["jour"]),
            "Tournoi": results["tourney_name"],
            "Tour": results["round"].map(round_fr),
            "Vainqueur": [
                f"{country_flag(i)} {n}"
                for i, n in zip(results["winner_ioc"], results["winner_name"], strict=True)
            ],
            "Battu(e)": [
                f"{country_flag(i)} {n}"
                for i, n in zip(results["loser_ioc"], results["loser_name"], strict=True)
            ],
            "Score": mark_provisional(results["score"], results["source"]),
        }
    )
    df_styled(table)
    if (results["source"] == "espn").any():
        st.caption(PROVISIONAL_NOTE)
    st.page_link("views/resultats.py", label="Tous les résultats", icon=":material/arrow_forward:")

# ── Top Elo ─────────────────────────────────────────────────────────────────
section(
    "Meilleurs joueurs du moment",
    caption="Classement Elo des joueurs actifs (au moins un match dans les 12 derniers mois).",
)
circuits = ["ATP", "WTA"] if circuit == "Tous" else [circuit]
cols = st.columns(len(circuits))
for col, circ in zip(cols, circuits, strict=True):
    with col:
        st.subheader(circ, anchor=False)
        top = elo_ranking(_DATA_KEY, circ, "elo_global", 5)
        if top.empty:
            st.info("Classement indisponible.")
            continue
        df_styled(
            pd.DataFrame(
                {
                    "Rang": top["rang"],
                    "Joueur": [
                        f"{country_flag(i)} {n}"
                        for i, n in zip(top["ioc"], top["joueur"], strict=True)
                    ],
                    "Elo": top["elo_global"],
                    "Forme": top["forme"],
                }
            ),
            column_config={
                "Forme": st.column_config.TextColumn(
                    help="5 derniers matchs, du plus ancien au plus récent (V = victoire, D = défaite)"
                )
            },
        )
st.page_link("views/classements.py", label="Classement complet", icon=":material/arrow_forward:")

last = results["jour"].max() if not results.empty else None
if last:
    st.caption(
        f"Dernier match enregistré : {format_date_long(int(last))} · page générée le {datetime.now():%d/%m/%Y à %H:%M}."
    )
