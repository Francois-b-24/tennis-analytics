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

    # Garantir l'existence de la colonne `round` (RR vs F pour Tour Finals)
    if "round" not in matches.columns:
        matches["round"] = ""

    # match_uid : séparateur '§' (absent des données Sackmann) pour éviter
    # toute collision entre concaténations ambiguës (ex. id 1+2 vs 12+_).
    sep = "§"
    matches["match_uid"] = (
        matches["circuit"].astype(str)
        + sep
        + matches["tourney_date_int"].astype(str)
        + sep
        + matches["winner_id"].astype(str)
        + sep
        + matches["loser_id"].astype(str)
        + sep
        + matches["round"].fillna("").astype(str)
    )

    # Les colonnes *_seed contiennent des valeurs mixtes (entiers + 'WC', 'Q', 'LL'…)
    for col in ("winner_seed", "loser_seed"):
        if col in matches.columns:
            matches[col] = pd.to_numeric(matches[col], errors="coerce")

    # Suppression des doublons restants (matchs Davis Cup parfois loggés en double)
    before = len(matches)
    matches = matches.drop_duplicates(subset=["match_uid"])
    if before - len(matches) > 0:
        logger.info("Doublons matches.parquet supprimés : {}", before - len(matches))

    assert matches["match_uid"].is_unique, "match_uid doit être unique après dédup"

    matches.to_parquet(processed / "matches.parquet", index=False)
    logger.info("Table `matches` écrite ({} lignes).", len(matches))

    players = _concat_parquet_glob(interim, "*_players.parquet")
    if not players.empty:
        # Dédup : un joueur peut apparaître dans atp_players ET wta_players
        # (cas du double mixte). On agrège pour avoir 1 ligne par player_id.
        before = len(players)

        def _first_non_null(s: pd.Series) -> object:
            s = s.dropna()
            return s.iloc[0] if len(s) > 0 else None

        agg_dict = {
            col: _first_non_null for col in players.columns if col not in ("player_id", "circuit")
        }
        agg_dict["circuit"] = lambda s: "BOTH" if s.nunique() > 1 else s.iloc[0]
        players = players.groupby("player_id", as_index=False).agg(agg_dict)
        logger.info(
            "Doublons players.parquet fusionnés : {} → {} ({} BOTH)",
            before,
            len(players),
            int((players["circuit"] == "BOTH").sum()),
        )

        players.to_parquet(processed / "players.parquet", index=False)
        logger.info("Table `players` écrite ({} lignes).", len(players))

    rankings = _concat_parquet_glob(interim, "*_rankings_*.parquet")
    if not rankings.empty:
        rankings = rankings.drop_duplicates(subset=["ranking_date", "player", "circuit"])
        rankings.to_parquet(processed / "rankings.parquet", index=False)
        logger.info("Table `rankings` écrite ({} lignes).", len(rankings))
