"""Requêtes SQL partagées entre les pages Streamlit.

Centralise les patterns dupliqués (listes joueurs, tournois, dernier match) pour
éviter la dérive entre pages. Chaque fonction est cachée par `(_conn_key, ...)`
où `_conn_key` est le `data_key()` issu de `init_app()` : racine du projet **et**
empreinte des parquets. Dès que l'ingestion quotidienne réécrit les données,
la clé change et les résultats cachés sont recalculés — sans redémarrage.

Note : ce module est dans `app/components/` plutôt qu'`app/db/` pour éviter
le conflit de namespace avec `src/db/duckdb_session` (déjà importé sous `db.*`).
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from components._bootstrap import connection_for_key


def _shared_connection(conn_key: str) -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB partagée (réutilise le cache de :func:`init_app`)."""
    return connection_for_key(conn_key)


@st.cache_data(ttl=3600, show_spinner=False)
def player_options(_conn_key: str, circuit: str) -> pd.DataFrame:
    """Retourne les joueurs d'un circuit avec leur code pays IOC.

    Fusion de l'ancien `_player_options` (1_Joueurs) et `_player_options_circuit`
    (2_Face_a_Face). `circuit` peut valoir 'ATP', 'WTA' ou 'Tous'.

    **Seuls les joueurs ayant réellement disputé un match sont proposés.** Le
    fichier joueurs de Sackmann contient ~122 800 entrées (juniors, qualifiés,
    homonymes) contre ~3 500 ayant joué depuis 2010 : sans ce filtre, 97 % des
    noms de la liste n'ont ni statistiques ni historique Elo, et la page affiche
    « Historique Elo indisponible » dès l'ouverture.

    Args:
        _conn_key: Clé `data_key()` (racine + empreinte des données).
        circuit: 'ATP', 'WTA' ou 'Tous'.

    Returns:
        DataFrame avec colonnes `player_id`, `full_name`, `ioc`, trié par nom.
    """
    conn = _shared_connection(_conn_key)
    try:
        cols = conn.execute("DESCRIBE v_players").df()["column_name"].tolist()
    except duckdb.Error:
        return pd.DataFrame(columns=["player_id", "full_name", "ioc"])
    pays_col = "ioc" if "ioc" in cols else ("country_code" if "country_code" in cols else "NULL")
    where_circuit = "" if circuit == "Tous" else "WHERE p.circuit = ?"
    # Le filtre par circuit s'applique aussi aux matchs : un joueur « BOTH » ne
    # doit pas remonter dans la liste ATP s'il n'a joué que sur le circuit WTA.
    where_matchs = "" if circuit == "Tous" else "WHERE circuit = ?"
    sql = f"""
        WITH joueurs_actifs AS (
            SELECT DISTINCT player_id FROM (
                SELECT winner_id AS player_id, circuit FROM v_matches
                UNION ALL
                SELECT loser_id AS player_id, circuit FROM v_matches
            ) {where_matchs}
        )
        SELECT p.player_id,
               TRIM(CONCAT(COALESCE(ANY_VALUE(p.name_first), ''),
                           ' ',
                           COALESCE(ANY_VALUE(p.name_last), ''))) AS full_name,
               ANY_VALUE({pays_col}) AS ioc
        FROM v_players p
        JOIN joueurs_actifs a ON p.player_id = a.player_id
        {where_circuit}
        GROUP BY p.player_id
        HAVING TRIM(CONCAT(COALESCE(ANY_VALUE(p.name_first), ''),
                           ' ',
                           COALESCE(ANY_VALUE(p.name_last), ''))) <> ''
        ORDER BY full_name
    """
    try:
        # Deux placeholders quand un circuit est choisi : filtre matchs + filtre joueurs.
        params = [] if circuit == "Tous" else [circuit, circuit]
        return conn.execute(sql, params).df()
    except duckdb.Error:
        return pd.DataFrame(columns=["player_id", "full_name", "ioc"])


@st.cache_data(ttl=3600, show_spinner=False)
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


@st.cache_data(ttl=3600, show_spinner=False)
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
