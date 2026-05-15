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

_SRC = _ROOT / "src"
for path in (_APP_DIR, _ROOT, _SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from components.widgets import circuit_filter_sql, format_date_dd_mm_yyyy, inject_global_css, safe_scalar
from db.duckdb_session import create_connection

st.set_page_config(
    page_title="Tennis Analytics",
    page_icon="🎾",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_global_css()


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return create_connection(_ROOT)


connection = _connection()

# ── Diagnostic : vérifier que les vues sont bien chargées ────────────────────
try:
    _check = connection.execute("SELECT COUNT(*) FROM v_matches").fetchone()
    if not _check or _check[0] == 0:
        st.error(
            "⚠️ Aucune donnée chargée — la vue `v_matches` est vide ou absente. "
            "Vérifiez que les fichiers `data/processed/*.parquet` sont bien présents "
            "dans le déploiement."
        )
        st.stop()
except Exception as e:
    st.error(f"⚠️ Erreur de chargement des données : {e}")
    st.info(
        "Sur Streamlit Cloud, cliquez sur **Manage app → Reboot app** pour vider le cache "
        "de connexion et recharger les parquets."
    )
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
circuit = st.sidebar.selectbox("Circuit", ["Tous", "ATP", "WTA"], key="home_circuit")
cf = circuit_filter_sql(circuit)

# ── Hero ──────────────────────────────────────────────────────────────────────
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

# ── KPIs row 1 ────────────────────────────────────────────────────────────────
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
    st.metric("Matchs indexés", f"{total_matches:,}".replace(",", " "))
with col2:
    st.metric("Joueurs", f"{total_players:,}".replace(",", " "))
with col3:
    st.metric("Tournois couverts", f"{total_tournois:,}".replace(",", " "))

# ── KPIs row 2 ────────────────────────────────────────────────────────────────
col4, col5, col6 = st.columns(3)

date_range = connection.execute(
    "SELECT MIN(tourney_date), MAX(tourney_date) FROM v_matches"
).fetchone()
min_date = format_date_dd_mm_yyyy(date_range[0]) if date_range else "—"
max_date = format_date_dd_mm_yyyy(date_range[1]) if date_range else "—"

last_atp = connection.execute(
    """
    SELECT tourney_name, tourney_date
    FROM v_matches
    WHERE circuit = 'ATP'
    ORDER BY tourney_date DESC
    LIMIT 1
    """
).fetchone()
last_wta = connection.execute(
    """
    SELECT tourney_name, tourney_date
    FROM v_matches
    WHERE circuit = 'WTA'
    ORDER BY tourney_date DESC
    LIMIT 1
    """
).fetchone()

last_atp_name = last_atp[0] if last_atp else "—"
last_atp_date = format_date_dd_mm_yyyy(last_atp[1]) if last_atp else ""
last_wta_name = last_wta[0] if last_wta else "—"
last_wta_date = format_date_dd_mm_yyyy(last_wta[1]) if last_wta else ""

with col4:
    st.metric("Periode couverte", f"{min_date} → {max_date}")
with col5:
    st.metric("Dernier tournoi ATP", last_atp_name, delta=last_atp_date, delta_color="off")
with col6:
    st.metric("Dernier tournoi WTA", last_wta_name, delta=last_wta_date, delta_color="off")

st.divider()

st.markdown(
    """
    <style>
    .elo-tooltip {
        position: relative;
        display: inline-block;
        color: #3A7D44;
        font-weight: 600;
        border-bottom: 1px dashed #3A7D44;
        cursor: help;
    }
    .elo-tooltip .elo-tip {
        visibility: hidden;
        opacity: 0;
        width: 300px;
        background: #1e2d24;
        color: #f0f7f2;
        font-size: 0.82rem;
        line-height: 1.6;
        border-radius: 8px;
        padding: 12px 14px;
        position: absolute;
        bottom: calc(100% + 8px);
        left: 50%;
        transform: translateX(-50%);
        box-shadow: 0 4px 20px rgba(0,0,0,0.25);
        transition: opacity 0.2s ease;
        z-index: 9999;
        pointer-events: none;
    }
    .elo-tooltip .elo-tip::after {
        content: "";
        position: absolute;
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        border: 6px solid transparent;
        border-top-color: #1e2d24;
    }
    .elo-tooltip:hover .elo-tip {
        visibility: visible;
        opacity: 1;
    }
    .info-band {
        background: linear-gradient(135deg, #f4f9f5 0%, #eaf3ec 100%);
        border-left: 4px solid #3A7D44;
        border-radius: 0 8px 8px 0;
        padding: 12px 16px;
        margin-bottom: 16px;
        color: #3a3a3a;
        font-size: 0.92rem;
        line-height: 1.6;
    }
    </style>

    <div class="info-band">
    🎾&nbsp; Bienvenue sur cette plateforme d'analyse tennis personnelle.
    Explorez les statistiques de carrière des joueurs ATP et WTA depuis 2010,
    comparez-les en face à face, consultez les classements
    <span class="elo-tooltip">Elo
        <span class="elo-tip">
            <strong>Rating Elo</strong><br>
            Système de notation qui mesure le niveau d'un joueur match après match.
            Battre un adversaire fort rapporte plus de points que battre un outsider.
            Chaque joueur dispose de 4 ratings : Global, Dur, Terre battue et Gazon.<br><br>
            <em>Repères : 1 500 = débutant · 1 800 = pro · 2 000 = Top 20 · 2 200+ = élite</em>
            <br><br>📖 <em>Voir la page « Définition Elo » pour le document complet.</em>
        </span>
    </span>
    par surface et simulez des probabilités de match grâce à un modèle ML calibré.
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Navigation cards ───────────────────────────────────────────────────────────
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
    {
        "path": "pages/7_Definition_Elo.py",
        "title": "Définition Elo",
        "icon": "📖",
        "desc": "Document PDF de référence sur le système de rating Elo appliqué au tennis.",
    },
]

row1 = st.columns(3)
row2 = st.columns(3)
row3 = st.columns(3)

for i, page in enumerate(PAGES):
    if i < 3:
        col = row1[i]
    elif i < 6:
        col = row2[i - 3]
    else:
        col = row3[i - 6]
    with col:
        with st.container(border=True):
            st.markdown(f"### {page['icon']} {page['title']}")
            st.caption(page["desc"])
            st.page_link(page["path"], label=f"Ouvrir {page['title']} →")
