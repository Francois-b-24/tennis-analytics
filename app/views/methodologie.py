"""Méthodologie : calcul de l'Elo, fiabilité du modèle de prédiction, sources des données."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components._bootstrap import data_key, init_app, load_metadata, processed_dir
from components.plotly_theme import ACCENT, LOSS_COLOR, WIN_COLOR, apply_tennis_theme
from components.queries import elo_ranking
from components.widgets import (
    df_styled,
    format_date_long,
    kpi_row,
    load_model_bundle,
    page_header,
    section,
)
from tennis_analytics.ratings.elo import (
    BASE_ELO,
    BO5_K_MULTIPLIER,
    DECAY_LAMBDA,
    INACTIVITY_DAYS,
)

_ROOT, _CONNECTION = init_app(__file__)
_DATA_KEY = data_key(_ROOT)

FEATURE_LABELS = {
    "diff_elo_surface": "Écart Elo sur la surface",
    "diff_elo_global": "Écart Elo global",
    "diff_rank": "Écart de classement",
    "diff_age": "Écart d'âge",
    "h2h_ratio": "Confrontations directes",
    "surface_winrate_diff": "Écart de réussite sur la surface",
    "recent_form_diff": "Écart de forme récente",
}

page_header(
    "Méthodologie",
    subtitle="Comment sont calculés les classements Elo et les prédictions, et d'où viennent les données.",
)

tab_elo, tab_model, tab_data = st.tabs(["Le rating Elo", "Le modèle de prédiction", "Les données"])

with tab_elo:
    pdf = _ROOT / "references" / "elo_tennis_definition.pdf"
    if pdf.exists():
        st.download_button(
            "Télécharger la définition complète (PDF)",
            data=pdf.read_bytes(),
            file_name="elo_tennis_definition.pdf",
            mime="application/pdf",
            icon=":material/download:",
        )

    section("Le principe", level=3)
    st.markdown(
        "Chaque joueur part de **1 500 points**. Après chaque match, le vainqueur prend des "
        "points au perdant ; **plus la victoire était inattendue, plus l'échange est "
        "important**. Battre le n°1 rapporte beaucoup, battre un joueur bien moins classé "
        "presque rien. Inventé par Arpad Elo pour les échecs, ce système est aussi utilisé "
        "par Tennis Abstract ou FiveThirtyEight."
    )
    st.latex(r"P(A \text{ bat } B) = \frac{1}{1 + 10^{(Elo_B - Elo_A)/400}}")
    st.latex(r"Elo_A' = Elo_A + K \times (\text{résultat} - P(A \text{ bat } B))")
    st.markdown(
        "Un écart de **100 points** donne environ **64 %** de chances au mieux classé ; "
        "un écart de **400 points**, **91 %**."
    )

    section("Les réglages de ce site", level=3)
    df_styled(
        pd.DataFrame(
            {
                "Paramètre": [
                    "Facteur K (vitesse d'ajustement)",
                    "Matchs en 3 sets gagnants",
                    "Elo par surface",
                    "Inactivité",
                ],
                "Valeur": [
                    "40 (moins de 30 matchs), 20 (30 à 99), 10 (100 et plus)",
                    f"K multiplié par {BO5_K_MULTIPLIER:.1f}".replace(".", ","),
                    "Global, dur, terre battue et gazon calculés en parallèle",
                    f"Après {INACTIVITY_DAYS // 30} mois sans jouer, retour progressif vers "
                    f"{BASE_ELO:.0f} ({DECAY_LAMBDA:.0%} par mois)".replace(".", ","),
                ],
            }
        )
    )

    section("Repères", level=3, caption="Valeurs actuelles, joueurs actifs uniquement.")
    rows = []
    for circuit in ("ATP", "WTA"):
        ranking = elo_ranking(_DATA_KEY, circuit, "elo_global", 100)
        for position in (1, 10, 20, 50, 100):
            match = ranking.loc[ranking["rang"] == position]
            if not match.empty:
                rows.append(
                    {"Circuit": circuit, "Rang Elo": position, "Elo": match.iloc[0]["elo_global"]}
                )
    if rows:
        scale = (
            pd.DataFrame(rows)
            .pivot(index="Rang Elo", columns="Circuit", values="Elo")
            .reset_index()
        )
        df_styled(scale)

    with st.expander("Le calcul en Python"):
        st.code(
            """def mettre_a_jour_elo(elo_gagnant: float, elo_perdant: float, k: float = 20.0):
    proba = 1 / (1 + 10 ** ((elo_perdant - elo_gagnant) / 400))  # victoire attendue
    ajustement = k * (1 - proba)
    return elo_gagnant + ajustement, elo_perdant - ajustement""",
            language="python",
        )
    st.caption(
        "Pour aller plus loin : méthodologies Elo de FiveThirtyEight et de Tennis Abstract, "
        "article « Tennis Elo Modelling » du Betfair Hub."
    )

with tab_model:
    bundle = load_model_bundle(
        str(processed_dir(_ROOT) / "models" / "logreg_calibrated.joblib"), _DATA_KEY
    )
    diagnostics = (bundle or {}).get("diagnostics") or {}
    if not diagnostics:
        st.info("Diagnostics du modèle indisponibles.")
    else:
        st.markdown(
            "Une **régression logistique calibrée** estime la probabilité de victoire à partir "
            "des écarts entre les deux joueurs. Elle est évaluée sur des matchs **postérieurs** "
            "à ceux d'entraînement, pour mesurer sa fiabilité sur des matchs qu'elle n'a jamais vus ; "
            "le modèle utilisé par la page Prédictions est ensuite ré-entraîné sur tout l'historique."
        )
        metrics = diagnostics.get("metrics", {})
        kpi_row(
            [
                {
                    "label": "Favori qui gagne",
                    "value": f"{metrics.get('accuracy', 0):.1%}".replace(".", ","),
                    "help": "Part des matchs de test remportés par le joueur donné favori.",
                },
                {
                    "label": "Score de Brier",
                    "value": f"{metrics.get('brier', 0):.3f}".replace(".", ","),
                    "help": "Erreur moyenne des probabilités : 0 = parfait, 0,25 = hasard.",
                },
                {
                    "label": "Matchs de test",
                    "value": f"{int(metrics.get('n_test', 0)):,}".replace(",", " "),
                },
            ]
        )
        col_cal, col_fi = st.columns(2)
        calibration = diagnostics.get("calibration") or {}
        with col_cal:
            section("Les probabilités sont-elles fiables ?", level=3)
            if calibration.get("prob_pred"):
                fig = go.Figure(
                    [
                        go.Scatter(
                            x=[0, 1],
                            y=[0, 1],
                            mode="lines",
                            name="Idéal",
                            line=dict(color="#8A968F", dash="dash"),
                            hoverinfo="skip",
                        ),
                        go.Scatter(
                            x=calibration["prob_pred"],
                            y=calibration["prob_true"],
                            mode="lines+markers",
                            name="Modèle",
                            line=dict(color=ACCENT, width=2.5),
                        ),
                    ]
                )
                fig.update_xaxes(title_text="Probabilité annoncée", tickformat=".0%", range=[0, 1])
                fig.update_yaxes(title_text="Victoires observées", tickformat=".0%", range=[0, 1])
                fig.update_layout(hovermode="closest")
                st.plotly_chart(apply_tennis_theme(fig, height=340), width="stretch")
                st.caption(
                    "Une prédiction à 70 % doit se vérifier environ 7 fois sur 10 : plus la courbe suit la diagonale, mieux c'est."
                )
        importance = diagnostics.get("feature_importance") or {}
        with col_fi:
            section("Poids de chaque indicateur", level=3)
            if importance:
                fi = (
                    pd.DataFrame({"feature": list(importance), "coef": list(importance.values())})
                    .assign(label=lambda d: d["feature"].map(FEATURE_LABELS).fillna(d["feature"]))
                    .sort_values("coef", key=abs)
                )
                fig = go.Figure(
                    go.Bar(
                        x=fi["coef"],
                        y=fi["label"],
                        orientation="h",
                        marker_color=[WIN_COLOR if c >= 0 else LOSS_COLOR for c in fi["coef"]],
                        text=[f"{c:+.2f}" for c in fi["coef"]],
                        textposition="outside",
                    )
                )
                fig.update_layout(hovermode="y")
                st.plotly_chart(apply_tennis_theme(fig, height=340), width="stretch")
                st.caption(
                    "Signe + : l'indicateur favorise le joueur qui a l'avantage ; la longueur indique le poids."
                )

with tab_data:
    metadata = load_metadata(_ROOT)
    st.markdown(
        "- **2010 → 25 mai 2026** : archive de Jeff Sackmann (`tennis_atp`, `tennis_wta`, "
        "licence CC BY-NC-SA 4.0), avec les statistiques détaillées de chaque match.\n"
        "- **Depuis juin 2026** : [tennis-data.co.uk](https://www.tennis-data.co.uk) "
        "(résultats et classements, publiés chaque semaine) et ESPN pour les résultats "
        "du jour, marqués *provisoires* jusqu'à leur confirmation.\n"
        "- **Mise à jour** : toutes les 3 heures ; l'application vérifie les nouveautés "
        "toutes les 15 minutes."
    )
    if metadata:
        last = metadata.get("last_match_date", {})
        sources = metadata.get("matches_by_source", {})
        kpi_row(
            [
                *[
                    {"label": f"Dernier match {c}", "value": format_date_long(d)}
                    for c, d in sorted(last.items())
                ],
                {
                    "label": "Matchs",
                    "value": f"{sum(sources.values()):,}".replace(",", " "),
                    "help": " · ".join(
                        f"{k} : {v:,}".replace(",", " ") for k, v in sources.items()
                    ),
                },
            ]
        )
    st.caption(
        "Périmètre : circuit principal (Grand Chelem, Masters, ATP/WTA 250 à 1000, Masters "
        "de fin d'année, Coupe Davis et BJK Cup jusqu'en mai 2026). Qualifications, "
        "Challenger et ITF exclus."
    )
