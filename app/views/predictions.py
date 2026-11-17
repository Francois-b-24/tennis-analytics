"""Prédictions : probabilité de victoire entre deux joueurs sur une surface."""

from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components._bootstrap import data_key, init_app, processed_dir
from components.plotly_theme import PALETTE, apply_tennis_theme
from components.queries import player_options, top_player_ids
from components.widgets import (
    circuit_selectbox,
    df_styled,
    disambiguate_player_labels,
    load_model_bundle,
    page_header,
    player_selectbox,
    section,
)
from tennis_analytics.modeling.inference import head_to_head, matchup_features, player_context

_ROOT, _CONNECTION = init_app(__file__)
_DATA_KEY = data_key(_ROOT)

SURFACES = {"Dur": "hard", "Terre battue": "clay", "Gazon": "grass"}
COLOR_A, COLOR_B = PALETTE[0], PALETTE[1]


@st.cache_data(ttl=3600, show_spinner=False)
def _contexts(cache_key: str, player_a: int, player_b: int, surface: str) -> tuple:
    return (
        player_context(_CONNECTION, player_a, surface),
        player_context(_CONNECTION, player_b, surface),
        head_to_head(_CONNECTION, player_a, player_b),
    )


page_header(
    "Prédictions",
    subtitle=(
        "Probabilité de victoire estimée par un modèle entraîné sur tous les matchs depuis "
        "2010 (Elo, confrontations, forme, réussite sur la surface)."
    ),
)
circuit = circuit_selectbox()

bundle = load_model_bundle(
    str(processed_dir(_ROOT) / "models" / "logreg_calibrated.joblib"), _DATA_KEY
)
if bundle is None:
    st.error("Le modèle de prédiction est momentanément indisponible.")
    st.stop()

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
        key=f"pred_a_{circuit}",
        default_player_id=defaults[0] if defaults else None,
    )
with col_b:
    player_b = player_selectbox(
        "Joueur B",
        players,
        key=f"pred_b_{circuit}",
        default_index=1,
        default_player_id=defaults[1] if len(defaults) > 1 else None,
    )
surface_label = st.segmented_control(
    "Surface", list(SURFACES), default="Dur", required=True, key="pred_surface"
)
if player_a is None or player_b is None or player_a == player_b:
    st.warning("Choisissez deux joueurs différents.")
    st.stop()

name_of = dict(zip(players["player_id"], players["full_name"], strict=False))
name_a, name_b = name_of[player_a], name_of[player_b]
ctx_a, ctx_b, h2h = _contexts(_DATA_KEY, player_a, player_b, SURFACES[surface_label])
features = matchup_features(ctx_a, ctx_b, h2h)
X = pd.DataFrame([features])[bundle["features"]]
prob_a = float(bundle["model"].predict_proba(X)[:, 1][0])
prob_b = 1 - prob_a
favorite, fav_prob = (name_a, prob_a) if prob_a >= 0.5 else (name_b, prob_b)

section(f"Sur {surface_label.lower()}", level=3)
st.markdown(
    f"**{favorite}** est favori(te) avec **{fav_prob:.0%}** de chances de victoire.".replace(
        "%", " %"
    )
)
left, right = st.columns(2)
left.markdown(f"**{name_a}** · {prob_a:.0%}".replace("%", " %"))
right.markdown(
    f"<div style='text-align:right'><b>{html.escape(name_b)}</b> · {prob_b:.0%}</div>".replace(
        "%", " %"
    ),
    unsafe_allow_html=True,
)
fig = go.Figure(
    [
        go.Bar(
            x=[prob_a * 100],
            y=[""],
            orientation="h",
            name=name_a,
            marker_color=COLOR_A,
            hovertemplate=f"{name_a} : %{{x:.1f}} %<extra></extra>",
        ),
        go.Bar(
            x=[prob_b * 100],
            y=[""],
            orientation="h",
            name=name_b,
            marker_color=COLOR_B,
            hovertemplate=f"{name_b} : %{{x:.1f}} %<extra></extra>",
        ),
    ]
)
fig.update_layout(barmode="stack", showlegend=False, hovermode="closest")
fig.update_xaxes(range=[0, 100], visible=False)
fig.update_yaxes(visible=False)
st.plotly_chart(apply_tennis_theme(fig, height=70), width="stretch")

section("Ce qui pèse dans la balance", level=3)


def _fmt_rank(value: float | None) -> str:
    return f"n°{int(value)}" if value else "—"


wins_a, wins_b = h2h
df_styled(
    pd.DataFrame(
        {
            "Indicateur": [
                f"Elo {surface_label.lower()}",
                "Elo global",
                "Classement officiel",
                f"Victoires sur {surface_label.lower()}",
                "Forme (10 derniers matchs)",
                "Confrontations directes",
                "Âge",
            ],
            name_a: [
                f"{ctx_a.elo_surface:.0f}",
                f"{ctx_a.elo_global:.0f}",
                _fmt_rank(ctx_a.rank),
                f"{ctx_a.surface_winrate:.0%} ({ctx_a.surface_matches} matchs)",
                f"{ctx_a.recent_form:.0%}",
                str(wins_a),
                f"{ctx_a.age:.0f} ans",
            ],
            name_b: [
                f"{ctx_b.elo_surface:.0f}",
                f"{ctx_b.elo_global:.0f}",
                _fmt_rank(ctx_b.rank),
                f"{ctx_b.surface_winrate:.0%} ({ctx_b.surface_matches} matchs)",
                f"{ctx_b.recent_form:.0%}",
                str(wins_b),
                f"{ctx_b.age:.0f} ans",
            ],
        }
    )
)
st.caption(
    "Estimation statistique fondée sur les résultats passés : elle ne constitue pas un "
    "conseil de pari."
)
st.page_link(
    "views/methodologie.py",
    label="Fiabilité du modèle (calibration, poids des indicateurs)",
    icon=":material/menu_book:",
)
