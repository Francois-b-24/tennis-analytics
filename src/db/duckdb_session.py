"""Connexion DuckDB et enregistrement des vues analytiques sur parquet."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
from loguru import logger


def get_project_root() -> Path:
    """Retourne la racine du projet depuis `ROOT_PATH` ou la découverte locale."""
    env = os.getenv("ROOT_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _processed_dir(root: Path) -> Path:
    return root / "data" / "processed"


def _register_parquet_view(
    connection: duckdb.DuckDBPyConnection,
    view_name: str,
    parquet_path: Path,
) -> None:
    """Crée une vue `view_name` si le parquet existe."""
    if not parquet_path.exists():
        logger.warning("Parquet absent, vue `{}` ignorée : {}", view_name, parquet_path)
        return
    sql_path = parquet_path.resolve().as_posix().replace("'", "''")
    ddl = f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{sql_path}');"
    connection.execute(ddl)


def create_connection(project_root: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Ouvre une connexion DuckDB (fichier optionnel) et enregistre les vues parquet.

    Args:
        project_root: Racine du dépôt ; si None, utilise `ROOT_PATH` ou inférence locale.

    Returns:
        Connexion prête à l'emploi.
    """
    root = project_root or get_project_root()
    db_path = os.getenv("DUCKDB_PATH")
    if db_path:
        connection = duckdb.connect(Path(db_path).expanduser().resolve().as_posix())
    else:
        connection = duckdb.connect(database=":memory:")

    processed = _processed_dir(root)
    _register_parquet_view(connection, "v_matches", processed / "matches.parquet")
    _register_parquet_view(connection, "v_rankings", processed / "rankings.parquet")
    _register_parquet_view(connection, "v_elo_latest", processed / "elo_latest.parquet")
    _register_parquet_view(connection, "v_elo_history", processed / "elo_history.parquet")
    _register_parquet_view(
        connection, "v_match_elo_context", processed / "match_elo_context.parquet"
    )

    players_path = processed / "players.parquet"
    if players_path.exists():
        # On enregistre le parquet brut sous v_players_raw, puis on construit
        # v_players qui expose les joueurs « BOTH » comme appartenant à la fois
        # à ATP et WTA — pour que les requêtes WHERE circuit = 'ATP' / 'WTA'
        # restent compatibles sans modification.
        _register_parquet_view(connection, "v_players_raw", players_path)
        connection.execute(
            """
            CREATE OR REPLACE VIEW v_players AS
            SELECT player_id, name_first, name_last, hand, dob, ioc, height,
                   wikidata_id,
                   CASE WHEN circuit = 'BOTH' THEN 'ATP' ELSE circuit END AS circuit
            FROM v_players_raw
            UNION ALL
            SELECT player_id, name_first, name_last, hand, dob, ioc, height,
                   wikidata_id,
                   'WTA' AS circuit
            FROM v_players_raw
            WHERE circuit = 'BOTH';
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE VIEW v_player_names AS
            SELECT DISTINCT
                player_id,
                TRIM(CONCAT(COALESCE(name_first, ''), ' ', COALESCE(name_last, ''))) AS full_name,
                circuit
            FROM v_players;
            """
        )

    return connection


def get_readonly_connection(project_root: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Alias explicite pour une connexion en lecture seule (vues analytiques)."""
    return create_connection(project_root)
