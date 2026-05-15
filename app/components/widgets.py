"""Widgets Streamlit réutilisables (sélecteurs, formatage FR)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import streamlit as st


def format_date_dd_mm_yyyy(value: int | float | None) -> str:
    """Formate un entier `YYYYMMDD` en `DD/MM/YYYY`."""
    if value is None:
        return ""
    try:
        text = f"{int(value):08d}"
        return datetime.strptime(text, "%Y%m%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(value)


def format_percent(value: float | None, digits: int = 1) -> str:
    """Formate un ratio [0,1] en pourcentage avec virgule décimale."""
    if value is None:
        return ""
    pct = value * 100.0
    return f"{pct:.{digits}f}".replace(".", ",") + " %"


def load_player_options(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Retourne la liste des joueurs disponibles (id + nom)."""
    try:
        frame = connection.execute(
            """
            SELECT player_id, full_name
            FROM v_player_names
            WHERE TRIM(full_name) <> ''
            ORDER BY full_name;
            """
        ).df()
        if not frame.empty:
            return frame.drop_duplicates(subset=["full_name"])
    except duckdb.Error:
        pass
    frame = connection.execute(
        """
        SELECT DISTINCT winner_id AS player_id, winner_name AS full_name
        FROM v_matches
        ORDER BY full_name;
        """
    ).df()
    return frame.drop_duplicates(subset=["full_name"])


def player_selectbox(label: str, options: pd.DataFrame, key: str) -> int | None:
    """Sélecteur Streamlit basé sur une liste de joueurs."""
    if options.empty:
        st.warning("Aucun joueur disponible : lancez l'ingestion pour construire les parquets.")
        return None
    mapping = dict(zip(options["full_name"], options["player_id"], strict=False))
    choice = st.selectbox(label, list(mapping.keys()), key=key)
    return int(mapping[choice])


def query_dataframe(
    connection: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None
) -> pd.DataFrame:
    """Exécute une requête SQL et retourne un DataFrame pandas."""
    if params:
        return connection.execute(sql, params).df()
    return connection.execute(sql).df()


def safe_scalar(
    connection: duckdb.DuckDBPyConnection,
    sql: str,
    params: list[Any] | None = None,
    default: Any = None,
) -> Any:
    """Exécute une requête scalaire et retourne `default` en cas d'erreur."""
    try:
        row = connection.execute(sql, params or []).fetchone()
        return row[0] if row else default
    except duckdb.Error:
        return default


def format_elo(value: float | None) -> str:
    """Formate un rating Elo en entier arrondi (ex : 1847)."""
    if value is None:
        return "—"
    return f"{int(round(value))}"


def circuit_filter_sql(circuit: str) -> str:
    """Génère une clause SQL WHERE pour filtrer par circuit (ATP/WTA).

    Ne jamais interpoler de valeurs issues directement de l'utilisateur sans
    passer par cette fonction — seules 'ATP' et 'WTA' sont acceptées.
    """
    if circuit in ("ATP", "WTA"):
        return f"AND circuit = '{circuit}'"
    return ""


def inject_global_css() -> None:
    """Injecte le CSS global responsive tennis (à appeler une fois par page)."""
    st.markdown(
        """
        <style>
        /* ── Colonnes Streamlit empilées sur mobile ─────────────────────── */
        @media (max-width: 768px) {

            /* Empile toutes les colonnes en vertical */
            [data-testid="stHorizontalBlock"] {
                flex-direction: column !important;
            }
            [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
                width: 100% !important;
                flex: 1 1 100% !important;
                min-width: 0 !important;
            }

            /* Réduit le padding latéral de la page */
            .main .block-container {
                padding-left: 1rem !important;
                padding-right: 1rem !important;
            }

            /* Sidebar masquée par défaut sur mobile (repliée) */
            [data-testid="stSidebar"] {
                min-width: 0 !important;
            }

            /* Métriques : texte légèrement réduit */
            [data-testid="stMetricValue"] {
                font-size: 1.1rem !important;
            }
            [data-testid="stMetricLabel"] {
                font-size: 0.78rem !important;
            }

            /* Dataframes scrollables horizontalement */
            [data-testid="stDataFrame"] {
                overflow-x: auto !important;
            }

            /* Titres réduits */
            h1 { font-size: 1.6rem !important; }
            h2 { font-size: 1.3rem !important; }
            h3 { font-size: 1.1rem !important; }

            /* Cards navigation home */
            [data-testid="stVerticalBlock"] > div[data-testid="element-container"] > div {
                margin-bottom: 0.5rem;
            }
        }

        /* ── Tooltip Elo : reste dans le viewport sur mobile ───────────── */
        @media (max-width: 500px) {
            .elo-tooltip .elo-tip {
                width: 85vw !important;
                left: 0 !important;
                transform: none !important;
            }
        }

        /* ── Charts Plotly toujours 100% largeur ───────────────────────── */
        .js-plotly-plot, .plotly {
            max-width: 100% !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_info(text: str, icon: str = "🎾") -> None:
    """Affiche un encart descriptif soft au style tennis (vert discret)."""
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #f4f9f5 0%, #eaf3ec 100%);
            border-left: 4px solid #3A7D44;
            border-radius: 0 8px 8px 0;
            padding: 12px 16px;
            margin-bottom: 16px;
            color: #3a3a3a;
            font-size: 0.92rem;
            line-height: 1.6;
        ">
        {icon}&nbsp; {text}
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def load_model_bundle(model_path: str) -> dict | None:
    """Charge le bundle joblib {'model': ..., 'features': [...]}."""
    import joblib

    p = Path(model_path)
    if not p.exists():
        return None
    return joblib.load(str(p))
