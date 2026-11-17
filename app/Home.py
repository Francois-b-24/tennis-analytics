"""Point d'entrée Streamlit : navigation, barre latérale commune, contrôle des données.

Chaque page vit dans `app/views/`. Les `url_path` historiques sont conservés
(`/Joueurs`, `/Classements_Elo`…) pour ne casser aucun favori ; les pages
supprimées redirigent vers leur remplaçante.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from components._bootstrap import init_app, load_metadata

_ROOT, _CONNECTION = init_app(__file__)

import streamlit as st

from components.widgets import freshness_panel, inject_global_css, safe_scalar

st.set_page_config(
    page_title="Tennis Analytics",
    page_icon=":material/sports_tennis:",
    layout="wide",
    initial_sidebar_state="auto",
)
inject_global_css()

VIEWS = Path(__file__).resolve().parent / "views"


def _page(
    file: str,
    title: str,
    icon: str,
    url_path: str | None = None,
    *,
    default: bool = False,
    hidden: bool = False,
) -> st.Page:
    return st.Page(
        VIEWS / file,
        title=title,
        icon=f":material/{icon}:",
        url_path=url_path,
        default=default,
        visibility="hidden" if hidden else "visible",
    )


PAGES = {
    "Suivre": [
        _page("accueil.py", "Accueil", "home", default=True),
        _page("resultats.py", "Résultats", "scoreboard", "Resultats"),
        _page("classements.py", "Classements", "leaderboard", "Classements_Elo"),
        _page("redirect_top20.py", "Top 20", "leaderboard", "Top_20_actuel", hidden=True),
    ],
    "Explorer": [
        _page("joueurs.py", "Joueurs", "person", "Joueurs"),
        _page("face_a_face.py", "Face-à-face", "compare_arrows", "Face_a_Face"),
        _page("tournois.py", "Tournois", "emoji_events", "Tournois"),
    ],
    "Analyser": [
        _page("tendances.py", "Tendances", "insights", "Insights"),
        _page("styles.py", "Styles de jeu", "scatter_plot", "Profils_et_Styles"),
        _page("predictions.py", "Prédictions", "query_stats", "Predictions"),
    ],
    "À propos": [
        _page("methodologie.py", "Méthodologie", "menu_book", "Definition_Elo"),
    ],
}

navigation = st.navigation(PAGES, position="top")

# Garde-fou : sans données, aucune page n'a de sens.
if not safe_scalar(_CONNECTION, "SELECT COUNT(*) FROM v_matches", default=0):
    st.error(
        "Les données ne sont pas disponibles pour le moment. "
        "Réessayez dans quelques minutes ; si le problème persiste, redémarrez l'application."
    )
    st.stop()

navigation.run()

# Après la page : l'encart se place sous le choix du circuit dans la barre latérale.
freshness_panel(load_metadata(_ROOT))
