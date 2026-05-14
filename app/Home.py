"""Point d'entrée Streamlit : accueil et métriques globales."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb
import streamlit as st
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")
os.environ.setdefault("ROOT_PATH", str(_ROOT))

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from db.duckdb_session import create_connection


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return create_connection(_ROOT)


def _safe_scalar(connection: duckdb.DuckDBPyConnection, sql: str) -> int | float | None:
    try:
        value = connection.execute(sql).fetchone()[0]
    except duckdb.Error:
        return None
    return value


st.set_page_config(page_title="Tennis Analytics", layout="wide")
st.title("Tennis Analytics Platform")
st.markdown(
    """
    **Plateforme personnelle d'analytics tennis (ATP/WTA)** : statistiques descriptives,
    ratings Elo maison, modèles de prédiction et insights tactiques (MVP).
    """
)

hero = st.container()
with hero:
    st.markdown("### Bienvenue")
    st.write(
        "Explorez les joueurs, affrontements direct (H2H), tournois, classements Elo, "
        "prédictions et insights depuis le menu des pages."
    )

connection = _connection()
col_a, col_b, col_c = st.columns(3)
with col_a:
    matches_count = int(_safe_scalar(connection, "SELECT COUNT(*) FROM v_matches;") or 0)
    st.metric("Matchs indexés", f"{matches_count:,}".replace(",", " "))
with col_b:
    players_count = int(
        _safe_scalar(connection, "SELECT COUNT(DISTINCT player_id) FROM v_players;") or 0
    )
    if players_count == 0:
        players_count = int(
            _safe_scalar(connection, "SELECT COUNT(DISTINCT winner_id) FROM v_matches;") or 0
        )
    st.metric("Joueurs (approx.)", f"{players_count:,}".replace(",", " "))
with col_c:
    last_date = _safe_scalar(connection, "SELECT MAX(tourney_date) FROM v_matches;")
    st.metric("Dernière date de match", str(last_date or "—"))

st.info(
    "Astuce : si les métriques sont vides, lancez `uv run tennis-ingest` "
    "puis `uv run python -m transformation.build_elo`.",
)

st.divider()
st.markdown("### Pages disponibles")
st.page_link("pages/1_Joueurs.py", label="Joueurs")
st.page_link("pages/2_Face_a_Face.py", label="Face à Face")
st.page_link("pages/3_Tournois.py", label="Tournois")
st.page_link("pages/4_Classements_Elo.py", label="Classements Elo")
st.page_link("pages/5_Predictions.py", label="Prédictions")
st.page_link("pages/6_Insights.py", label="Insights")
