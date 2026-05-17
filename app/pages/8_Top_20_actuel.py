"""Page Top 20 : focus sur les 20 meilleurs joueurs ATP et WTA selon l'Elo global."""

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
from plotly.subplots import make_subplots

from components.plotly_theme import (
    TENNIS_CLAY,
    TENNIS_GREEN,
    TENNIS_HARD,
    TENNIS_LINE,
    apply_tennis_theme,
)
from components.widgets import (
    country_flag_with_code,
    df_styled,
    format_elo,
    inject_global_css,
    kpi_row,
    page_header,
    section,
)
from db.duckdb_session import create_connection

st.set_page_config(page_title="Top 20 actuel — Tennis Analytics", layout="wide")
inject_global_css()


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return create_connection(_ROOT)


def _country_column_name(conn: duckdb.DuckDBPyConnection) -> str:
    """Détecte le nom de la colonne pays dans v_players (schéma variable)."""
    cols = conn.execute("DESCRIBE v_players").df()["column_name"].tolist()
    if "ioc" in cols:
        return "ioc"
    if "country_code" in cols:
        return "country_code"
    return "NULL"  # fallback : pas de pays


@st.cache_data(show_spinner=False)
def _top20_per_circuit(_root: str, circuit: str) -> pd.DataFrame:
    """Top 20 joueurs d'un circuit selon Elo global, avec leurs ratings par surface."""
    conn = _connection()
    country_col = _country_column_name(conn)
    sql = f"""
        WITH player_unique AS (
            SELECT player_id,
                   ANY_VALUE(name_first) AS name_first,
                   ANY_VALUE(name_last) AS name_last,
                   ANY_VALUE({country_col}) AS pays_raw
            FROM v_players
            WHERE circuit = ?
            GROUP BY player_id
        )
        SELECT
            ROW_NUMBER() OVER (ORDER BY e.elo_global DESC NULLS LAST) AS rang,
            e.player_id,
            TRIM(CONCAT(COALESCE(p.name_first, ''), ' ', COALESCE(p.name_last, ''))) AS joueur,
            COALESCE(NULLIF(TRIM(CAST(p.pays_raw AS VARCHAR)), ''), '—') AS pays,
            ROUND(e.elo_global, 0) AS elo_global,
            ROUND(e.elo_hard,   0) AS elo_dur,
            ROUND(e.elo_clay,   0) AS elo_terre,
            ROUND(e.elo_grass,  0) AS elo_gazon,
            e.last_match_date
        FROM v_elo_latest e
        JOIN player_unique p ON e.player_id = p.player_id
        WHERE e.elo_global IS NOT NULL
          AND TRIM(CONCAT(COALESCE(p.name_first, ''), ' ', COALESCE(p.name_last, ''))) <> ''
        ORDER BY e.elo_global DESC NULLS LAST
        LIMIT 20
    """
    return conn.execute(sql, [circuit]).df()


@st.cache_data(show_spinner=False)
def _player_career_stats(_root: str, player_id: int) -> pd.DataFrame:
    """Stats de carrière agrégées d'un joueur."""
    return (
        _connection()
        .execute(
            """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wins,
            ROUND(
                SUM(CASE WHEN winner_id = ? THEN 1.0 ELSE 0.0 END) / NULLIF(COUNT(*), 0) * 100,
                1
            ) AS win_pct,
            COUNT(DISTINCT tourney_name) AS tournaments,
            ROUND(AVG(CASE WHEN winner_id = ? THEN w_ace ELSE l_ace END), 1) AS avg_aces,
            ROUND(AVG(CASE WHEN winner_id = ? THEN w_df  ELSE l_df  END), 1) AS avg_df,
            ROUND(AVG(minutes) FILTER (WHERE minutes > 0 AND minutes < 400), 0) AS avg_duration,
            SUM(CASE WHEN winner_id = ? AND round = 'F' THEN 1 ELSE 0 END) AS titres
        FROM v_matches
        WHERE winner_id = ? OR loser_id = ?
        """,
            [player_id] * 7,
        )
        .df()
    )


@st.cache_data(show_spinner=False)
def _player_recent_form(_root: str, player_id: int) -> tuple[float, list[str]]:
    """Forme sur les 20 derniers matchs (% victoires + séquence V/D)."""
    df = (
        _connection()
        .execute(
            """
        SELECT winner_id
        FROM v_matches
        WHERE winner_id = ? OR loser_id = ?
        ORDER BY tourney_date DESC
        LIMIT 20
        """,
            [player_id, player_id],
        )
        .df()
    )
    if df.empty:
        return 0.0, []
    seq = ["V" if w == player_id else "D" for w in df["winner_id"]]
    pct = sum(1 for x in seq if x == "V") / len(seq) * 100
    return pct, seq


@st.cache_data(show_spinner=False)
def _player_surface_winrate(_root: str, player_id: int) -> pd.DataFrame:
    """Taux de victoire par surface."""
    return (
        _connection()
        .execute(
            """
        SELECT
            COALESCE(NULLIF(surface, ''), 'Inconnue') AS surface,
            COUNT(*) AS total,
            SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wins,
            ROUND(
                SUM(CASE WHEN winner_id = ? THEN 1.0 ELSE 0.0 END) / NULLIF(COUNT(*), 0) * 100,
                1
            ) AS win_pct
        FROM v_matches
        WHERE winner_id = ? OR loser_id = ?
        GROUP BY surface
        HAVING COUNT(*) >= 5
        ORDER BY total DESC
        """,
            [player_id, player_id, player_id, player_id],
        )
        .df()
    )


@st.cache_data(show_spinner=False)
def _atp_vs_wta_top20_stats(_root: str) -> pd.DataFrame:
    """Stats agrégées comparées entre Top 20 ATP et Top 20 WTA."""
    return (
        _connection()
        .execute(
            """
        WITH top20 AS (
            SELECT player_id, p.circuit
            FROM v_elo_latest e
            JOIN v_players p USING (player_id)
            WHERE e.elo_global IS NOT NULL
            QUALIFY ROW_NUMBER() OVER (PARTITION BY p.circuit ORDER BY e.elo_global DESC) <= 20
        )
        SELECT
            t.circuit,
            ROUND(AVG(CASE WHEN m.winner_id = t.player_id THEN m.w_ace ELSE m.l_ace END), 2) AS aces_par_match,
            ROUND(AVG(CASE WHEN m.winner_id = t.player_id THEN m.w_df  ELSE m.l_df  END), 2) AS df_par_match,
            ROUND(
                AVG(m.minutes) FILTER (WHERE m.minutes > 0 AND m.minutes < 400),
                0
            ) AS duree_moy,
            ROUND(
                AVG(
                    CASE WHEN m.winner_id = t.player_id THEN m.w_bpSaved ELSE m.l_bpSaved END * 1.0
                  / NULLIF(CASE WHEN m.winner_id = t.player_id THEN m.w_bpFaced ELSE m.l_bpFaced END, 0)
                ) * 100,
                1
            ) AS bp_saves_pct
        FROM top20 t
        JOIN v_matches m ON (m.winner_id = t.player_id OR m.loser_id = t.player_id)
        WHERE m.w_ace IS NOT NULL
        GROUP BY t.circuit
        ORDER BY t.circuit
        """
        )
        .df()
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────
circuit_filter = st.sidebar.selectbox("Circuit", ["Les deux", "ATP", "WTA"], key="top20_circuit")

page_header(
    "Top 20 actuel — Élite mondiale",
    subtitle=(
        "20 meilleurs joueurs ATP et WTA selon leur rating Elo global le plus récent. "
        "Ratings par surface, forme récente, style de jeu, comparaison ATP vs WTA."
    ),
    icon="🌟",
)

# ── Données Top 20 ATP + WTA ─────────────────────────────────────────────────
top_atp = _top20_per_circuit(str(_ROOT), "ATP")
top_wta = _top20_per_circuit(str(_ROOT), "WTA")

if top_atp.empty and top_wta.empty:
    st.error("Aucune donnée Elo disponible.")
    st.stop()

# Filtre
if circuit_filter == "ATP":
    df_top = top_atp.copy()
elif circuit_filter == "WTA":
    df_top = top_wta.copy()
else:
    df_top = pd.concat([top_atp, top_wta], ignore_index=True)

# ── Section 1 : Tableau du Top 20 ────────────────────────────────────────────
section(f"Classement — {circuit_filter}", level=3)

display_df = df_top.copy()
if circuit_filter == "Les deux":
    display_df["Circuit"] = ["ATP"] * len(top_atp) + ["WTA"] * len(top_wta)

display_df["pays"] = display_df["pays"].apply(country_flag_with_code)

display_df = display_df.rename(
    columns={
        "rang": "Rang",
        "joueur": "Joueur",
        "pays": "Pays",
        "elo_global": "Elo global",
        "elo_dur": "Elo dur",
        "elo_terre": "Elo terre",
        "elo_gazon": "Elo gazon",
    }
)

ordered = ["Circuit", "Rang", "Joueur", "Pays", "Elo global", "Elo dur", "Elo terre", "Elo gazon"]
final_cols = [c for c in ordered if c in display_df.columns]

df_styled(
    display_df[final_cols],
    column_config={
        "Rang": st.column_config.NumberColumn(format="#%d"),
        "Elo global": st.column_config.NumberColumn(format="%d"),
        "Elo dur": st.column_config.NumberColumn(format="%d"),
        "Elo terre": st.column_config.NumberColumn(format="%d"),
        "Elo gazon": st.column_config.NumberColumn(format="%d"),
    },
)

# ── Section 2 : Focus joueur ─────────────────────────────────────────────────
section("Zoom sur un joueur", level=3, divider_before=True)


# Construit un label unique : "Joueur (PAYS)" pour eviter toute collision
def _build_label(row: pd.Series) -> str:
    name = str(row["joueur"]).strip()
    pays = str(row.get("pays", "")).strip()
    return f"{name} ({pays})" if pays and pays != "—" else name


df_top = df_top.copy()
df_top["_label"] = df_top.apply(_build_label, axis=1)
mapping = dict(zip(df_top["_label"], df_top["player_id"], strict=False))
selected = st.selectbox(
    "Sélectionner un joueur",
    list(mapping.keys()),
    key="top20_player_select",
    help="💡 Tapez pour rechercher",
    placeholder="Rechercher un joueur…",
)
pid = int(mapping[selected])

# Ligne du joueur (recherche par player_id pour eviter toute ambiguite)
row = df_top[df_top["player_id"] == pid].iloc[0]
selected_name = str(row["joueur"])

# Stats carrière
career = _player_career_stats(str(_ROOT), pid)
form_pct, form_seq = _player_recent_form(str(_ROOT), pid)
surf_winrate = _player_surface_winrate(str(_ROOT), pid)

# Carte d'identité — métriques principales
import math as _m

_wins_raw = career.iloc[0]["wins"] if not career.empty else None
_win_pct_raw = career.iloc[0]["win_pct"] if not career.empty else None
_wins = (
    0
    if _wins_raw is None or (isinstance(_wins_raw, float) and _m.isnan(_wins_raw))
    else int(_wins_raw)
)
_wp = (
    0.0
    if _win_pct_raw is None or (isinstance(_win_pct_raw, float) and _m.isnan(_win_pct_raw))
    else float(_win_pct_raw)
)
kpi_row(
    [
        {"label": "Rang", "value": f"#{int(row['rang'])}", "icon": "🥇"},
        {"label": "Elo global", "value": format_elo(row["elo_global"]), "icon": "📊"},
        {"label": "Bilan carrière", "value": f"{_wins} V", "delta": f"{_wp:.1f} %", "icon": "🎾"},
        {"label": "Forme (20 derniers)", "value": f"{form_pct:.0f} %", "icon": "📈"},
    ]
)

# Séquence V/D visuelle
if form_seq:
    seq_html = " ".join(
        f"<span style='display:inline-block;width:22px;height:22px;line-height:22px;"
        f"text-align:center;border-radius:4px;margin:1px;color:white;font-size:11px;"
        f"font-weight:600;background:{TENNIS_GREEN if v == 'V' else TENNIS_CLAY}'>{v}</span>"
        for v in form_seq
    )
    st.markdown(
        f"<div style='margin-top:8px'><strong>20 derniers matchs :</strong><br>{seq_html}</div>",
        unsafe_allow_html=True,
    )

st.markdown("")  # espacement

# Profil 3 colonnes : Elo radar + Surface bars + Style stats
col_a, col_b, col_c = st.columns(3)

# A) Radar des 4 Elo
with col_a:
    st.markdown("##### Profil Elo multi-surface")
    fig_radar = go.Figure()
    surfaces = ["Global", "Dur", "Terre", "Gazon"]
    values = [
        float(row["elo_global"] or 0),
        float(row["elo_dur"] or 0),
        float(row["elo_terre"] or 0),
        float(row["elo_gazon"] or 0),
    ]
    fig_radar.add_trace(
        go.Scatterpolar(
            r=[*values, values[0]],
            theta=[*surfaces, surfaces[0]],
            fill="toself",
            line=dict(color=TENNIS_HARD, width=2),
            fillcolor="rgba(31, 78, 121, 0.25)",
            name=selected_name,
        )
    )
    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[1500, max(values) + 50]),
        ),
        showlegend=False,
        height=320,
        margin=dict(l=20, r=20, t=20, b=20),
    )
    apply_tennis_theme(fig_radar)
    st.plotly_chart(fig_radar, use_container_width=True)

# B) % Victoires par surface
with col_b:
    st.markdown("##### % victoires par surface")
    if not surf_winrate.empty:
        SURF_COLORS = {"Hard": TENNIS_HARD, "Clay": TENNIS_CLAY, "Grass": TENNIS_GREEN}
        colors = [SURF_COLORS.get(s, TENNIS_LINE) for s in surf_winrate["surface"]]
        fig_surf = go.Figure(
            go.Bar(
                x=surf_winrate["surface"],
                y=surf_winrate["win_pct"],
                marker_color=colors,
                text=[f"{v:.0f}%" for v in surf_winrate["win_pct"]],
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>%{y}% sur %{customdata} matchs<extra></extra>",
                customdata=surf_winrate["total"],
            )
        )
        fig_surf.update_layout(
            yaxis_title="% victoires",
            yaxis=dict(range=[0, 100]),
            height=320,
            showlegend=False,
            margin=dict(l=40, r=20, t=20, b=40),
        )
        apply_tennis_theme(fig_surf)
        st.plotly_chart(fig_surf, use_container_width=True)
    else:
        st.info("Pas assez de matchs pour calculer un taux par surface.")

# C) Style de jeu
with col_c:
    st.markdown("##### Style de jeu")
    if not career.empty:
        c = career.iloc[0]

        def fmt(v, suffix="", default="—"):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return default
            return f"{v:.1f}{suffix}" if isinstance(v, float) else f"{v}{suffix}"

        st.metric("Aces / match", fmt(c["avg_aces"]))
        st.metric("Double-fautes / match", fmt(c["avg_df"]))
        if c["avg_duration"] and not pd.isna(c["avg_duration"]):
            st.metric("Durée moyenne", f"{int(c['avg_duration'])} min")
        if c["tournaments"]:
            st.metric("Tournois joués", f"{int(c['tournaments'])}")

# ── Section 3 : Comparaison ATP vs WTA ───────────────────────────────────────
section("Comparaison structurelle ATP vs WTA", level=3, divider_before=True)
st.caption("Stats moyennes calculées sur tous les matchs joués par les Top 20 de chaque circuit.")

cmp = _atp_vs_wta_top20_stats(str(_ROOT))

if cmp.empty or len(cmp) < 2:
    st.info("Données insuffisantes pour la comparaison.")
else:
    fig_cmp = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Aces / match",
            "Double-fautes / match",
            "Durée moyenne (min)",
            "% Break points sauvés",
        ),
        vertical_spacing=0.18,
        horizontal_spacing=0.18,
    )

    metrics = [
        ("aces_par_match", 1, 1),
        ("df_par_match", 1, 2),
        ("duree_moy", 2, 1),
        ("bp_saves_pct", 2, 2),
    ]

    for col, row_pos, col_pos in metrics:
        fig_cmp.add_trace(
            go.Bar(
                x=cmp["circuit"],
                y=cmp[col],
                marker_color=[TENNIS_HARD if c == "ATP" else TENNIS_CLAY for c in cmp["circuit"]],
                text=cmp[col].round(1),
                textposition="outside",
                showlegend=False,
                hovertemplate="<b>%{x}</b><br>%{y}<extra></extra>",
            ),
            row=row_pos,
            col=col_pos,
        )

    fig_cmp.update_layout(
        height=550,
        showlegend=False,
        margin=dict(l=40, r=20, t=60, b=40),
    )
    apply_tennis_theme(fig_cmp)
    st.plotly_chart(fig_cmp, use_container_width=True)

    # Lecture rapide
    if len(cmp) == 2:
        atp_row = cmp[cmp["circuit"] == "ATP"].iloc[0]
        wta_row = cmp[cmp["circuit"] == "WTA"].iloc[0]
        st.markdown(
            f"""
            **Lecture rapide :**
            - 🎾 Les Top 20 ATP servent en moyenne **{atp_row['aces_par_match']:.1f} aces / match**
              contre **{wta_row['aces_par_match']:.1f}** côté WTA.
            - ⏱️ Un match d'élite ATP dure en moyenne **{int(atp_row['duree_moy'])} min**,
              contre **{int(wta_row['duree_moy'])} min** en WTA.
            - 🛡️ Les Top 20 ATP sauvent **{atp_row['bp_saves_pct']:.1f} %** de leurs balles de break,
              les WTA **{wta_row['bp_saves_pct']:.1f} %**.
            """
        )
