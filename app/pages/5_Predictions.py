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
from components.widgets import load_model_bundle, load_player_options, player_selectbox
from db.duckdb_session import create_connection

st.set_page_config(page_title="Prédictions — Tennis Analytics", layout="wide")

MODEL_PATH = str(_ROOT / "data" / "processed" / "models" / "logreg_calibrated.joblib")

SURFACE_ELO_COL = {"Dur": "elo_hard", "Terre battue": "elo_clay", "Gazon": "elo_grass"}
SURFACE_NORM = {"Dur": "hard", "Terre battue": "clay", "Gazon": "grass"}


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
def _h2h_ratio(_root: str, player_a: int, player_b: int) -> float:
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
            return float(row[1]) / float(row[0])
    except duckdb.Error:
        pass
    return 0.5


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


# ── Sidebar ───────────────────────────────────────────────────────────────────
circuit = st.sidebar.selectbox("Circuit", ["ATP", "WTA"], key="pred_circuit")

st.title("Prédictions")

# ── Vérification modèle ───────────────────────────────────────────────────────
bundle = load_model_bundle(MODEL_PATH)
if bundle is None:
    st.error(
        "Modèle non disponible. Lancez d'abord :\n\n"
        "```bash\nuv run python -m transformation.build_model\n```"
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

surface_choice = st.selectbox("Surface", list(SURFACE_ELO_COL.keys()), key="pred_surface")

if player_a is None or player_b is None or player_a == player_b:
    st.warning("Choisissez deux joueurs distincts.")
    st.stop()

name_a = players.loc[players["player_id"] == player_a, "full_name"].iloc[0]
name_b = players.loc[players["player_id"] == player_b, "full_name"].iloc[0]

# ── Calcul des features ───────────────────────────────────────────────────────
if st.button("Calculer la probabilité", type="primary"):
    with st.spinner("Calcul en cours..."):
        elo_col = SURFACE_ELO_COL[surface_choice]
        surf_norm = SURFACE_NORM[surface_choice]

        elo_a = _elo_row(str(_ROOT), player_a)
        elo_b = _elo_row(str(_ROOT), player_b)

        def _get_elo(df: pd.DataFrame, col: str) -> float:
            if df.empty or col not in df.columns:
                return 1500.0
            v = df.iloc[0].get(col)
            return float(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else 1500.0

        ea_surf = _get_elo(elo_a, elo_col)
        eb_surf = _get_elo(elo_b, elo_col)
        ea_glob = _get_elo(elo_a, "elo_global")
        eb_glob = _get_elo(elo_b, "elo_global")

        current_year = datetime.now().year
        dob_a = _player_dob(str(_ROOT), player_a)
        dob_b = _player_dob(str(_ROOT), player_b)
        age_a = current_year - dob_a if dob_a else 27
        age_b = current_year - dob_b if dob_b else 27

        h2h = _h2h_ratio(str(_ROOT), player_a, player_b)
        wr_a = _surface_winrate(str(_ROOT), player_a, surf_norm)
        wr_b = _surface_winrate(str(_ROOT), player_b, surf_norm)
        form_a = _recent_form(str(_ROOT), player_a)
        form_b = _recent_form(str(_ROOT), player_b)

        features = {
            "diff_elo_surface": ea_surf - eb_surf,
            "diff_elo_global": ea_glob - eb_glob,
            "diff_rank": 0.0,
            "diff_age": float(age_a - age_b),
            "h2h_ratio": h2h,
            "surface_winrate_diff": wr_a - wr_b,
            "recent_form_diff": form_a - form_b,
        }

        feature_cols = bundle["features"]
        X = pd.DataFrame([features])[feature_cols]
        prob_a = float(bundle["model"].predict_proba(X)[:, 1][0])
        prob_b = 1.0 - prob_a

    # ── Résultat ──────────────────────────────────────────────────────────────
    st.divider()
    st.subheader(f"Probabilité de victoire — {surface_choice}")

    winner = name_a if prob_a >= prob_b else name_b
    win_prob = max(prob_a, prob_b)
    st.markdown(f"**Favori : {winner}** avec {win_prob*100:.1f} % de probabilité de victoire.")

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
        title=f"{name_a} vs {name_b} — {surface_choice}",
        xaxis=dict(range=[0, 100], ticksuffix="%"),
        xaxis_title="Probabilité de victoire (%)",
        yaxis_title=None,
        height=250,
        showlegend=False,
    )
    apply_tennis_theme(fig)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Détail des features utilisées"):
        feat_display = pd.DataFrame(
            [{"Feature": k, "Valeur": f"{v:.4f}"} for k, v in features.items()]
        )
        st.dataframe(feat_display, use_container_width=True, hide_index=True)

    st.caption(
        "Modèle : régression logistique calibrée (isotonique) entraînée sur les matchs ATP/WTA "
        "depuis 2010. Les probabilités reflètent les performances historiques et les ratings Elo — "
        "elles ne constituent pas une recommandation de pari."
    )
