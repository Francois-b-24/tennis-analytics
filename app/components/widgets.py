"""Widgets Streamlit réutilisables (sélecteurs, formatage FR)."""

from __future__ import annotations

from datetime import datetime
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
