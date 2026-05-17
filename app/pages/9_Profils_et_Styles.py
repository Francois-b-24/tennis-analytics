"""Page Profils & Styles : clustering automatique + indice de polyvalence."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from components._bootstrap import init_app

_ROOT, _ = init_app(__file__)

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from components.plotly_theme import (
    TENNIS_CLAY,
    TENNIS_GREEN,
    TENNIS_HARD,
    TENNIS_LINE,
    apply_tennis_theme,
)
from components.widgets import (
    circuit_selectbox,
    format_elo,
    inject_global_css,
    page_info,
    player_selectbox,
)
from db.duckdb_session import create_connection

st.set_page_config(page_title="Profils & Styles — Tennis Analytics", layout="wide")
inject_global_css()


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return create_connection(_ROOT)


# Labels métier pour les clusters — assignés a posteriori en fonction du centroïde
# (méthode : on regarde quelle feature domine pour chaque cluster).
CLUSTER_LABELS_TEMPLATE = {
    "big_server": "🚀 Gros serveur",
    "aggressive_baseliner": "💥 Frappe puissante",
    "all_courter": "🎯 Joueur complet",
    "counter_puncher": "🧱 Mur défensif",
    "clutch": "🥶 Sang-froid clutch",
    "inconsistent": "🎲 Joueur irrégulier",
}


@st.cache_data(show_spinner=False)
def _player_aggregates(_root: str, circuit: str, min_matches: int = 50) -> pd.DataFrame:
    """Agrège les statistiques de jeu par joueur (winner + loser unifiés).

    Construit les features comportementales utiles au clustering :
    - ace_per_svgm : aces / jeu de service (intensité service)
    - df_per_svgm : double-fautes / jeu de service (fragilité service)
    - first_in_pct : % de 1res balles entrées (consistance)
    - first_won_pct : % points gagnés sur 1re balle (puissance service)
    - second_won_pct : % points gagnés sur 2e balle (sécurité 2e)
    - bp_saved_pct : % BP sauvées (mental clutch)
    """
    cf_match = "AND circuit = ?" if circuit in ("ATP", "WTA") else ""
    cf_player = "WHERE p.circuit = ?" if circuit in ("ATP", "WTA") else ""
    params: list = []
    if circuit in ("ATP", "WTA"):
        # ordre : 2 fois dans la sous-requête, 1 fois dans le join final
        params = [circuit, circuit, circuit]

    sql = f"""
        WITH winner_lines AS (
            SELECT winner_id AS player_id,
                   w_ace AS ace, w_df AS df, w_svpt AS svpt,
                   w_1stIn AS first_in, w_1stWon AS first_won,
                   w_2ndWon AS second_won, w_SvGms AS sv_games,
                   w_bpSaved AS bp_saved, w_bpFaced AS bp_faced,
                   1 AS is_win
            FROM v_matches
            WHERE w_svpt IS NOT NULL AND w_svpt > 0 {cf_match}
        ),
        loser_lines AS (
            SELECT loser_id AS player_id,
                   l_ace AS ace, l_df AS df, l_svpt AS svpt,
                   l_1stIn AS first_in, l_1stWon AS first_won,
                   l_2ndWon AS second_won, l_SvGms AS sv_games,
                   l_bpSaved AS bp_saved, l_bpFaced AS bp_faced,
                   0 AS is_win
            FROM v_matches
            WHERE l_svpt IS NOT NULL AND l_svpt > 0 {cf_match}
        ),
        all_lines AS (
            SELECT * FROM winner_lines UNION ALL SELECT * FROM loser_lines
        ),
        agg AS (
            SELECT player_id,
                   COUNT(*) AS n_matches,
                   SUM(is_win) AS wins,
                   SUM(ace) AS total_ace, SUM(df) AS total_df,
                   SUM(svpt) AS total_svpt,
                   SUM(first_in) AS total_first_in,
                   SUM(first_won) AS total_first_won,
                   SUM(second_won) AS total_second_won,
                   SUM(sv_games) AS total_sv_games,
                   SUM(bp_saved) AS total_bp_saved,
                   SUM(bp_faced) AS total_bp_faced
            FROM all_lines
            GROUP BY player_id
            HAVING COUNT(*) >= {min_matches}
        )
        SELECT
            a.player_id,
            TRIM(CONCAT(COALESCE(ANY_VALUE(p.name_first), ''), ' ',
                        COALESCE(ANY_VALUE(p.name_last), ''))) AS full_name,
            ANY_VALUE(p.ioc) AS ioc,
            a.n_matches,
            a.wins,
            a.total_ace::DOUBLE / NULLIF(a.total_sv_games, 0) AS ace_per_svgm,
            a.total_df::DOUBLE  / NULLIF(a.total_sv_games, 0) AS df_per_svgm,
            a.total_first_in::DOUBLE   / NULLIF(a.total_svpt, 0) AS first_in_pct,
            a.total_first_won::DOUBLE  / NULLIF(a.total_first_in, 0) AS first_won_pct,
            a.total_second_won::DOUBLE / NULLIF(a.total_svpt - a.total_first_in, 0)
                AS second_won_pct,
            a.total_bp_saved::DOUBLE   / NULLIF(a.total_bp_faced, 0) AS bp_saved_pct
        FROM agg a
        LEFT JOIN v_players p ON a.player_id = p.player_id {cf_player}
        GROUP BY a.player_id, a.n_matches, a.wins, a.total_ace, a.total_df,
                 a.total_sv_games, a.total_svpt, a.total_first_in,
                 a.total_first_won, a.total_second_won,
                 a.total_bp_saved, a.total_bp_faced
        HAVING TRIM(full_name) <> ''
    """
    try:
        return _connection().execute(sql, params).df()
    except duckdb.Error:
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def _versatility_index(_root: str, circuit: str, min_matches: int = 100) -> pd.DataFrame:
    """Calcule l'indice de polyvalence (low std => très polyvalent)."""
    cf = "WHERE p.circuit = ?" if circuit in ("ATP", "WTA") else ""
    params = [circuit] if circuit in ("ATP", "WTA") else []
    sql = f"""
        WITH counts AS (
            SELECT player_id, COUNT(*) AS n
            FROM (
                SELECT winner_id AS player_id FROM v_matches
                UNION ALL
                SELECT loser_id  AS player_id FROM v_matches
            ) GROUP BY player_id HAVING COUNT(*) >= {min_matches}
        )
        SELECT
            e.player_id,
            TRIM(CONCAT(COALESCE(ANY_VALUE(p.name_first), ''), ' ',
                        COALESCE(ANY_VALUE(p.name_last), ''))) AS full_name,
            ANY_VALUE(p.ioc) AS ioc,
            e.elo_global, e.elo_hard, e.elo_clay, e.elo_grass
        FROM v_elo_latest e
        JOIN counts c ON c.player_id = e.player_id
        LEFT JOIN v_players p ON p.player_id = e.player_id {cf}
        WHERE e.elo_hard IS NOT NULL AND e.elo_clay IS NOT NULL AND e.elo_grass IS NOT NULL
        GROUP BY e.player_id, e.elo_global, e.elo_hard, e.elo_clay, e.elo_grass
        HAVING TRIM(full_name) <> ''
    """
    try:
        df = _connection().execute(sql, params).df()
    except duckdb.Error:
        return pd.DataFrame()
    if df.empty:
        return df
    # Calcul polyvalence : plus l'écart-type Elo par surface est petit, plus le joueur est polyvalent.
    # On normalise sur [0, 100] : 100 = parfaitement polyvalent, 0 = ultra spécialiste.
    surf_stds = df[["elo_hard", "elo_clay", "elo_grass"]].std(axis=1)
    max_std = surf_stds.quantile(0.95)  # robuste aux outliers
    df["versatility"] = (1 - (surf_stds / max(max_std, 1)).clip(0, 1)) * 100
    return df.sort_values("versatility", ascending=False).reset_index(drop=True)


def _label_clusters(centers: np.ndarray, feature_names: list[str]) -> list[str]:
    """Attribue un label métier à chaque cluster selon la feature qui domine.

    Heuristique simple : on regarde la feature avec la valeur centrée la plus élevée
    (en valeur absolue) pour chaque cluster.
    """
    labels: list[str] = []
    n_clusters = centers.shape[0]
    for i in range(n_clusters):
        c = centers[i]
        top_idx = int(np.argmax(np.abs(c)))
        top_feat = feature_names[top_idx]
        sign = c[top_idx]
        if top_feat == "ace_per_svgm" and sign > 0:
            labels.append(CLUSTER_LABELS_TEMPLATE["big_server"])
        elif top_feat == "first_won_pct" and sign > 0:
            labels.append(CLUSTER_LABELS_TEMPLATE["aggressive_baseliner"])
        elif top_feat == "bp_saved_pct" and sign > 0:
            labels.append(CLUSTER_LABELS_TEMPLATE["clutch"])
        elif top_feat == "df_per_svgm" and sign > 0:
            labels.append(CLUSTER_LABELS_TEMPLATE["inconsistent"])
        elif top_feat == "second_won_pct" and sign > 0:
            labels.append(CLUSTER_LABELS_TEMPLATE["counter_puncher"])
        else:
            labels.append(CLUSTER_LABELS_TEMPLATE["all_courter"])
    # Si doublons (deux clusters même label), suffixer
    seen: dict[str, int] = {}
    out: list[str] = []
    for label in labels:
        seen[label] = seen.get(label, 0) + 1
        out.append(label if seen[label] == 1 else f"{label} {seen[label]}")
    return out


# ── Sidebar ───────────────────────────────────────────────────────────────────
circuit = circuit_selectbox(key="profile_circuit", include_all=False, default="ATP")
n_clusters = st.sidebar.slider("Nombre de styles (clusters)", 3, 6, value=5)
min_matches = st.sidebar.slider("Matchs minimum", 50, 300, value=100, step=10)

st.title("Profils & Styles de jeu")
page_info(
    "Identifie automatiquement les styles de jeu par regroupement statistique (KMeans) "
    "sur les indicateurs de service et de break-points. Mesure également la polyvalence "
    "des joueurs (capacité à performer sur les 3 surfaces principales)."
)

# ── Section A — Clustering KMeans ─────────────────────────────────────────────
agg = _player_aggregates(str(_ROOT), circuit, min_matches=min_matches)

if agg.empty:
    st.warning(
        "Données insuffisantes pour le clustering. "
        "Augmentez la limite des matchs ou vérifiez l'ingestion."
    )
    st.stop()

FEATURES = [
    "ace_per_svgm",
    "df_per_svgm",
    "first_in_pct",
    "first_won_pct",
    "second_won_pct",
    "bp_saved_pct",
]
FEATURE_LABELS_FR = {
    "ace_per_svgm": "Aces / jeu service",
    "df_per_svgm": "Doubles fautes / jeu",
    "first_in_pct": "% 1res balles in",
    "first_won_pct": "% pts gagnés 1re balle",
    "second_won_pct": "% pts gagnés 2e balle",
    "bp_saved_pct": "% BP sauvées",
}

X = agg[FEATURES].dropna()
agg_valid = agg.loc[X.index].reset_index(drop=True)
X = X.reset_index(drop=True)

if len(X) < n_clusters + 1:
    st.warning("Pas assez de joueurs avec stats complètes pour effectuer le clustering.")
    st.stop()

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

km = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
agg_valid["cluster"] = km.fit_predict(X_scaled)
cluster_labels = _label_clusters(km.cluster_centers_, FEATURES)
agg_valid["style"] = agg_valid["cluster"].map(dict(enumerate(cluster_labels)))

# Projection 2D pour visualisation
pca = PCA(n_components=2, random_state=42)
coords = pca.fit_transform(X_scaled)
agg_valid["pc1"] = coords[:, 0]
agg_valid["pc2"] = coords[:, 1]
agg_valid["wins_pct"] = (agg_valid["wins"] / agg_valid["n_matches"] * 100).round(1)

st.subheader(f"Carte des styles ({n_clusters} clusters, {len(agg_valid)} joueurs)")

cluster_colors = [
    TENNIS_HARD,
    TENNIS_CLAY,
    TENNIS_GREEN,
    "#9B59B6",
    "#E67E22",
    "#3498DB",
][:n_clusters]

fig_scatter = go.Figure()
for cid in sorted(agg_valid["cluster"].unique()):
    sub = agg_valid[agg_valid["cluster"] == cid]
    fig_scatter.add_trace(
        go.Scatter(
            x=sub["pc1"],
            y=sub["pc2"],
            mode="markers",
            name=cluster_labels[cid],
            marker=dict(
                size=8 + sub["n_matches"] / 80,  # taille = nb matchs
                color=cluster_colors[cid],
                opacity=0.7,
                line=dict(width=0.5, color="white"),
            ),
            text=sub["full_name"],
            customdata=np.stack(
                [sub["n_matches"], sub["wins_pct"]],
                axis=-1,
            ),
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Style : " + cluster_labels[cid] + "<br>"
                "Matchs : %{customdata[0]}<br>"
                "Victoires : %{customdata[1]} %<extra></extra>"
            ),
        )
    )
fig_scatter.update_layout(
    title="Projection PCA des styles de jeu (taille = nb matchs joués)",
    xaxis_title=f"Composante 1 ({pca.explained_variance_ratio_[0] * 100:.0f} % variance)",
    yaxis_title=f"Composante 2 ({pca.explained_variance_ratio_[1] * 100:.0f} % variance)",
    height=550,
    legend=dict(orientation="h", y=-0.15),
)
apply_tennis_theme(fig_scatter)
st.plotly_chart(fig_scatter, use_container_width=True)

# Caractéristiques de chaque cluster
with st.expander("📊 Profil moyen de chaque style"):
    summary = agg_valid.groupby("style")[FEATURES].mean().rename(columns=FEATURE_LABELS_FR).round(3)
    summary["Joueurs"] = agg_valid.groupby("style").size()
    st.dataframe(summary, use_container_width=True)

st.divider()

# ── Section B — Zoom sur un joueur ───────────────────────────────────────────
st.subheader("Zoom sur un joueur")

player_options = agg_valid[["player_id", "full_name", "ioc"]].copy()
selected_id = player_selectbox(
    "Joueur (parmi les " + str(len(player_options)) + " avec stats complètes)",
    player_options,
    key="profile_player_zoom",
)

if selected_id is not None:
    row = agg_valid[agg_valid["player_id"] == selected_id].iloc[0]
    zcol1, zcol2, zcol3 = st.columns([1, 1, 2])
    with zcol1:
        st.metric("Style détecté", row["style"])
        st.metric("Matchs joués", int(row["n_matches"]))
    with zcol2:
        st.metric("Victoires", f"{int(row['wins'])} ({row['wins_pct']:.1f} %)")
    with zcol3:
        # Radar des 6 features du joueur vs médiane globale
        values_player = [row[f] for f in FEATURES]
        values_median = [float(agg_valid[f].median()) for f in FEATURES]
        labels = [FEATURE_LABELS_FR[f] for f in FEATURES]

        fig_radar = go.Figure()
        fig_radar.add_trace(
            go.Scatterpolar(
                r=[*values_median, values_median[0]],
                theta=[*labels, labels[0]],
                fill="toself",
                name="Médiane",
                line=dict(color=TENNIS_LINE, width=1, dash="dot"),
                fillcolor="rgba(150,150,150,0.15)",
            )
        )
        fig_radar.add_trace(
            go.Scatterpolar(
                r=[*values_player, values_player[0]],
                theta=[*labels, labels[0]],
                fill="toself",
                name=str(row["full_name"]),
                line=dict(color=TENNIS_GREEN, width=2),
                fillcolor="rgba(58,125,68,0.25)",
            )
        )
        fig_radar.update_layout(
            title="Profil vs médiane",
            height=380,
            polar=dict(radialaxis=dict(visible=True, showticklabels=False)),
            showlegend=True,
        )
        apply_tennis_theme(fig_radar)
        st.plotly_chart(fig_radar, use_container_width=True)

st.divider()

# ── Section C — Indice de polyvalence ────────────────────────────────────────
st.subheader("Indice de polyvalence multi-surface")
page_info(
    "Mesure la régularité d'un joueur entre Dur, Terre battue et Gazon : "
    "100 = excelle uniformément sur les 3 surfaces, 0 = ultra-spécialiste. "
    "Calculé sur l'écart-type des 3 Elos surface, normalisé."
)

vers = _versatility_index(str(_ROOT), circuit, min_matches=min_matches)

if vers.empty:
    st.info("Données Elo par surface indisponibles.")
else:
    top_v = vers.head(20)
    fig_v = go.Figure(
        go.Bar(
            x=top_v["versatility"][::-1],
            y=top_v["full_name"][::-1],
            orientation="h",
            marker=dict(
                color=top_v["versatility"][::-1],
                colorscale=[[0, TENNIS_CLAY], [1, TENNIS_GREEN]],
                showscale=False,
            ),
            text=[f"{v:.0f}" for v in top_v["versatility"][::-1]],
            textposition="outside",
            customdata=np.stack(
                [
                    top_v["elo_hard"][::-1],
                    top_v["elo_clay"][::-1],
                    top_v["elo_grass"][::-1],
                ],
                axis=-1,
            ),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Polyvalence : %{x:.0f}/100<br>"
                "Elo Dur : %{customdata[0]:.0f}<br>"
                "Elo Terre : %{customdata[1]:.0f}<br>"
                "Elo Gazon : %{customdata[2]:.0f}<extra></extra>"
            ),
        )
    )
    fig_v.update_layout(
        title=f"Top 20 joueurs polyvalents — {circuit}",
        xaxis_title="Indice de polyvalence (0–100)",
        yaxis_title=None,
        height=620,
        margin=dict(l=10, r=60),
    )
    apply_tennis_theme(fig_v)
    st.plotly_chart(fig_v, use_container_width=True)

    # Tableau détaillé
    with st.expander("Voir le classement complet"):
        display_v = vers.copy()
        for col in ("elo_global", "elo_hard", "elo_clay", "elo_grass"):
            display_v[col] = display_v[col].map(lambda v: format_elo(v) if pd.notna(v) else "—")
        display_v["versatility"] = display_v["versatility"].round(1)
        display_v.insert(0, "Rang", range(1, len(display_v) + 1))
        st.dataframe(
            display_v[
                [
                    "Rang",
                    "full_name",
                    "versatility",
                    "elo_global",
                    "elo_hard",
                    "elo_clay",
                    "elo_grass",
                ]
            ].rename(
                columns={
                    "full_name": "Joueur",
                    "versatility": "Polyvalence",
                    "elo_global": "Global",
                    "elo_hard": "Dur",
                    "elo_clay": "Terre",
                    "elo_grass": "Gazon",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
