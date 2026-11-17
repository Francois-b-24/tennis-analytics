"""Construction des tables analytiques finales (parquet).

Deux étages :

1. **Archive Sackmann** (`data/reference/sackmann_*.parquet`) — construite une
   seule fois par :func:`build_sackmann_archive` à partir des parquets
   intermédiaires. Les dépôts Sackmann n'étant plus mis à jour depuis juin
   2026, cette archive est figée et versionnée.
2. **Tables servies** (`data/processed/*.parquet`) — :func:`build_processed_tables`
   fusionne l'archive et les sources récentes, puis normalise (surface,
   `match_uid`, tri chronologique).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd
from loguru import logger

from tennis_analytics.ids import globalize_ids
from tennis_analytics.transformation.ordering import sort_chronologically

SURFACE_MAP: Final[dict[str, str]] = {
    "hard": "hard",
    "clay": "clay",
    "grass": "grass",
    "carpet": "hard",
}

#: Séparateur des composantes de `match_uid` (absent des données sources).
UID_SEP: Final[str] = "§"


def reference_dir(project_root: Path) -> Path:
    """Dossier des données de référence versionnées (archive, alias)."""
    return project_root / "data" / "reference"


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


def _concat_optional(path: Path, extra: pd.DataFrame | None) -> pd.DataFrame:
    """Concatène un parquet d'archive (s'il existe) et un complément récent."""
    frames = [pd.read_parquet(path)] if path.exists() else []
    if extra is not None and not extra.empty:
        frames.append(extra)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_sackmann_archive(project_root: Path) -> None:
    """Fige l'archive Sackmann dans `data/reference/` à partir de `data/interim/`.

    Les identifiants WTA sont décalés (cf. :mod:`tennis_analytics.ids`) : plus
    aucun joueur n'est partagé entre circuits. Les joueurs sont restreints à
    ceux qui apparaissent dans un match ou un classement depuis 2010, pour
    garder l'archive légère.

    Args:
        project_root: Racine du dépôt.

    Raises:
        RuntimeError: Si les parquets intermédiaires de matchs sont absents.
    """
    interim = project_root / "data" / "interim"
    out_dir = reference_dir(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    matches = _concat_parquet_glob(interim, "*_matches_*.parquet")
    if matches.empty:
        raise RuntimeError("Aucun match intermédiaire : lancez d'abord le téléchargement.")
    matches = globalize_ids(matches, ("winner_id", "loser_id"))
    for col in ("winner_seed", "loser_seed"):
        if col in matches.columns:
            matches[col] = pd.to_numeric(matches[col], errors="coerce")
    matches["source"] = "sackmann"
    matches = sort_chronologically(matches)
    matches.to_parquet(out_dir / "sackmann_matches.parquet", index=False)
    logger.info("Archive matchs : {} lignes", len(matches))

    rankings = _concat_parquet_glob(interim, "*_rankings_*.parquet")
    if not rankings.empty:
        rankings = globalize_ids(rankings, ("player",))
        rankings = rankings.drop_duplicates(subset=["ranking_date", "player", "circuit"])
        rankings = rankings.sort_values(
            ["circuit", "ranking_date", "rank", "player"], kind="mergesort"
        ).reset_index(drop=True)
        rankings.to_parquet(out_dir / "sackmann_rankings.parquet", index=False)
        logger.info("Archive classements : {} lignes", len(rankings))

    players = _concat_parquet_glob(interim, "*_players.parquet")
    if not players.empty:
        players = globalize_ids(players, ("player_id",))
        used = set(matches["winner_id"].astype("int64")) | set(matches["loser_id"].astype("int64"))
        if not rankings.empty:
            used |= set(rankings["player"].astype("int64"))
        players = players.loc[players["player_id"].isin(used)]
        players = players.drop_duplicates(subset=["player_id"]).sort_values(
            "player_id", kind="mergesort"
        )
        players.reset_index(drop=True).to_parquet(out_dir / "sackmann_players.parquet", index=False)
        logger.info("Archive joueurs : {} lignes", len(players))


def finalize_matches(matches: pd.DataFrame) -> pd.DataFrame:
    """Normalise une table de matchs consolidée (surface, uid, ordre).

    Args:
        matches: Matchs toutes sources confondues.

    Returns:
        Table dédupliquée par `match_uid` et triée chronologiquement.
    """
    out = matches.copy()
    out["surface_norm"] = out["surface"].map(_normalize_surface)
    out["tourney_date"] = pd.to_numeric(out["tourney_date"], errors="coerce").astype("int64")
    out["tourney_date_int"] = out["tourney_date"].astype("Int64")
    if "round" not in out.columns:
        out["round"] = ""

    # match_uid : séparateur '§' pour éviter toute collision entre
    # concaténations ambiguës (ex. id 1+2 vs 12+_).
    out["match_uid"] = (
        out["circuit"].astype(str)
        + UID_SEP
        + out["tourney_date"].astype(str)
        + UID_SEP
        + out["winner_id"].astype(str)
        + UID_SEP
        + out["loser_id"].astype(str)
        + UID_SEP
        + out["round"].fillna("").astype(str)
    )
    for col in ("winner_seed", "loser_seed"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    # Doublons résiduels (matchs Davis Cup parfois loggés deux fois).
    before = len(out)
    out = out.drop_duplicates(subset=["match_uid"])
    if before - len(out) > 0:
        logger.info("Doublons matches supprimés : {}", before - len(out))
    assert out["match_uid"].is_unique, "match_uid doit être unique après dédup"
    return sort_chronologically(out)


def build_processed_tables(
    project_root: Path,
    recent_matches: pd.DataFrame | None = None,
    recent_players: pd.DataFrame | None = None,
    recent_rankings: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Fusionne l'archive et les sources récentes, puis écrit `data/processed`.

    Args:
        project_root: Racine du dépôt.
        recent_matches: Matchs postérieurs à l'archive (schéma `matches`).
        recent_players: Nouveaux joueurs (schéma `players`).
        recent_rankings: Classements récents (schéma `rankings`).

    Returns:
        La table `matches` écrite.

    Raises:
        FileNotFoundError: Si l'archive Sackmann est absente.
    """
    ref = reference_dir(project_root)
    processed = project_root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)

    archive_path = ref / "sackmann_matches.parquet"
    if not archive_path.exists():
        raise FileNotFoundError(
            f"Archive absente : {archive_path}. Lancez `tennis-ingest --rebuild-archive`."
        )
    frames = [pd.read_parquet(archive_path)]
    if recent_matches is not None and not recent_matches.empty:
        frames.append(recent_matches)
    matches = finalize_matches(pd.concat(frames, ignore_index=True))
    matches.to_parquet(processed / "matches.parquet", index=False)
    logger.info("Table `matches` écrite ({} lignes).", len(matches))

    players = _concat_optional(ref / "sackmann_players.parquet", recent_players)
    if players.empty:
        return matches
    players = players.drop_duplicates(subset=["player_id"], keep="first")
    players = players.sort_values("player_id", kind="mergesort").reset_index(drop=True)
    players.to_parquet(processed / "players.parquet", index=False)
    logger.info("Table `players` écrite ({} lignes).", len(players))

    rankings = _concat_optional(ref / "sackmann_rankings.parquet", recent_rankings)
    if rankings.empty:
        return matches
    rankings = rankings.drop_duplicates(subset=["ranking_date", "player", "circuit"], keep="last")
    rankings = rankings.sort_values(
        ["circuit", "ranking_date", "rank", "player"], kind="mergesort"
    ).reset_index(drop=True)
    rankings.to_parquet(processed / "rankings.parquet", index=False)
    logger.info("Table `rankings` écrite ({} lignes).", len(rankings))
    return matches
