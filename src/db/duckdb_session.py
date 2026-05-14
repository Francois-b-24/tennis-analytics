"""Connexion DuckDB et enregistrement des vues analytiques sur parquet."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
from loguru import logger

from ingestion.sackmann_loader import get_project_root


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
    _register_parquet_view(
        connection, "v_match_elo_context", processed / "match_elo_context.parquet"
    )

    players_path = processed / "players.parquet"
    if players_path.exists():
        _register_parquet_view(connection, "v_players", players_path)
        connection.execute(
            """
            CREATE OR REPLACE VIEW v_player_names AS
            SELECT
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
