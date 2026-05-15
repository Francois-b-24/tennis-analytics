"""Page Prédictions : probabilité de victoire ML (LogisticRegression calibré)."""

from __future__ import annotations

import os
import sys
from datetime import datetime
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
import numpy as np
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
from components.widgets import inject_global_css, load_model_bundle, load_player_options, page_info, player_selectbox
from db.duckdb_session import create_connection

st.set_page_config(page_title="Prédictions — Tennis Analytics", layout="wide")
inject_global_css()

MODEL_PATH = str(_ROOT / "data" / "processed" / "models" / "logreg_calibrated.joblib")

SURFACE_ELO_COL = {"Dur": "elo_hard", "Terre battue": "elo_clay", "Gazon": "elo_grass"}
SURFACE_NORM    = {"Dur": "hard",     "Terre battue": "clay",     "Gazon": "grass"}
SURFACE_LABEL   = {"Dur": "🔵 Dur",   "Terre battue": "🟠 Terre battue", "Gazon": "🟢 Gazon"}


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return create_connection(_ROOT)


@st.cache_data(show_spinner=False)
def _elo_row(_root: str, player_id: int) -> pd.DataFrame:
    try:
        return _connection().execute(
            "SELECT * FROM v_elo_latest WHERE player_id = ? LIMIT 1;", [player_id]
        ).df()
    except duckdb.Error:
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def _player_dob(_root: str, player_id: int) -> int | None:
    try:
        row = _connection().execute(
            "SELECT dob FROM v_players WHERE player_id = ? LIMIT 1;", [player_id]
        ).fetchone()
        if row and row[0]:
            token = str(row[0]).split(".")[0]
            if len(token) >= 4:
                return int(token[:4])
    except duckdb.Error:
        pass
    return None


@st.cache_data(show_spinner=False)
def _h2h_ratio(_root: str, player_a: int, player_b: int) -> tuple[float, int, int, int]:
    """Retourne (ratio_a, wins_a, wins_b, total)."""
    try:
        row = _connection().execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wins_a
            FROM v_matches
            WHERE (winner_id = ? AND loser_id = ?)
               OR (winner_id = ? AND loser_id = ?)
            """,
            [player_a, player_a, player_b, player_b, player_a],
        ).fetchone()
        if row and row[0] > 0:
            total  = int(row[0])
            wins_a = int(row[1])
            wins_b = total - wins_a
            return float(wins_a) / float(total), wins_a, wins_b, total
    except duckdb.Error:
        pass
    return 0.5, 0, 0, 0


@st.cache_data(show_spinner=False)
def _surface_winrate(_root: str, player_id: int, surface_norm: str) -> float:
    try:
        row = _connection().execute(
            """
            SELECT
                SUM(CASE WHEN winner_id = ? THEN 1.0 ELSE 0.0 END) AS wins,
                COUNT(*) AS total
            FROM v_matches
            WHERE surface_norm = ?
              AND (winner_id = ? OR loser_id = ?)
            """,
            [player_id, surface_norm, player_id, player_id],
        ).fetchone()
        if row and row[1] > 0:
            return float(row[0]) / float(row[1])
    except duckdb.Error:
        pass
    return 0.5


@st.cache_data(show_spinner=False)
def _recent_form(_root: str, player_id: int) -> float:
    try:
        df = _connection().execute(
            """
            SELECT winner_id
            FROM v_matches
            WHERE winner_id = ? OR loser_id = ?
            ORDER BY tourney_date DESC
            LIMIT 10
            """,
            [player_id, player_id],
        ).df()
        if not df.empty:
            return float((df["winner_id"] == player_id).sum()) / len(df)
    except duckdb.Error:
        pass
    return 0.5


def _get_elo(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 1500.0
    v = df.iloc[0].get(col)
    return float(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else 1500.0


# ── Sidebar ───────────────────────────────────────────────────────────────────
circuit = st.sidebar.selectbox("Circuit", ["ATP", "WTA"], key="pred_circuit")

st.title("Prédictions")
page_info(
    "Estimez la probabilité de victoire entre deux joueurs sur une surface donnée. "
    "Le modèle est une régression logistique calibrée entraînée sur ~90 000 matchs depuis 2010 — "
    "il combine les ratings Elo, le bilan H2H, la forme récente et la spécialisation par surface."
)

# ── Vérification modèle ───────────────────────────────────────────────────────
bundle = load_model_bundle(MODEL_PATH)
if bundle is None:
    st.error(
        "Modèle non disponible. Lancez d'abord :\n\n"
        "```bash\nPYTHONPATH=src uv run python -m transformation.build_model\n```"
    )
    st.stop()

# ── Sélection joueurs ─────────────────────────────────────────────────────────
connection = _connection()

try:
    players = connection.execute(
        """
        SELECT pn.player_id, pn.full_name
        FROM v_player_names pn
        JOIN v_players p USING (player_id)
        WHERE p.circuit = ?
          AND TRIM(pn.full_name) <> ''
        ORDER BY pn.full_name
        """,
        [circuit],
    ).df().drop_duplicates(subset=["full_name"])
except duckdb.Error:
    players = load_player_options(connection)

if players.empty:
    st.warning("Aucun joueur disponible. Lancez l'ingestion.")
    st.stop()

col_a, col_b = st.columns(2)
with col_a:
    player_a = player_selectbox("Joueur A", players, key="pred_a")
with col_b:
    player_b = player_selectbox("Joueur B", players, key="pred_b")

surface_choice = st.selectbox(
    "Surface", list(SURFACE_ELO_COL.keys()), key="pred_surface"
)

if player_a is None or player_b is None or player_a == player_b:
    st.warning("Choisissez deux joueurs distincts.")
    st.stop()

name_a = players.loc[players["player_id"] == player_a, "full_name"].iloc[0]
name_b = players.loc[players["player_id"] == player_b, "full_name"].iloc[0]

# ── Calcul automatique ────────────────────────────────────────────────────────
elo_col   = SURFACE_ELO_COL[surface_choice]
surf_norm = SURFACE_NORM[surface_choice]

elo_a = _elo_row(str(_ROOT), player_a)
elo_b = _elo_row(str(_ROOT), player_b)

ea_surf = _get_elo(elo_a, elo_col)
eb_surf = _get_elo(elo_b, elo_col)
ea_glob = _get_elo(elo_a, "elo_global")
eb_glob = _get_elo(elo_b, "elo_global")

current_year = datetime.now().year
dob_a = _player_dob(str(_ROOT), player_a)
dob_b = _player_dob(str(_ROOT), player_b)
age_a = current_year - dob_a if dob_a else 27
age_b = current_year - dob_b if dob_b else 27

h2h_ratio, h2h_wins_a, h2h_wins_b, h2h_total = _h2h_ratio(str(_ROOT), player_a, player_b)
wr_a   = _surface_winrate(str(_ROOT), player_a, surf_norm)
wr_b   = _surface_winrate(str(_ROOT), player_b, surf_norm)
form_a = _recent_form(str(_ROOT), player_a)
form_b = _recent_form(str(_ROOT), player_b)

features = {
    "diff_elo_surface":    ea_surf - eb_surf,
    "diff_elo_global":     ea_glob - eb_glob,
    "diff_rank":           0.0,
    "diff_age":            float(age_a - age_b),
    "h2h_ratio":           h2h_ratio,
    "surface_winrate_diff": wr_a - wr_b,
    "recent_form_diff":    form_a - form_b,
}

feature_cols = bundle["features"]
X = pd.DataFrame([features])[feature_cols]
prob_a = float(bundle["model"].predict_proba(X)[:, 1][0])
prob_b = 1.0 - prob_a

st.divider()

# ── Contexte des deux joueurs ─────────────────────────────────────────────────
st.subheader("Contexte")

ca, cb = st.columns(2)

with ca:
    st.markdown(f"#### {name_a}")
    m1, m2 = st.columns(2)
    with m1:
        st.metric("Elo global",          f"{int(round(ea_glob))}")
        st.metric(f"Elo {surface_choice}", f"{int(round(ea_surf))}")
    with m2:
        st.metric("% victoires surface", f"{wr_a*100:.0f} %")
        st.metric("Forme récente (10)",  f"{form_a*100:.0f} %")

with cb:
    st.markdown(f"#### {name_b}")
    m1, m2 = st.columns(2)
    with m1:
        st.metric("Elo global",          f"{int(round(eb_glob))}")
        st.metric(f"Elo {surface_choice}", f"{int(round(eb_surf))}")
    with m2:
        st.metric("% victoires surface", f"{wr_b*100:.0f} %")
        st.metric("Forme récente (10)",  f"{form_b*100:.0f} %")

# H2H summary
if h2h_total > 0:
    leader = name_a if h2h_wins_a >= h2h_wins_b else name_b
    st.caption(
        f"H2H — {name_a} **{h2h_wins_a}** — **{h2h_wins_b}** {name_b} "
        f"sur {h2h_total} confrontations officielles. Avantage : {leader}."
    )
else:
    st.caption("Aucune confrontation directe dans les données.")

st.divider()

# ── Probabilité de victoire ───────────────────────────────────────────────────
st.subheader(f"Probabilité de victoire — {SURFACE_LABEL[surface_choice]}")

winner   = name_a if prob_a >= prob_b else name_b
win_prob = max(prob_a, prob_b)

# Bandeau favori
fav_color = "#3A7D44" if prob_a >= prob_b else "#C27940"
st.markdown(
    f"""
    <div style="
        background:{fav_color}18;
        border-left:4px solid {fav_color};
        border-radius:0 8px 8px 0;
        padding:10px 16px;
        margin-bottom:12px;
        font-size:1.05rem;
    ">
    🏆 &nbsp;<strong>Favori : {winner}</strong> — probabilité de victoire estimée à
    <strong>{win_prob*100:.1f} %</strong>
    </div>
    """,
    unsafe_allow_html=True,
)

fig = go.Figure(go.Bar(
    x=[prob_a * 100, prob_b * 100],
    y=[name_a, name_b],
    orientation="h",
    marker_color=[TENNIS_GREEN, TENNIS_CLAY],
    text=[f"{prob_a*100:.1f} %", f"{prob_b*100:.1f} %"],
    textposition="inside",
    insidetextanchor="middle",
    hovertemplate="%{y} : %{x:.1f} %<extra></extra>",
))
fig.update_layout(
    xaxis=dict(range=[0, 100], ticksuffix="%"),
    xaxis_title="Probabilité de victoire (%)",
    yaxis_title=None,
    height=220,
    showlegend=False,
    margin=dict(l=10, r=10, t=10, b=30),
)
apply_tennis_theme(fig)
st.plotly_chart(fig, use_container_width=True)

# ── Détail des features ───────────────────────────────────────────────────────
with st.expander("Détail des indicateurs utilisés par le modèle"):
    FEATURE_LABELS = {
        "diff_elo_surface":    f"Écart Elo {surface_choice} (A − B)",
        "diff_elo_global":     "Écart Elo global (A − B)",
        "diff_rank":           "Écart classement (A − B)",
        "diff_age":            "Écart d'âge en années (A − B)",
        "h2h_ratio":           "Ratio H2H historique (victoires A / total)",
        "surface_winrate_diff": f"Écart % victoires sur {surface_choice} (A − B)",
        "recent_form_diff":    "Écart forme récente — 10 derniers matchs (A − B)",
    }
    rows = [
        {"Indicateur": FEATURE_LABELS[k], "Valeur": f"{v:+.3f}" if k != "h2h_ratio" else f"{v:.3f}"}
        for k, v in features.items()
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.caption(
    "Modèle : régression logistique calibrée (isotonique) entraînée sur les matchs ATP/WTA "
    "depuis 2010. Les probabilités reflètent les performances historiques et les ratings Elo — "
    "elles ne constituent pas une recommandation de pari."
)
