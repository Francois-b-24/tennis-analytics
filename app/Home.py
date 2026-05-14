"""Point d'entrée Streamlit : accueil, métriques globales et navigation."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb
import streamlit as st
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
_APP_DIR = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")
os.environ.setdefault("ROOT_PATH", str(_ROOT))

if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from components.widgets import circuit_filter_sql, format_date_dd_mm_yyyy, safe_scalar
from db.duckdb_session import create_connection

st.set_page_config(
    page_title="Tennis Analytics",
    page_icon="🎾",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return create_connection(_ROOT)


connection = _connection()

# ── Sidebar ──────────────────────────────────────────────────────────────────
circuit = st.sidebar.selectbox("Circuit", ["Tous", "ATP", "WTA"], key="home_circuit")
cf = circuit_filter_sql(circuit)

# ── Hero ─────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <h1 style='margin-bottom:0'>🎾 Tennis Analytics</h1>
    <p style='color:#666;font-size:1.1rem;margin-top:4px'>
        Plateforme personnelle d'analyse ATP/WTA — statistiques, ratings Elo et prédictions ML
    </p>
    """,
    unsafe_allow_html=True,
)
st.divider()

# ── KPIs row 1 ───────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)

total_matches = int(
    safe_scalar(connection, f"SELECT COUNT(*) FROM v_matches WHERE 1=1 {cf}", default=0) or 0
)
total_players = int(
    safe_scalar(
        connection,
        f"SELECT COUNT(DISTINCT player_id) FROM v_players p WHERE 1=1 {cf.replace('circuit', 'p.circuit')}",
        default=0,
    )
    or 0
)
if total_players == 0:
    total_players = int(
        safe_scalar(
            connection,
            f"SELECT COUNT(DISTINCT winner_id) FROM v_matches WHERE 1=1 {cf}",
            default=0,
        )
        or 0
    )
total_tournois = int(
    safe_scalar(
        connection,
        f"SELECT COUNT(DISTINCT tourney_name) FROM v_matches WHERE 1=1 {cf}",
        default=0,
    )
    or 0
)

with col1:
    st.metric("Matchs indexés", f"{total_matches:,}".replace(",", " "))
with col2:
    st.metric("Joueurs", f"{total_players:,}".replace(",", " "))
with col3:
    st.metric("Tournois couverts", f"{total_tournois:,}".replace(",", " "))

# ── KPIs row 2 ───────────────────────────────────────────────────────────────
col4, col5, col6 = st.columns(3)

atp_matches = int(
    safe_scalar(connection, "SELECT COUNT(*) FROM v_matches WHERE circuit = 'ATP'", default=0) or 0
)
wta_matches = int(
    safe_scalar(connection, "SELECT COUNT(*) FROM v_matches WHERE circuit = 'WTA'", default=0) or 0
)
date_range = connection.execute(
    "SELECT MIN(tourney_date), MAX(tourney_date) FROM v_matches"
).fetchone()
min_date = format_date_dd_mm_yyyy(date_range[0]) if date_range else "—"
max_date = format_date_dd_mm_yyyy(date_range[1]) if date_range else "—"

with col4:
    st.metric("Matchs ATP", f"{atp_matches:,}".replace(",", " "))
with col5:
    st.metric("Matchs WTA", f"{wta_matches:,}".replace(",", " "))
with col6:
    st.metric("Période couverte", f"{min_date} → {max_date}")

st.divider()

# ── Encart pédagogique Elo ────────────────────────────────────────────────────
with st.expander("ℹ️ C'est quoi le rating Elo (utilisé partout dans l'app) ?"):
    st.markdown(
        """
        Le **rating Elo** attribue à chaque joueur un score reflétant son niveau actuel :
        plus c'est élevé, plus le joueur est fort. Initialement conçu pour les échecs,
        il est aujourd'hui largement utilisé au tennis (FiveThirtyEight, Tennis Abstract…).

        **Repères rapides :**
        - **2200+** : élite mondiale (Top 5)
        - **2000–2200** : Top 20
        - **1800–2000** : circuit pro
        - **1500** : valeur de départ pour tout nouveau joueur

        Chaque joueur a **4 ratings** : Global, Dur, Terre battue, Gazon (pour capter la
        spécialisation par surface). Les détails du modèle (facteur K adaptatif,
        décroissance d'inactivité, bonus Best-of-5) sont expliqués sur la page
        **Classements Elo**.
        """
    )

# ── Navigation cards ──────────────────────────────────────────────────────────
st.markdown("### Explorer l'application")

PAGES = [
    {
        "path": "pages/1_Joueurs.py",
        "title": "Joueurs",
        "icon": "👤",
        "desc": "Fiche joueur, stats carrière par surface, évolution Elo dans le temps et derniers matchs.",
    },
    {
        "path": "pages/2_Face_a_Face.py",
        "title": "Face à Face",
        "icon": "⚔️",
        "desc": "Bilan H2H, radar de style de jeu et favori Elo pour n'importe quelle paire de joueurs.",
    },
    {
        "path": "pages/3_Tournois.py",
        "title": "Tournois",
        "icon": "🏆",
        "desc": "Palmarès historique, top vainqueurs et durée des matchs pour chaque tournoi.",
    },
    {
        "path": "pages/4_Classements_Elo.py",
        "title": "Classements Elo",
        "icon": "📊",
        "desc": "Top N joueurs par rating Elo global ou par surface, avec comparaison multi-surface.",
    },
    {
        "path": "pages/5_Predictions.py",
        "title": "Prédictions",
        "icon": "🤖",
        "desc": "Probabilité de victoire ML (régression logistique calibrée) pour deux joueurs sur une surface.",
    },
    {
        "path": "pages/6_Insights.py",
        "title": "Insights",
        "icon": "💡",
        "desc": "Tendances long-terme : aces, double-fautes, durée des matchs et comparaison ATP/WTA.",
    },
]

row1 = st.columns(3)
row2 = st.columns(3)

for i, page in enumerate(PAGES):
    col = row1[i] if i < 3 else row2[i - 3]
    with col:
        with st.container(border=True):
            st.markdown(f"### {page['icon']} {page['title']}")
            st.caption(page["desc"])
            st.page_link(page["path"], label=f"Ouvrir {page['title']} →")
