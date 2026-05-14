"""Recalcule les séries Elo et matérialise les parquets dérivés."""

from __future__ import annotations

import pandas as pd
from loguru import logger

from ingestion.sackmann_loader import get_project_root
from ratings.elo import compute_elo_from_matches


def main() -> None:
    """Point d'entrée : lit `matches.parquet` et écrit les tables Elo."""
    root = get_project_root()
    processed = root / "data" / "processed"
    matches_path = processed / "matches.parquet"
    if not matches_path.exists():
        logger.error("Fichier introuvable : {}", matches_path)
        return

    matches = pd.read_parquet(matches_path)
    history, latest, context = compute_elo_from_matches(matches)
    history.to_parquet(processed / "elo_history.parquet", index=False)
    latest.to_parquet(processed / "elo_latest.parquet", index=False)
    context.to_parquet(processed / "match_elo_context.parquet", index=False)
    logger.info(
        "Elo recalculé : historique={} lignes, derniers états={} joueurs.",
        len(history),
        len(latest),
    )


if __name__ == "__main__":
    main()
