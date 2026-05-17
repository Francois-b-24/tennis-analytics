"""Point d'entrée Streamlit : accueil, métriques globales et navigation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from components._bootstrap import init_app

_ROOT, connection = init_app(__file__)

import streamlit as st

from components.widgets import (
    circuit_filter_sql,
    circuit_selectbox,
    format_date_dd_mm_yyyy,
    inject_global_css,
    kpi_row,
    page_header,
    safe_scalar,
    section,
)

st.set_page_config(
    page_title="Tennis Analytics",
    page_icon="🎾",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_global_css()

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
circuit = circuit_selectbox(key="home_circuit")
cf = circuit_filter_sql(circuit)

# ── Hero ──────────────────────────────────────────────────────────────────────
page_header(
    "Tennis Analytics",
    subtitle="Plateforme personnelle d'analyse ATP/WTA — statistiques, ratings Elo et prédictions ML.",
    icon="🎾",
)

# ── KPIs : volume des données ─────────────────────────────────────────────────
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

kpi_row(
    [
        {"label": "Matchs indexés", "value": f"{total_matches:,}".replace(",", " "), "icon": "🎾"},
        {"label": "Joueurs", "value": f"{total_players:,}".replace(",", " "), "icon": "👤"},
        {"label": "Tournois", "value": f"{total_tournois:,}".replace(",", " "), "icon": "🏆"},
    ]
)

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

kpi_row(
    [
        {"label": "Période couverte", "value": f"{min_date} → {max_date}", "icon": "📅"},
        {
            "label": "Dernier tournoi ATP",
            "value": last_atp_name,
            "delta": last_atp_date,
            "icon": "🟦",
        },
        {
            "label": "Dernier tournoi WTA",
            "value": last_wta_name,
            "delta": last_wta_date,
            "icon": "🟪",
        },
    ]
)

st.markdown(
    """
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
section("Explorer l'application", level=3, divider_before=True)

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
    {
        "path": "pages/8_Top_20_actuel.py",
        "title": "Top 20 actuel",
        "icon": "🌟",
        "desc": "Focus sur les 20 meilleurs joueurs ATP et WTA actuels : profil Elo, forme, style et comparaison structurelle.",
    },
    {
        "path": "pages/9_Profils_et_Styles.py",
        "title": "Profils & Styles",
        "icon": "🧬",
        "desc": "Clustering automatique des styles de jeu (KMeans) et indice de polyvalence multi-surface.",
    },
]

# Grille 3 colonnes x N lignes (ajustee dynamiquement a la longueur de PAGES)
n_rows = (len(PAGES) + 2) // 3
rows = [st.columns(3) for _ in range(n_rows)]

for i, page in enumerate(PAGES):
    col = rows[i // 3][i % 3]
    with col, st.container(border=True):
        st.markdown(f"### {page['icon']} {page['title']}")
        st.caption(page["desc"])
        st.page_link(page["path"], label=f"Ouvrir {page['title']} →")
