"""Requêtes SQL partagées entre les pages Streamlit.

Centralise les patterns dupliqués (listes joueurs, tournois, dernier match) pour
éviter la dérive entre pages. Chaque fonction est cachée par `(_conn_key, ...)`
où `_conn_key` est le `str(_ROOT)` issu de `init_app()` — c'est une clé stable
réutilisable par `@st.cache_data`.

Note : ce module est dans `app/components/` plutôt qu'`app/db/` pour éviter
le conflit de namespace avec `src/db/duckdb_session` (déjà importé sous `db.*`).
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from components._bootstrap import _cached_connection


def _shared_connection(root_str: str) -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB partagée (réutilise le cache de :func:`init_app`)."""
    return _cached_connection(root_str)


@st.cache_data(show_spinner=False)
def player_options(_conn_key: str, circuit: str) -> pd.DataFrame:
    """Retourne les joueurs d'un circuit avec leur code pays IOC.

    Fusion de l'ancien `_player_options` (1_Joueurs) et `_player_options_circuit`
    (2_Face_a_Face). `circuit` peut valoir 'ATP', 'WTA' ou 'Tous'.

    Args:
        _conn_key: Racine projet (str) — clé de cache stable.
        circuit: 'ATP', 'WTA' ou 'Tous'.

    Returns:
        DataFrame avec colonnes `player_id`, `full_name`, `ioc`.
    """
    conn = _shared_connection(_conn_key)
    try:
        cols = conn.execute("DESCRIBE v_players").df()["column_name"].tolist()
    except duckdb.Error:
        return pd.DataFrame(columns=["player_id", "full_name", "ioc"])
    pays_col = "ioc" if "ioc" in cols else ("country_code" if "country_code" in cols else "NULL")
    where_circuit = "" if circuit == "Tous" else "WHERE circuit = ?"
    sql = f"""
        SELECT player_id,
               TRIM(CONCAT(COALESCE(ANY_VALUE(name_first), ''),
                           ' ',
                           COALESCE(ANY_VALUE(name_last), ''))) AS full_name,
               ANY_VALUE({pays_col}) AS ioc
        FROM v_players
        {where_circuit}
        GROUP BY player_id
        HAVING TRIM(CONCAT(COALESCE(ANY_VALUE(name_first), ''),
                           ' ',
                           COALESCE(ANY_VALUE(name_last), ''))) <> ''
    """
    try:
        params = [] if circuit == "Tous" else [circuit]
        return conn.execute(sql, params).df()
    except duckdb.Error:
        return pd.DataFrame(columns=["player_id", "full_name", "ioc"])


@st.cache_data(show_spinner=False)
def tournaments_for_circuit(_conn_key: str, circuit: str) -> list[str]:
    """Retourne la liste triée des tournois distincts pour un circuit donné."""
    conn = _shared_connection(_conn_key)
    try:
        if circuit == "Tous":
            df = conn.execute(
                "SELECT DISTINCT tourney_name FROM v_matches ORDER BY tourney_name"
            ).df()
        else:
            df = conn.execute(
                "SELECT DISTINCT tourney_name FROM v_matches WHERE circuit = ? ORDER BY tourney_name",
                [circuit],
            ).df()
        return df["tourney_name"].tolist()
    except duckdb.Error:
        return []


@st.cache_data(show_spinner=False)
def latest_match_per_circuit(_conn_key: str, circuit: str) -> dict:
    """Retourne le tournoi et la date du dernier match d'un circuit."""
    conn = _shared_connection(_conn_key)
    try:
        row = conn.execute(
            """
            SELECT tourney_name, tourney_date
            FROM v_matches
            WHERE circuit = ?
            ORDER BY tourney_date DESC
            LIMIT 1
            """,
            [circuit],
        ).fetchone()
        if not row:
            return {"tourney_name": "—", "tourney_date": None}
        return {"tourney_name": row[0], "tourney_date": row[1]}
    except duckdb.Error:
        return {"tourney_name": "—", "tourney_date": None}
