"""Page Classements Elo : Top N joueurs par surface et comparaison multi-surface."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from components._bootstrap import init_app

_ROOT, _ = init_app(__file__)

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.plotly_theme import (
    TENNIS_CLAY,
    TENNIS_GREEN,
    TENNIS_HARD,
    TENNIS_LINE,
    apply_tennis_theme,
)
from components.widgets import (
    circuit_selectbox,
    df_styled,
    format_elo,
    inject_global_css,
    page_header,
    section,
)
from db.duckdb_session import create_connection

st.set_page_config(page_title="Classements Elo — Tennis Analytics", layout="wide")
inject_global_css()

SURFACE_MAP = {
    "Global": "elo_global",
    "Dur": "elo_hard",
    "Terre battue": "elo_clay",
    "Gazon": "elo_grass",
}
SURFACE_COLORS = {
    "Global": TENNIS_LINE,
    "Dur": TENNIS_HARD,
    "Terre battue": TENNIS_CLAY,
    "Gazon": TENNIS_GREEN,
}


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return create_connection(_ROOT)


@st.cache_data(show_spinner=False)
def _top_elo(_root: str, circuit: str, surface_col: str, top_n: int) -> pd.DataFrame:
    # surface_col vient d'un dict Python hardcodé — pas de risque d'injection
    sql = f"""
        WITH player_unique AS (
            SELECT player_id,
                   TRIM(CONCAT(COALESCE(ANY_VALUE(name_first), ''),
                               ' ',
                               COALESCE(ANY_VALUE(name_last), ''))) AS joueur
            FROM v_players
            WHERE circuit = ?
            GROUP BY player_id
        )
        SELECT
            ROW_NUMBER() OVER (ORDER BY e.{surface_col} DESC NULLS LAST) AS rang,
            pu.joueur,
            ROUND(e.elo_global, 0) AS elo_global,
            ROUND(e.elo_hard,   0) AS elo_hard,
            ROUND(e.elo_clay,   0) AS elo_clay,
            ROUND(e.elo_grass,  0) AS elo_grass,
            e.last_match_date
        FROM v_elo_latest e
        JOIN player_unique pu ON e.player_id = pu.player_id
        WHERE e.{surface_col} IS NOT NULL
          AND pu.joueur <> ''
        ORDER BY e.{surface_col} DESC NULLS LAST
        LIMIT ?
    """
    return _connection().execute(sql, [circuit, top_n]).df()


# ── Sidebar ───────────────────────────────────────────────────────────────────
circuit = circuit_selectbox(key="elo_circuit", include_all=False, default="ATP")
top_n = st.sidebar.slider("Top N joueurs", min_value=10, max_value=100, value=50, step=10)
surface_choice = st.sidebar.selectbox(
    "Surface de classement", list(SURFACE_MAP.keys()), key="elo_surface"
)
surface_col = SURFACE_MAP[surface_choice]
surface_color = SURFACE_COLORS[surface_choice]

page_header(
    "Classements Elo",
    subtitle=(
        "Classement par rating Elo — un indicateur calculé match après match, plus précis "
        "que le classement officiel car il tient compte de la force des adversaires."
    ),
    icon="📊",
)
st.caption(
    f"Ratings calculés sur {top_n} joueurs {circuit} — surface de référence : **{surface_choice}**"
)

with st.expander("ℹ️ Qu'est-ce que le rating Elo ?"):
    st.markdown(
        """
        Le **rating Elo** est un système de notation inventé par le physicien Arpad Elo
        (initialement pour les échecs) puis adapté au tennis. Il attribue à chaque joueur
        un score numérique reflétant son **niveau actuel** : plus le score est élevé, plus
        le joueur est fort.

        **Principes du modèle utilisé ici :**

        - 🎯 **Base de départ : 1500 points** pour tout nouveau joueur.
        - ⚖️ **Mise à jour après chaque match** : le vainqueur gagne des points, le perdant
          en perd. L'ampleur du transfert dépend de l'écart attendu entre les deux joueurs
          *avant* la rencontre.
        - 📈 **Battre un favori rapporte plus de points** que battre un outsider — et inversement.
        - 🎾 **Quatre ratings par joueur** : Global, Dur, Terre battue, Gazon. Les ratings
          surface capturent la spécialisation (ex : Nadal sur terre).
        - 🔄 **Facteur K adaptatif** : 40 pour les joueurs débutants (< 30 matchs), 20 entre
          30 et 100 matchs, 10 ensuite. Cela stabilise les ratings des vétérans.
        - 🏆 **Best-of-5 majoré** : les matchs en 3 sets gagnants pèsent 1.1× plus.
        - 💤 **Décroissance d'inactivité** : après 6 mois sans match, le rating glisse
          progressivement vers 1500 (modèle exponentiel).

        **Lecture rapide :**
        - **2200+** : élite mondiale (Top 5)
        - **2000–2200** : Top 20
        - **1800–2000** : circuit professionnel
        - **1500–1800** : joueurs en développement

        Notre Elo est **calculé maison** depuis 2010 ; il s'inspire des approches publiques
        (FiveThirtyEight, Tennis Abstract) sans en reproduire un modèle propriétaire.
        """
    )

df = _top_elo(str(_ROOT), circuit, surface_col, top_n)

if df.empty:
    st.warning(
        "Aucune donnée Elo disponible. " "Lancez `uv run python -m transformation.build_elo`."
    )
    st.stop()

# ── Section A — Tableau ───────────────────────────────────────────────────────
section(f"Top {top_n} — {circuit} ({surface_choice})", level=3)

display_df = df.rename(
    columns={
        "rang": "Rang",
        "joueur": "Joueur",
        "elo_global": "Global",
        "elo_hard": "Dur",
        "elo_clay": "Terre",
        "elo_grass": "Gazon",
        "last_match_date": "Dernier match",
    }
)
df_styled(
    display_df,
    column_config={
        "Rang": st.column_config.NumberColumn(format="#%d"),
        "Global": st.column_config.NumberColumn(format="%d"),
        "Dur": st.column_config.NumberColumn(format="%d"),
        "Terre": st.column_config.NumberColumn(format="%d"),
        "Gazon": st.column_config.NumberColumn(format="%d"),
    },
)

# ── Section B — Bar chart Top N ───────────────────────────────────────────────
section(f"Visualisation Top {min(top_n, 30)}", level=3, divider_before=True)

chart_df = df.head(30).sort_values(surface_col, ascending=True)

fig_bar = go.Figure(
    go.Bar(
        x=chart_df[surface_col],
        y=chart_df["joueur"],
        orientation="h",
        marker_color=surface_color,
        text=chart_df[surface_col].apply(lambda v: format_elo(v) if pd.notna(v) else "—"),
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Elo %{x:.0f}<extra></extra>",
    )
)
fig_bar.update_layout(
    title=f"Top {min(top_n, 30)} {circuit} — Elo {surface_choice}",
    xaxis_title=f"Rating Elo ({surface_choice})",
    yaxis_title=None,
    height=max(500, len(chart_df) * 22),
    margin=dict(l=10, r=10),
)
apply_tennis_theme(fig_bar)
st.plotly_chart(fig_bar, use_container_width=True)

# ── Section C — Comparaison multi-surface pour un joueur ─────────────────────
section("Comparaison 4 surfaces pour un joueur", level=3, divider_before=True)

player_choice = st.selectbox(
    "Sélectionner un joueur",
    df["joueur"].tolist(),
    key="elo_player_compare",
    help="💡 Tapez pour rechercher",
    placeholder="Rechercher un joueur…",
)

player_row = df[df["joueur"] == player_choice].iloc[0]

surfaces = ["Global", "Dur", "Terre battue", "Gazon"]
values = [
    float(player_row["elo_global"]) if pd.notna(player_row["elo_global"]) else None,
    float(player_row["elo_hard"]) if pd.notna(player_row["elo_hard"]) else None,
    float(player_row["elo_clay"]) if pd.notna(player_row["elo_clay"]) else None,
    float(player_row["elo_grass"]) if pd.notna(player_row["elo_grass"]) else None,
]
colors = [TENNIS_LINE, TENNIS_HARD, TENNIS_CLAY, TENNIS_GREEN]

fig_comp = go.Figure(
    go.Bar(
        x=surfaces,
        y=values,
        marker_color=colors,
        text=[format_elo(v) for v in values],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Elo : %{y:.0f}<extra></extra>",
    )
)
fig_comp.update_layout(
    title=f"Profil Elo multi-surface — {player_choice}",
    xaxis_title="Surface",
    yaxis_title="Rating Elo",
    showlegend=False,
)
apply_tennis_theme(fig_comp)
st.plotly_chart(fig_comp, use_container_width=True)
