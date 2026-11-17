"""Tendances : évolution du jeu depuis 2010 (service, durée, ATP vs WTA, séries)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components._bootstrap import data_key, init_app
from components.plotly_theme import (
    CIRCUIT_COLORS,
    LOSS_COLOR,
    SURFACE_COLORS,
    WIN_COLOR,
    apply_tennis_theme,
)
from components.queries import PLAYED_ON_SQL, ROUND_ORDER_SQL
from components.widgets import (
    circuit_filter_sql,
    circuit_selectbox,
    df_styled,
    page_header,
    section,
    surface_fr,
    to_date,
)

_ROOT, _CONNECTION = init_app(__file__)
_DATA_KEY = data_key(_ROOT)

STATS_NOTE = (
    "Les statistiques détaillées (aces, durée, balles de break) proviennent de "
    "l'archive Sackmann et s'arrêtent au 25/05/2026 ; les résultats plus récents n'en "
    "ont pas."
)


@st.cache_data(ttl=3600, show_spinner=False)
def _serve_by_year(cache_key: str, circuit: str) -> pd.DataFrame:
    cf = circuit_filter_sql(circuit)
    return _CONNECTION.execute(f"""
        SELECT CAST(tourney_date // 10000 AS INT) AS annee,
               ROUND(AVG(w_ace + l_ace), 2) AS aces, ROUND(AVG(w_df + l_df), 2) AS df,
               COUNT(*) AS matchs
        FROM v_matches WHERE w_ace IS NOT NULL AND l_ace IS NOT NULL {cf}
        GROUP BY annee HAVING COUNT(*) >= 100 ORDER BY annee
        """).df()


@st.cache_data(ttl=3600, show_spinner=False)
def _duration_by_year(cache_key: str, circuit: str) -> pd.DataFrame:
    cf = circuit_filter_sql(circuit)
    return _CONNECTION.execute(f"""
        SELECT CAST(tourney_date // 10000 AS INT) AS annee,
               ROUND(AVG(minutes)) AS moyenne, ROUND(MEDIAN(minutes)) AS mediane
        FROM v_matches WHERE minutes > 0 AND minutes < 400 {cf}
        GROUP BY annee HAVING COUNT(*) >= 100 ORDER BY annee
        """).df()


@st.cache_data(ttl=3600, show_spinner=False)
def _duration_by_surface(cache_key: str, circuit: str) -> pd.DataFrame:
    cf = circuit_filter_sql(circuit)
    return _CONNECTION.execute(f"""
        SELECT surface, minutes FROM v_matches
        WHERE minutes > 0 AND minutes < 400 AND surface IN ('Hard', 'Clay', 'Grass') {cf}
        """).df()


@st.cache_data(ttl=3600, show_spinner=False)
def _atp_vs_wta(cache_key: str) -> pd.DataFrame:
    return _CONNECTION.execute("""
        SELECT circuit, CAST(tourney_date // 10000 AS INT) AS annee,
               ROUND(AVG(w_ace + l_ace), 2) AS aces,
               ROUND(AVG(minutes) FILTER (WHERE minutes > 0 AND minutes < 400)) AS duree,
               ROUND(AVG(w_bpFaced + l_bpFaced), 2) AS balles_break
        FROM v_matches WHERE w_ace IS NOT NULL
        GROUP BY circuit, annee HAVING COUNT(*) >= 100 ORDER BY annee, circuit
        """).df()


@st.cache_data(ttl=3600, show_spinner=False)
def _longest_streaks(cache_key: str, circuit: str, top_n: int = 15) -> pd.DataFrame:
    """Plus longues séries de victoires consécutives (méthode « gaps and islands »)."""
    cf = circuit_filter_sql(circuit)
    return _CONNECTION.execute(
        f"""
        WITH m AS (
            SELECT winner_id AS pid, winner_name AS nom, 1 AS v,
                   {PLAYED_ON_SQL} AS jour, tourney_date, tourney_id, {ROUND_ORDER_SQL} AS tour
            FROM v_matches WHERE 1=1 {cf}
            UNION ALL
            SELECT loser_id, loser_name, 0, {PLAYED_ON_SQL}, tourney_date, tourney_id,
                   {ROUND_ORDER_SQL}
            FROM v_matches WHERE 1=1 {cf}
        ),
        o AS (
            SELECT *, ROW_NUMBER() OVER w - SUM(v) OVER (w ROWS UNBOUNDED PRECEDING) AS grp
            FROM m
            WINDOW w AS (PARTITION BY pid ORDER BY tourney_date, tourney_id, tour, jour)
        )
        SELECT ANY_VALUE(nom) AS joueur, COUNT(*) AS serie,
               MIN(jour) AS debut, MAX(jour) AS fin
        FROM o WHERE v = 1
        GROUP BY pid, grp
        ORDER BY serie DESC, fin DESC
        LIMIT ?
        """,
        [top_n],
    ).df()


def _line(
    fig: go.Figure, x: pd.Series, y: pd.Series, name: str, color: str, dash: str = "solid"
) -> None:
    fig.add_trace(
        go.Scatter(
            x=x, y=y, name=name, mode="lines+markers", line=dict(color=color, dash=dash, width=2.4)
        )
    )


circuit = circuit_selectbox()
page_header("Tendances", subtitle="Comment le tennis a évolué depuis 2010.")

tab_serve, tab_duration, tab_circuits, tab_streaks = st.tabs(
    ["Service", "Durée des matchs", "ATP vs WTA", "Séries de victoires"]
)

with tab_serve:
    serve = _serve_by_year(_DATA_KEY, circuit)
    if serve.empty:
        st.info("Pas de statistiques de service pour ce circuit.")
    else:
        fig = go.Figure()
        _line(fig, serve["annee"], serve["aces"], "Aces par match", WIN_COLOR)
        _line(fig, serve["annee"], serve["df"], "Doubles fautes par match", LOSS_COLOR, "dash")
        fig.update_yaxes(title_text="Par match (deux joueurs)")
        st.plotly_chart(apply_tennis_theme(fig, height=360), width="stretch")
        first, last = serve.iloc[0], serve.iloc[-1]
        st.markdown(
            f"De {first['annee']} à {last['annee']}, le nombre d'aces par match passe de "
            f"**{first['aces']:.1f}** à **{last['aces']:.1f}**."
        )
    st.caption(STATS_NOTE)

with tab_duration:
    durations = _duration_by_year(_DATA_KEY, circuit)
    if durations.empty:
        st.info("Pas de durées disponibles.")
    else:
        fig = go.Figure()
        _line(fig, durations["annee"], durations["moyenne"], "Moyenne", WIN_COLOR)
        _line(fig, durations["annee"], durations["mediane"], "Médiane", LOSS_COLOR, "dash")
        fig.update_yaxes(title_text="Minutes")
        st.plotly_chart(apply_tennis_theme(fig, height=340), width="stretch")

        section("Par surface", level=3)
        by_surface = _duration_by_surface(_DATA_KEY, circuit)
        fig = go.Figure()
        for surface in ("Hard", "Clay", "Grass"):
            values = by_surface.loc[by_surface["surface"] == surface, "minutes"]
            fig.add_trace(
                go.Box(
                    y=values,
                    name=surface_fr(surface),
                    marker_color=SURFACE_COLORS[surface],
                    boxmean=True,
                    boxpoints=False,
                )
            )
        fig.update_yaxes(title_text="Minutes")
        fig.update_layout(showlegend=False, hovermode="closest")
        st.plotly_chart(apply_tennis_theme(fig, height=340), width="stretch")
        medians = by_surface.groupby("surface")["minutes"].median()
        st.caption(
            "Durée médiane : "
            + " · ".join(f"{surface_fr(s)} {int(m)} min" for s, m in medians.sort_values().items())
            + "."
        )
    st.caption(STATS_NOTE)

with tab_circuits:
    compare = _atp_vs_wta(_DATA_KEY)
    metrics = {
        "Aces par match": "aces",
        "Durée moyenne (min)": "duree",
        "Balles de break par match": "balles_break",
    }
    choice = st.segmented_control(
        "Indicateur", list(metrics), default="Aces par match", required=True, key="tendances_metric"
    )
    col = metrics[choice]
    fig = go.Figure()
    for circ, dash in (("ATP", "solid"), ("WTA", "dash")):
        part = compare.loc[compare["circuit"] == circ]
        _line(fig, part["annee"], part[col], circ, CIRCUIT_COLORS[circ], dash)
    fig.update_yaxes(title_text=choice)
    st.plotly_chart(apply_tennis_theme(fig, height=360), width="stretch")
    st.caption(STATS_NOTE)

with tab_streaks:
    streaks = _longest_streaks(_DATA_KEY, circuit)
    if streaks.empty:
        st.info("Aucune série.")
    else:
        df_styled(
            pd.DataFrame(
                {
                    "Joueur": streaks["joueur"],
                    "Victoires consécutives": streaks["serie"],
                    "Du": to_date(streaks["debut"]),
                    "Au": to_date(streaks["fin"]),
                }
            )
        )
        st.caption("Toutes surfaces et tous tournois confondus, depuis 2010.")
