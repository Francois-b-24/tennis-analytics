"""Page Joueurs : fiche joueur, stats carrière, évolution Elo et derniers matchs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parents[1]
_ROOT = Path(__file__).resolve().parents[2]

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")
os.environ.setdefault("ROOT_PATH", str(_ROOT))

_SRC = _ROOT / "src"
for path in (_APP_DIR, _ROOT, _SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import math

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
    disambiguate_player_labels,
    format_date_dd_mm_yyyy,
    format_elo,
    inject_global_css,
    page_info,
)
from db.duckdb_session import create_connection

st.set_page_config(page_title="Joueurs — Tennis Analytics", layout="wide")
inject_global_css()


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return create_connection(_ROOT)


@st.cache_data(show_spinner=False)
def _player_options(_root: str, circuit: str) -> pd.DataFrame:
    """Liste dédupliquée des joueurs d'un circuit avec leur code pays IOC."""
    conn = _connection()
    cols = conn.execute("DESCRIBE v_players").df()["column_name"].tolist()
    pays_col = "ioc" if "ioc" in cols else ("country_code" if "country_code" in cols else "NULL")
    sql = f"""
        SELECT player_id,
               TRIM(CONCAT(COALESCE(ANY_VALUE(name_first), ''),
                           ' ',
                           COALESCE(ANY_VALUE(name_last), ''))) AS full_name,
               ANY_VALUE({pays_col}) AS ioc
        FROM v_players
        WHERE circuit = ?
        GROUP BY player_id
        HAVING TRIM(CONCAT(COALESCE(ANY_VALUE(name_first), ''),
                           ' ',
                           COALESCE(ANY_VALUE(name_last), ''))) <> ''
    """
    try:
        return conn.execute(sql, [circuit]).df()
    except duckdb.Error:
        return pd.DataFrame(columns=["player_id", "full_name", "ioc"])


@st.cache_data(show_spinner=False)
def _identity(_root: str, player_id: int) -> pd.DataFrame:
    return _connection().execute(
        """
        SELECT p.name_first, p.name_last, p.ioc AS pays, p.dob, p.circuit,
               e.elo_global, e.elo_hard, e.elo_clay, e.elo_grass, e.last_match_date
        FROM v_players p
        LEFT JOIN v_elo_latest e ON p.player_id = e.player_id
        WHERE p.player_id = ?
        LIMIT 1;
        """,
        [player_id],
    ).df()


@st.cache_data(show_spinner=False)
def _career_stats(_root: str, player_id: int) -> pd.DataFrame:
    return _connection().execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN loser_id  = ? THEN 1 ELSE 0 END) AS losses,
            ROUND(
                SUM(CASE WHEN winner_id = ? THEN 1.0 ELSE 0.0 END) / NULLIF(COUNT(*), 0) * 100,
                1
            ) AS win_pct,
            COUNT(DISTINCT tourney_name) AS tournaments,
            ROUND(AVG(CASE WHEN winner_id = ? THEN w_ace ELSE l_ace END), 1) AS avg_aces,
            ROUND(AVG(CASE WHEN winner_id = ? THEN w_df  ELSE l_df  END), 1) AS avg_df,
            ROUND(AVG(minutes) FILTER (WHERE minutes > 0 AND minutes < 400), 0) AS avg_duration
        FROM v_matches
        WHERE winner_id = ? OR loser_id = ?
        """,
        [player_id] * 7,
    ).df()


@st.cache_data(show_spinner=False)
def _surface_stats(_root: str, player_id: int) -> pd.DataFrame:
    return _connection().execute(
        """
        SELECT
            COALESCE(NULLIF(surface, ''), 'Inconnue') AS surface,
            COUNT(*) AS total,
            SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN loser_id  = ? THEN 1 ELSE 0 END) AS losses
        FROM v_matches
        WHERE winner_id = ? OR loser_id = ?
        GROUP BY surface
        ORDER BY total DESC
        """,
        [player_id, player_id, player_id, player_id],
    ).df()


@st.cache_data(show_spinner=False)
def _elo_history(_root: str, player_id: int) -> pd.DataFrame:
    try:
        df = _connection().execute(
            """
            SELECT tourney_date, elo_global, elo_hard, elo_clay, elo_grass
            FROM v_elo_history
            WHERE player_id = ?
            ORDER BY tourney_date ASC
            """,
            [player_id],
        ).df()
        if not df.empty:
            df["date"] = pd.to_datetime(df["tourney_date"].astype(str), format="%Y%m%d")
        return df
    except duckdb.Error:
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def _recent_matches(_root: str, player_id: int) -> pd.DataFrame:
    return _connection().execute(
        """
        SELECT
            tourney_date,
            tourney_name,
            surface,
            round,
            CASE WHEN winner_id = ? THEN 'Victoire' ELSE 'Défaite' END AS résultat,
            CASE WHEN winner_id = ? THEN loser_name ELSE winner_name END AS adversaire,
            score,
            minutes
        FROM v_matches
        WHERE winner_id = ? OR loser_id = ?
        ORDER BY tourney_date DESC
        LIMIT 20
        """,
        [player_id, player_id, player_id, player_id],
    ).df()


# ── Sidebar ───────────────────────────────────────────────────────────────────
circuit = st.sidebar.selectbox("Circuit", ["ATP", "WTA"], key="joueurs_circuit")

# ── Titre ─────────────────────────────────────────────────────────────────────
st.title("Joueurs")
page_info(
    "Sélectionnez un joueur pour afficher sa fiche complète : ratings Elo actuels par surface, "
    "bilan victoires/défaites sur toute sa carrière, performances par type de terrain "
    "et évolution de son niveau dans le temps."
)

players = _player_options(str(_ROOT), circuit)
if players.empty:
    st.warning("Aucun joueur disponible. Lancez l'ingestion pour construire les parquets.")
    st.stop()

players = disambiguate_player_labels(players)
mapping = dict(zip(players["label"], players["player_id"], strict=False))
selected_label = st.selectbox(
    "Sélectionner un joueur", list(mapping.keys()), key="joueurs_player"
)
player_id = int(mapping[selected_label])
# Conserve le nom propre (sans IOC) pour les titres et affichages
selected_name = players.loc[players["player_id"] == player_id, "full_name"].iloc[0]

# ── Section A — Carte d'identité ──────────────────────────────────────────────
identity = _identity(str(_ROOT), player_id)

if identity.empty:
    st.error("Données introuvables pour ce joueur.")
    st.stop()

row = identity.iloc[0]

col_bio, col_elo = st.columns([2, 1])

with col_bio:
    dob_raw = row.get("dob")
    dob_str = format_date_dd_mm_yyyy(int(dob_raw)) if dob_raw and str(dob_raw) not in ("nan", "None", "") else "—"
    country = row.get("pays") or "—"
    st.markdown(f"## {selected_name}")
    st.markdown(f"**Nationalité :** {country} &nbsp;|&nbsp; **Naissance :** {dob_str} &nbsp;|&nbsp; **Circuit :** {circuit}")

with col_elo:
    st.markdown("#### Ratings Elo actuels")
    e1, e2 = st.columns(2)
    with e1:
        st.metric("Global", format_elo(row.get("elo_global")))
        st.metric("Dur", format_elo(row.get("elo_hard")))
    with e2:
        st.metric("Terre", format_elo(row.get("elo_clay")))
        st.metric("Gazon", format_elo(row.get("elo_grass")))

st.divider()

# ── Section B — Stats carrière ────────────────────────────────────────────────
st.subheader("Statistiques carrière")

career = _career_stats(str(_ROOT), player_id)

if not career.empty:
    r = career.iloc[0]

    def _safe_float(v: object) -> float | None:
        try:
            f = float(v)
            return None if math.isnan(f) else f
        except (TypeError, ValueError):
            return None

    total = int(r["total"])
    wins = int(r["wins"])
    win_pct = _safe_float(r["win_pct"]) or 0.0
    avg_aces = _safe_float(r["avg_aces"])
    avg_df = _safe_float(r["avg_df"])
    avg_dur = _safe_float(r["avg_duration"])
    tournaments = int(r["tournaments"])

    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        st.metric("Bilan", f"{wins}V / {total - wins}D", f"{win_pct:.1f} %")
    with mc2:
        st.metric("Tournois joués", str(tournaments))
    with mc3:
        st.metric("Aces / match (moy.)", f"{avg_aces:.1f}" if avg_aces is not None else "—")
    with mc4:
        st.metric("Durée moy. (min)", f"{int(avg_dur)}" if avg_dur is not None else "—")

# Stats par surface
surface_df = _surface_stats(str(_ROOT), player_id)

if not surface_df.empty:
    st.markdown("##### Par surface")
    SURF_COLORS = {"Hard": TENNIS_HARD, "Clay": TENNIS_CLAY, "Grass": TENNIS_GREEN}

    fig_surf = go.Figure()
    fig_surf.add_trace(go.Bar(
        name="Victoires",
        x=surface_df["surface"],
        y=surface_df["wins"],
        marker_color=TENNIS_GREEN,
    ))
    fig_surf.add_trace(go.Bar(
        name="Défaites",
        x=surface_df["surface"],
        y=surface_df["losses"],
        marker_color=TENNIS_CLAY,
    ))
    fig_surf.update_layout(barmode="group", title="Victoires et défaites par surface")
    apply_tennis_theme(fig_surf)
    st.plotly_chart(fig_surf, use_container_width=True)

st.divider()

# ── Section C — Évolution Elo ─────────────────────────────────────────────────
st.subheader("Évolution du rating Elo")

elo_hist = _elo_history(str(_ROOT), player_id)

if not elo_hist.empty and "date" in elo_hist.columns:
    fig_elo = go.Figure()
    traces = [
        ("elo_global", "Global", TENNIS_LINE, True),
        ("elo_hard", "Dur", TENNIS_HARD, "legendonly"),
        ("elo_clay", "Terre battue", TENNIS_CLAY, "legendonly"),
        ("elo_grass", "Gazon", TENNIS_GREEN, "legendonly"),
    ]
    for col, label, color, visible in traces:
        if col in elo_hist.columns:
            fig_elo.add_trace(go.Scatter(
                x=elo_hist["date"],
                y=elo_hist[col],
                mode="lines",
                name=label,
                line=dict(color=color, width=2),
                visible=visible,
            ))
    fig_elo.update_layout(
        title=f"Évolution Elo — {selected_name}",
        xaxis_title="Date",
        yaxis_title="Rating Elo",
        hovermode="x unified",
    )
    apply_tennis_theme(fig_elo)
    st.plotly_chart(fig_elo, use_container_width=True)
else:
    st.info("Historique Elo indisponible. Relancez `uv run python -m transformation.build_elo`.")

st.divider()

# ── Section D — Derniers matchs ───────────────────────────────────────────────
st.subheader("20 derniers matchs")

recent = _recent_matches(str(_ROOT), player_id)

if recent.empty:
    st.info("Aucun match disponible pour ce joueur.")
else:
    display = recent.copy()
    display["Date"] = display["tourney_date"].map(format_date_dd_mm_yyyy)
    display = display.rename(columns={
        "tourney_name": "Tournoi",
        "surface": "Surface",
        "round": "Tour",
        "résultat": "Résultat",
        "adversaire": "Adversaire",
        "score": "Score",
        "minutes": "Durée (min)",
    })
    st.dataframe(
        display[["Date", "Tournoi", "Surface", "Tour", "Résultat", "Adversaire", "Score", "Durée (min)"]],
        use_container_width=True,
        hide_index=True,
    )
