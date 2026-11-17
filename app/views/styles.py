"""Styles de jeu : regroupement automatique des profils au service et polyvalence."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components._bootstrap import data_key, init_app
from components.plotly_theme import ACCENT, PALETTE, apply_tennis_theme
from components.widgets import (
    circuit_selectbox,
    df_styled,
    kpi_row,
    page_header,
    player_selectbox,
    section,
)

_ROOT, _CONNECTION = init_app(__file__)
_DATA_KEY = data_key(_ROOT)

FEATURES = {
    "ace_per_svgm": "Aces par jeu de service",
    "df_per_svgm": "Doubles fautes par jeu de service",
    "first_in_pct": "1res balles réussies",
    "first_won_pct": "Points gagnés sur 1re balle",
    "second_won_pct": "Points gagnés sur 2e balle",
    "bp_saved_pct": "Balles de break sauvées",
}

#: Nom d'un groupe selon l'indicateur où il dépasse le plus la moyenne.
STYLE_NAMES = {
    "ace_per_svgm": "Gros serveurs",
    "first_won_pct": "Attaquants",
    "bp_saved_pct": "Solides sous pression",
    "df_per_svgm": "Prise de risque au service",
    "second_won_pct": "Solides en 2e balle",
    "first_in_pct": "Réguliers au service",
}


def name_styles(centers: np.ndarray) -> list[str]:
    """Nom distinct pour chaque groupe : son point fort le plus marqué encore libre.

    Les groupes sont traités du profil le plus marqué au moins marqué ; un groupe
    sans point fort au-dessus de la moyenne est qualifié de « Profil équilibré ».
    """
    features = list(FEATURES)
    names: list[str] = [""] * len(centers)
    used: set[str] = set()
    for idx in np.argsort(-centers.max(axis=1)):
        for f in np.argsort(-centers[idx]):
            if centers[idx][f] <= 0.25:
                break
            if features[f] not in used:
                used.add(features[f])
                names[idx] = STYLE_NAMES[features[f]]
                break
        if not names[idx]:
            names[idx] = "Profil équilibré"
    seen: dict[str, int] = {}
    unique = []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        unique.append(name if seen[name] == 1 else f"{name} {seen[name]}")
    return unique


@st.cache_data(ttl=3600, show_spinner=False)
def _aggregates(cache_key: str, circuit: str, min_matches: int) -> pd.DataFrame:
    """Statistiques de service cumulées par joueur (matchs avec statistiques)."""
    return _CONNECTION.execute(
        """
        WITH lignes AS (
            SELECT winner_id AS pid, w_ace AS ace, w_df AS df, w_svpt AS svpt,
                   w_1stIn AS fin, w_1stWon AS fwon, w_2ndWon AS swon, w_SvGms AS games,
                   w_bpSaved AS bps, w_bpFaced AS bpf, 1 AS v
            FROM v_matches WHERE w_svpt > 0 AND circuit = ?
            UNION ALL
            SELECT loser_id, l_ace, l_df, l_svpt, l_1stIn, l_1stWon, l_2ndWon, l_SvGms,
                   l_bpSaved, l_bpFaced, 0
            FROM v_matches WHERE l_svpt > 0 AND circuit = ?
        ),
        agg AS (
            SELECT pid, COUNT(*) AS matchs, SUM(v) AS victoires,
                   SUM(ace) / NULLIF(SUM(games), 0) AS ace_per_svgm,
                   SUM(df) / NULLIF(SUM(games), 0) AS df_per_svgm,
                   SUM(fin) / NULLIF(SUM(svpt), 0) AS first_in_pct,
                   SUM(fwon) / NULLIF(SUM(fin), 0) AS first_won_pct,
                   SUM(swon) / NULLIF(SUM(svpt) - SUM(fin), 0) AS second_won_pct,
                   SUM(bps) / NULLIF(SUM(bpf), 0) AS bp_saved_pct
            FROM lignes GROUP BY pid HAVING COUNT(*) >= ?
        )
        SELECT a.*, p.ioc,
               TRIM(CONCAT(COALESCE(p.name_first, ''), ' ', COALESCE(p.name_last, ''))) AS full_name
        FROM agg a JOIN v_players p ON p.player_id = a.pid
        """,
        [circuit, circuit, min_matches],
    ).df()


@st.cache_data(ttl=3600, show_spinner=False)
def _versatility(cache_key: str, circuit: str, min_matches: int) -> pd.DataFrame:
    df = _CONNECTION.execute(
        """
        WITH n AS (
            SELECT pid, COUNT(*) AS matchs FROM (
                SELECT winner_id AS pid FROM v_matches WHERE circuit = ?
                UNION ALL SELECT loser_id FROM v_matches WHERE circuit = ?
            ) GROUP BY pid HAVING COUNT(*) >= ?
        )
        SELECT e.player_id,
               TRIM(CONCAT(COALESCE(p.name_first, ''), ' ', COALESCE(p.name_last, ''))) AS joueur,
               e.elo_global, e.elo_hard, e.elo_clay, e.elo_grass, n.matchs
        FROM v_elo_latest e JOIN n ON n.pid = e.player_id
        JOIN v_players p ON p.player_id = e.player_id
        """,
        [circuit, circuit, min_matches],
    ).df()
    if df.empty:
        return df
    spread = df[["elo_hard", "elo_clay", "elo_grass"]].std(axis=1)
    df["polyvalence"] = (1 - (spread / max(spread.quantile(0.95), 1)).clip(0, 1)) * 100
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def _clusters(cache_key: str, circuit: str, min_matches: int, n_styles: int) -> pd.DataFrame:
    """Regroupe les joueurs en `n_styles` profils (KMeans) et projette en 2D (ACP)."""
    # Import paresseux : scikit-learn n'est chargé que pour cette page.
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    data = _aggregates(cache_key, circuit, min_matches).dropna(subset=list(FEATURES))
    if len(data) <= n_styles:
        return pd.DataFrame()
    scaled = StandardScaler().fit_transform(data[list(FEATURES)])
    model = KMeans(n_clusters=n_styles, n_init=10, random_state=42).fit(scaled)
    unique = name_styles(model.cluster_centers_)
    coords = PCA(n_components=2, random_state=42).fit_transform(scaled)
    out = data.reset_index(drop=True).copy()
    out["style"] = [unique[c] for c in model.labels_]
    out["x"], out["y"] = coords[:, 0], coords[:, 1]
    out["pct_victoires"] = out["victoires"] / out["matchs"]
    return out


page_header(
    "Styles de jeu",
    subtitle=(
        "Les joueurs regroupés selon leur profil au service, et les plus polyvalents "
        "d'une surface à l'autre."
    ),
)
circuit = circuit_selectbox(include_all=False)
with st.expander("Réglages", icon=":material/tune:"):
    col1, col2 = st.columns(2)
    n_styles = col1.slider("Nombre de styles", 3, 6, 5)
    min_matches = col2.slider("Matchs minimum par joueur", 50, 300, 100, step=10)

players = _clusters(_DATA_KEY, circuit, min_matches, n_styles)
if players.empty:
    st.info("Pas assez de joueurs avec des statistiques complètes.")
    st.stop()

section(
    "Carte des styles",
    caption=(
        f"{len(players)} joueurs {circuit}. Deux joueurs proches sur la carte ont des "
        "statistiques au service semblables ; la taille du point suit le nombre de matchs."
    ),
)
fig = go.Figure()
for i, (style, group) in enumerate(players.groupby("style")):
    fig.add_trace(
        go.Scatter(
            x=group["x"],
            y=group["y"],
            mode="markers",
            name=f"{style} ({len(group)})",
            marker=dict(
                size=6 + group["matchs"] / 90,
                color=PALETTE[i % len(PALETTE)],
                symbol=["circle", "square", "diamond", "triangle-up", "x", "star"][i % 6],
                opacity=0.75,
            ),
            text=group["full_name"],
            customdata=np.stack([group["matchs"], group["pct_victoires"] * 100], axis=-1),
            hovertemplate="<b>%{text}</b><br>%{customdata[0]} matchs · %{customdata[1]:.0f} % de victoires<extra></extra>",
        )
    )
fig.update_xaxes(showticklabels=False, title_text="")
fig.update_yaxes(showticklabels=False, title_text="", showgrid=False)
fig.update_layout(hovermode="closest")
st.plotly_chart(apply_tennis_theme(fig, height=480), width="stretch")

summary = players.groupby("style")[list(FEATURES)].mean()
display = pd.DataFrame(
    {
        "Style": summary.index,
        "Joueurs": players.groupby("style").size().values,
        "Aces / jeu": summary["ace_per_svgm"].round(2).values,
        "1re balle gagnée": (summary["first_won_pct"] * 100).round(1).values,
        "2e balle gagnée": (summary["second_won_pct"] * 100).round(1).values,
        "Balles de break sauvées": (summary["bp_saved_pct"] * 100).round(1).values,
    }
)
df_styled(
    display,
    column_config={
        c: st.column_config.NumberColumn(format="%.1f %%")
        for c in ("1re balle gagnée", "2e balle gagnée", "Balles de break sauvées")
    },
)

section("Profil d'un joueur", level=3)
player_id = player_selectbox(
    "Joueur",
    players.rename(columns={"pid": "player_id"})[["player_id", "full_name", "ioc"]],
    key=f"styles_player_{circuit}",
    default_player_id=int(players.sort_values("matchs").iloc[-1]["pid"]),
)
if player_id is not None:
    row = players.loc[players["pid"] == player_id].iloc[0]
    kpi_row(
        [
            {"label": "Style", "value": row["style"]},
            {"label": "Matchs analysés", "value": int(row["matchs"])},
            {"label": "Victoires", "value": f"{row['pct_victoires']:.0%}"},
        ]
    )
    percentiles = {
        label: (
            float((players[col] <= row[col]).mean() * 100)
            if col != "df_per_svgm"
            else float((players[col] >= row[col]).mean() * 100)
        )
        for col, label in FEATURES.items()
    }
    labels = list(percentiles)[::-1]
    fig = go.Figure(
        go.Bar(
            x=[percentiles[k] for k in labels],
            y=labels,
            orientation="h",
            marker_color=ACCENT,
            text=[f"{percentiles[k]:.0f}" for k in labels],
            textposition="outside",
        )
    )
    fig.add_vline(x=50, line_dash="dot", annotation_text="médiane", annotation_position="top")
    fig.update_xaxes(range=[0, 105], title_text="Percentile (100 = meilleur du circuit)")
    fig.update_layout(hovermode="y")
    st.plotly_chart(apply_tennis_theme(fig, height=300), width="stretch")
    st.caption("Doubles fautes : un percentile élevé signifie peu de doubles fautes.")

section(
    "Les plus polyvalents",
    level=3,
    caption=(
        "Parmi les 50 meilleurs Elo : indice 100 = même niveau sur dur, terre battue et "
        "gazon ; 0 = très spécialisé."
    ),
)
versatile = _versatility(_DATA_KEY, circuit, min_matches)
if not versatile.empty:
    pool = versatile.nlargest(50, "elo_global")
    top = pool.sort_values(["polyvalence", "elo_global"], ascending=False).head(15)
    df_styled(
        pd.DataFrame(
            {
                "Joueur": top["joueur"],
                "Polyvalence": top["polyvalence"].round(0),
                "Elo dur": top["elo_hard"].round(0),
                "Elo terre": top["elo_clay"].round(0),
                "Elo gazon": top["elo_grass"].round(0),
            }
        ),
        column_config={
            "Polyvalence": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d")
        },
    )
st.caption("Statistiques de service disponibles jusqu'au 25/05/2026.")
