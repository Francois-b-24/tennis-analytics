"""Reconstruit les parquets interim + processed à partir des CSV déjà dans `data/raw/`.

Utile lorsque le téléchargement a réussi mais que la matérialisation ou la consolidation
a échoué ou n'a pas été exécutée (ex. après correction des dépendances Pandera).
"""

from __future__ import annotations

from loguru import logger

from ingestion.sackmann_loader import get_project_root, materialize_interim_from_raw
from transformation.pipeline import build_processed_tables


def main() -> None:
    """Lit `data/raw/*.csv`, écrit `data/interim/*.parquet` puis `data/processed/*.parquet`."""
    root = get_project_root()
    raw_dir = root / "data" / "raw"
    interim_dir = root / "data" / "interim"

    if not any(raw_dir.glob("atp_matches_*.csv")) and not any(raw_dir.glob("wta_matches_*.csv")):
        logger.error(
            "Aucun CSV de matchs trouvé dans {}. Lancez d'abord : uv run tennis-ingest",
            raw_dir,
        )
        return

    logger.info("Matérialisation des CSV → parquet intermédiaires…")
    materialize_interim_from_raw(raw_dir, interim_dir)
    logger.info("Consolidation vers data/processed/…")
    build_processed_tables(root)
    out = root / "data" / "processed" / "matches.parquet"
    if out.exists():
        logger.info("Terminé : {}", out)
    else:
        logger.error(
            "{} est toujours absent : consultez les messages d'erreur ci-dessus "
            "(souvent validation Pandera ou table de matchs vide).",
            out,
        )


if __name__ == "__main__":
    main()
