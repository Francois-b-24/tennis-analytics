"""Page Classements Elo : Top N joueurs par surface et comparaison multi-surface."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parents[1]
_ROOT = Path(__file__).resolve().parents[2]

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")
os.environ.setdefault("ROOT_PATH", str(_ROOT))

if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

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
from components.widgets import format_elo
from db.duckdb_session import create_connection

st.set_page_config(page_title="Classements Elo — Tennis Analytics", layout="wide")

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
        SELECT
            ROW_NUMBER() OVER (ORDER BY e.{surface_col} DESC NULLS LAST) AS rang,
            pn.full_name AS joueur,
            ROUND(e.elo_global, 0) AS elo_global,
            ROUND(e.elo_hard,   0) AS elo_hard,
            ROUND(e.elo_clay,   0) AS elo_clay,
            ROUND(e.elo_grass,  0) AS elo_grass,
            e.last_match_date
        FROM v_elo_latest e
        JOIN v_player_names pn ON e.player_id = pn.player_id
        JOIN v_players p       ON e.player_id = p.player_id
        WHERE p.circuit = ?
          AND e.{surface_col} IS NOT NULL
        ORDER BY e.{surface_col} DESC NULLS LAST
        LIMIT ?
    """
    return _connection().execute(sql, [circuit, top_n]).df()


# ── Sidebar ───────────────────────────────────────────────────────────────────
circuit = st.sidebar.selectbox("Circuit", ["ATP", "WTA"], key="elo_circuit")
top_n = st.sidebar.slider("Top N joueurs", min_value=10, max_value=100, value=50, step=10)
surface_choice = st.sidebar.selectbox(
    "Surface de classement", list(SURFACE_MAP.keys()), key="elo_surface"
)
surface_col = SURFACE_MAP[surface_choice]
surface_color = SURFACE_COLORS[surface_choice]

st.title("Classements Elo")
st.caption(
    f"Ratings calculés sur {top_n} joueurs {circuit} — surface de référence : **{surface_choice}**"
)

df = _top_elo(str(_ROOT), circuit, surface_col, top_n)

if df.empty:
    st.warning(
        "Aucune donnée Elo disponible. "
        "Lancez `uv run python -m transformation.build_elo`."
    )
    st.stop()

# ── Section A — Tableau ───────────────────────────────────────────────────────
st.subheader(f"Top {top_n} — {circuit} ({surface_choice})")

display_df = df.copy()
for col in ["elo_global", "elo_hard", "elo_clay", "elo_grass"]:
    display_df[col] = display_df[col].apply(lambda v: format_elo(v) if pd.notna(v) else "—")

st.dataframe(
    display_df.rename(columns={
        "rang": "Rang",
        "joueur": "Joueur",
        "elo_global": "Global",
        "elo_hard": "Dur",
        "elo_clay": "Terre",
        "elo_grass": "Gazon",
        "last_match_date": "Dernier match",
    }),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# ── Section B — Bar chart Top N ───────────────────────────────────────────────
st.subheader(f"Visualisation Top {min(top_n, 30)}")

chart_df = df.head(30).sort_values(surface_col, ascending=True)

fig_bar = go.Figure(go.Bar(
    x=chart_df[surface_col],
    y=chart_df["joueur"],
    orientation="h",
    marker_color=surface_color,
    text=chart_df[surface_col].apply(lambda v: format_elo(v) if pd.notna(v) else "—"),
    textposition="outside",
    hovertemplate="<b>%{y}</b><br>Elo %{x:.0f}<extra></extra>",
))
fig_bar.update_layout(
    title=f"Top {min(top_n, 30)} {circuit} — Elo {surface_choice}",
    xaxis_title=f"Rating Elo ({surface_choice})",
    yaxis_title=None,
    height=max(500, len(chart_df) * 22),
    margin=dict(l=180),
)
apply_tennis_theme(fig_bar)
st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ── Section C — Comparaison multi-surface pour un joueur ─────────────────────
st.subheader("Comparaison 4 surfaces pour un joueur")

player_choice = st.selectbox(
    "Sélectionner un joueur",
    df["joueur"].tolist(),
    key="elo_player_compare",
)

player_row = df[df["joueur"] == player_choice].iloc[0]

surfaces = ["Global", "Dur", "Terre battue", "Gazon"]
values = [
    float(player_row["elo_global"]) if pd.notna(player_row["elo_global"]) else None,
    float(player_row["elo_hard"])   if pd.notna(player_row["elo_hard"])   else None,
    float(player_row["elo_clay"])   if pd.notna(player_row["elo_clay"])   else None,
    float(player_row["elo_grass"])  if pd.notna(player_row["elo_grass"])  else None,
]
colors = [TENNIS_LINE, TENNIS_HARD, TENNIS_CLAY, TENNIS_GREEN]

fig_comp = go.Figure(go.Bar(
    x=surfaces,
    y=values,
    marker_color=colors,
    text=[format_elo(v) for v in values],
    textposition="outside",
    hovertemplate="<b>%{x}</b><br>Elo : %{y:.0f}<extra></extra>",
))
fig_comp.update_layout(
    title=f"Profil Elo multi-surface — {player_choice}",
    xaxis_title="Surface",
    yaxis_title="Rating Elo",
    showlegend=False,
)
apply_tennis_theme(fig_comp)
st.plotly_chart(fig_comp, use_container_width=True)
