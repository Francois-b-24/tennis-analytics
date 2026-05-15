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
        /* ── Anti-débordement horizontal global ─────────────────────────── */
        html, body, [data-testid="stAppViewContainer"], .main, .stApp {
            overflow-x: hidden !important;
            max-width: 100vw !important;
        }

        /* ── Charts Plotly toujours 100% largeur ───────────────────────── */
        .js-plotly-plot, .plotly {
            max-width: 100% !important;
        }

        /* ── Encart info-band : largeur sûre ────────────────────────────── */
        .info-band {
            max-width: 100% !important;
            box-sizing: border-box !important;
            word-wrap: break-word !important;
            overflow-wrap: break-word !important;
        }

        /* ── Tableaux markdown : scroll horizontal au besoin ────────────── */
        .main table {
            display: block !important;
            overflow-x: auto !important;
            max-width: 100% !important;
            -webkit-overflow-scrolling: touch !important;
        }

        /* ── Blocs de code : pas de débordement ─────────────────────────── */
        .main pre, .main code {
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
            overflow-wrap: break-word !important;
            max-width: 100% !important;
        }

        /* ── Mobile (< 768px) ───────────────────────────────────────────── */
        @media (max-width: 768px) {

            /* Empile toutes les colonnes en vertical */
            [data-testid="stHorizontalBlock"] {
                flex-direction: column !important;
                gap: 0.5rem !important;
            }
            [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
                width: 100% !important;
                flex: 1 1 100% !important;
                min-width: 0 !important;
                max-width: 100% !important;
            }

            /* Padding réduit + largeur 100 % */
            .main .block-container,
            section.main > div.block-container,
            [data-testid="stAppViewContainer"] .main .block-container,
            [data-testid="stMain"] .block-container {
                padding-left: 0.75rem !important;
                padding-right: 0.75rem !important;
                padding-top: 1rem !important;
                max-width: 100% !important;
                width: 100% !important;
            }

            /* Conteneurs internes : strictement contenus */
            [data-testid="stHorizontalBlock"],
            [data-testid="stVerticalBlock"] {
                width: 100% !important;
                max-width: 100% !important;
                box-sizing: border-box !important;
            }

            /* Sidebar masquée par défaut */
            [data-testid="stSidebar"] {
                min-width: 0 !important;
            }

            /* Métriques : texte plus petit pour éviter le wrap moche */
            [data-testid="stMetricValue"] {
                font-size: 1.05rem !important;
                word-break: break-word !important;
            }
            [data-testid="stMetricLabel"] {
                font-size: 0.78rem !important;
            }
            [data-testid="stMetricDelta"] {
                font-size: 0.72rem !important;
            }

            /* Dataframes scrollables */
            [data-testid="stDataFrame"] {
                overflow-x: auto !important;
                max-width: 100% !important;
            }

            /* Titres réduits */
            h1 { font-size: 1.5rem !important; line-height: 1.2 !important; }
            h2 { font-size: 1.25rem !important; }
            h3 { font-size: 1.05rem !important; }
            h4 { font-size: 0.95rem !important; }

            /* Encart info-band en mobile : padding plus fin */
            .info-band {
                padding: 10px 12px !important;
                font-size: 0.88rem !important;
            }

            /* Tableaux markdown : police plus petite sur mobile */
            .main table {
                font-size: 0.82rem !important;
            }
            .main th, .main td {
                padding: 6px 8px !important;
            }
        }

        /* ── Tooltip Elo : reste dans le viewport ───────────────────────── */
        @media (max-width: 500px) {
            .elo-tooltip .elo-tip {
                width: 80vw !important;
                max-width: 280px !important;
                left: 50% !important;
                transform: translateX(-50%) !important;
                font-size: 0.78rem !important;
            }
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
