"""Face-à-face : bilan des confrontations, favori Elo par surface, historique."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components._bootstrap import data_key, init_app
from components.plotly_theme import PALETTE, apply_tennis_theme
from components.queries import player_elo, player_options, top_player_ids
from components.widgets import (
    circuit_selectbox,
    df_styled,
    disambiguate_player_labels,
    kpi_row,
    page_header,
    player_selectbox,
    round_fr,
    section,
    surface_fr,
    to_date,
)

_ROOT, _CONNECTION = init_app(__file__)
_DATA_KEY = data_key(_ROOT)

SURFACES = {
    "Global": "elo_global",
    "Dur": "elo_hard",
    "Terre battue": "elo_clay",
    "Gazon": "elo_grass",
}
COLOR_A, COLOR_B = PALETTE[0], PALETTE[1]


@st.cache_data(ttl=3600, show_spinner=False)
def _h2h_matches(cache_key: str, player_a: int, player_b: int) -> pd.DataFrame:
    return _CONNECTION.execute(
        """
        SELECT COALESCE(match_date, tourney_date) AS jour, tourney_name, surface, round,
               winner_id, loser_id, winner_name, loser_name, score,
               w_ace, w_df, w_svpt, w_1stIn, w_1stWon, w_bpSaved, w_bpFaced,
               l_ace, l_df, l_svpt, l_1stIn, l_1stWon, l_bpSaved, l_bpFaced
        FROM v_matches
        WHERE (winner_id = ? AND loser_id = ?) OR (winner_id = ? AND loser_id = ?)
        ORDER BY jour DESC
        """,
        [player_a, player_b, player_b, player_a],
    ).df()


def _serve_profile(frame: pd.DataFrame, player_id: int) -> dict[str, float]:
    """Ratios moyens au service du joueur sur leurs confrontations."""

    def ratio(num: str, den: str) -> float:
        won = frame["winner_id"] == player_id
        values = pd.concat(
            [
                frame.loc[won, f"w_{num}"] / frame.loc[won, f"w_{den}"].replace(0, np.nan),
                frame.loc[~won, f"l_{num}"] / frame.loc[~won, f"l_{den}"].replace(0, np.nan),
            ]
        )
        values = values.replace([np.inf, -np.inf], np.nan).dropna()
        return float(values.mean()) if len(values) else float("nan")

    return {
        "Aces (% des points de service)": ratio("ace", "svpt"),
        "Doubles fautes (%)": ratio("df", "svpt"),
        "1res balles réussies (%)": ratio("1stIn", "svpt"),
        "Points gagnés sur 1re balle (%)": ratio("1stWon", "1stIn"),
        "Balles de break sauvées (%)": ratio("bpSaved", "bpFaced"),
    }


circuit = circuit_selectbox()
page_header(
    "Face-à-face",
    subtitle="Bilan de leurs confrontations, favori selon l'Elo et historique complet.",
)

players = player_options(_DATA_KEY, circuit)
if players.empty:
    st.warning("Aucun joueur disponible pour ce circuit.")
    st.stop()
players = disambiguate_player_labels(players)
defaults = top_player_ids(_DATA_KEY, circuit, 2)
col_a, col_b = st.columns(2)
with col_a:
    player_a = player_selectbox(
        "Joueur A",
        players,
        key=f"h2h_a_{circuit}",
        default_player_id=defaults[0] if defaults else None,
    )
with col_b:
    player_b = player_selectbox(
        "Joueur B",
        players,
        key=f"h2h_b_{circuit}",
        default_index=1,
        default_player_id=defaults[1] if len(defaults) > 1 else None,
    )
if player_a is None or player_b is None or player_a == player_b:
    st.warning("Choisissez deux joueurs différents.")
    st.stop()

name_of = dict(zip(players["player_id"], players["full_name"], strict=False))
name_a, name_b = name_of[player_a], name_of[player_b]
matches = _h2h_matches(_DATA_KEY, player_a, player_b)
wins_a = int((matches["winner_id"] == player_a).sum())
wins_b = int((matches["winner_id"] == player_b).sum())

kpi_row(
    [
        {"label": f"Victoires {name_a}", "value": wins_a},
        {"label": f"Victoires {name_b}", "value": wins_b},
        {
            "label": "Dernière rencontre",
            "value": (
                to_date(matches["jour"].head(1)).iloc[0].strftime("%d/%m/%Y")
                if not matches.empty
                else "Jamais"
            ),
        },
    ]
)

# ── Favori selon l'Elo ──────────────────────────────────────────────────────
section("Qui est favori ?", level=3)
elo_a, elo_b = player_elo(_DATA_KEY, player_a), player_elo(_DATA_KEY, player_b)
if elo_a.empty or elo_b.empty:
    st.info("Elo indisponible pour l'un des deux joueurs.")
else:
    rows = []
    for label, col in SURFACES.items():
        ra, rb = float(elo_a.iloc[0][col]), float(elo_b.iloc[0][col])
        proba_a = 1 / (1 + 10 ** ((rb - ra) / 400))
        rows.append({"Surface": label, name_a: ra, name_b: rb, "proba_a": proba_a})
    elo_table = pd.DataFrame(rows)
    fig = go.Figure(
        [
            go.Bar(name=name_a, x=elo_table["Surface"], y=elo_table[name_a], marker_color=COLOR_A),
            go.Bar(
                name=name_b,
                x=elo_table["Surface"],
                y=elo_table[name_b],
                marker_color=COLOR_B,
                marker_pattern_shape="/",
            ),
        ]
    )
    low = float(elo_table[[name_a, name_b]].min().min())
    high = float(elo_table[[name_a, name_b]].max().max())
    fig.update_layout(barmode="group", hovermode="x")
    fig.update_yaxes(title_text="Elo", range=[max(low - 150, 1000), high + 40])
    st.plotly_chart(apply_tennis_theme(fig, height=320), width="stretch")
    phrases = []
    for r in rows:
        fav, p = (name_a, r["proba_a"]) if r["proba_a"] >= 0.5 else (name_b, 1 - r["proba_a"])
        phrases.append(f"**{r['Surface'].lower()}** : {fav} ({p:.0%})")
    st.markdown("Favori selon l'écart Elo — " + " · ".join(phrases) + ".")
    st.page_link(
        "views/predictions.py",
        label="Prédiction détaillée (modèle complet)",
        icon=":material/query_stats:",
    )

if matches.empty:
    st.info(f"{name_a} et {name_b} ne se sont jamais affrontés depuis 2010.")
    st.stop()

# ── Bilan par surface ───────────────────────────────────────────────────────
section("Bilan par surface", level=3)
matches["surface_fr"] = matches["surface"].map(surface_fr)
by_surface = (
    matches.assign(a=matches["winner_id"] == player_a)
    .groupby("surface_fr")["a"]
    .agg(wins_a="sum", total="count")
    .reset_index()
)
by_surface["wins_b"] = by_surface["total"] - by_surface["wins_a"]
fig = go.Figure(
    [
        go.Bar(
            name=name_a,
            y=by_surface["surface_fr"],
            x=by_surface["wins_a"],
            orientation="h",
            marker_color=COLOR_A,
            text=by_surface["wins_a"],
            textposition="inside",
        ),
        go.Bar(
            name=name_b,
            y=by_surface["surface_fr"],
            x=by_surface["wins_b"],
            orientation="h",
            marker_color=COLOR_B,
            text=by_surface["wins_b"],
            textposition="inside",
        ),
    ]
)
fig.update_layout(barmode="stack", hovermode="y")
fig.update_xaxes(title_text="Victoires")
st.plotly_chart(apply_tennis_theme(fig, height=80 + 60 * len(by_surface)), width="stretch")

# ── Service lors de leurs matchs ────────────────────────────────────────────
with_stats = matches.dropna(subset=["w_svpt", "l_svpt"])
if not with_stats.empty:
    section(
        "Au service lors de leurs confrontations",
        level=3,
        caption=f"Moyennes sur {len(with_stats)} matchs avec statistiques détaillées.",
    )
    profile_a, profile_b = _serve_profile(with_stats, player_a), _serve_profile(
        with_stats, player_b
    )
    df_styled(
        pd.DataFrame(
            {
                "Indicateur": list(profile_a),
                name_a: [round(v * 100, 1) for v in profile_a.values()],
                name_b: [round(v * 100, 1) for v in profile_b.values()],
            }
        ),
        column_config={
            name_a: st.column_config.NumberColumn(format="%.1f %%"),
            name_b: st.column_config.NumberColumn(format="%.1f %%"),
        },
    )

# ── Historique ──────────────────────────────────────────────────────────────
section("Toutes leurs confrontations", level=3)
df_styled(
    pd.DataFrame(
        {
            "Date": to_date(matches["jour"]),
            "Tournoi": matches["tourney_name"],
            "Surface": matches["surface_fr"],
            "Tour": matches["round"].map(round_fr),
            "Vainqueur": matches["winner_name"],
            "Score": matches["score"],
        }
    ),
    height=min(38 * (len(matches) + 1), 480),
)
