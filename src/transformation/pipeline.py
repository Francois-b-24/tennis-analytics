"""Construction des tables analytiques finales (parquet) à partir des fichiers intermédiaires."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd
from loguru import logger

SURFACE_MAP: Final[dict[str, str]] = {
    "hard": "hard",
    "clay": "clay",
    "grass": "grass",
    "carpet": "hard",
}


def _normalize_surface(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    key = str(value).strip().lower()
    return SURFACE_MAP.get(key, key if key in {"hard", "clay", "grass"} else None)


def _concat_parquet_glob(directory: Path, pattern: str) -> pd.DataFrame:
    paths = sorted(directory.glob(pattern))
    if not paths:
        logger.warning("Aucun fichier parquet pour le motif {} dans {}", pattern, directory)
        return pd.DataFrame()
    frames = [pd.read_parquet(p) for p in paths]
    return pd.concat(frames, ignore_index=True)


def build_processed_tables(project_root: Path) -> None:
    """Lit `data/interim` et écrit les parquets consommés par DuckDB/Streamlit.

    Args:
        project_root: Racine du dépôt.
    """
    interim = project_root / "data" / "interim"
    processed = project_root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)

    matches = _concat_parquet_glob(interim, "*_matches_*.parquet")
    if matches.empty:
        logger.error("Aucun match consolidé : vérifiez l'étape intermédiaire.")
        return

    matches = matches.copy()
    matches["surface_norm"] = matches["surface"].map(_normalize_surface)
    matches["tourney_date_int"] = pd.to_numeric(matches["tourney_date"], errors="coerce").astype(
        "Int64"
    )
    matches["match_uid"] = (
        matches["circuit"].astype(str)
        + "_"
        + matches["tourney_date_int"].astype(str)
        + "_"
        + matches["winner_id"].astype(str)
        + "_"
        + matches["loser_id"].astype(str)
    )
    matches.to_parquet(processed / "matches.parquet", index=False)
    logger.info("Table `matches` écrite ({} lignes).", len(matches))

    players = _concat_parquet_glob(interim, "*_players.parquet")
    if not players.empty:
        players.to_parquet(processed / "players.parquet", index=False)
        logger.info("Table `players` écrite ({} lignes).", len(players))

    rankings = _concat_parquet_glob(interim, "*_rankings_*.parquet")
    if not rankings.empty:
        rankings = rankings.drop_duplicates(subset=["ranking_date", "player", "circuit"])
        rankings.to_parquet(processed / "rankings.parquet", index=False)
        logger.info("Table `rankings` écrite ({} lignes).", len(rankings))
