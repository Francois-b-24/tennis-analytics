"""Point d'entrée CLI pour lancer l'ingestion complète."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from ingestion.sackmann_loader import (
    download_atp_wta_matches,
    download_players,
    download_rankings,
    get_project_root,
    materialize_interim_from_raw,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tennis-ingest",
        description="Ingestion Sackmann ATP/WTA : téléchargement, matérialisation, build tables.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Racine du projet (par défaut : auto-détectée depuis ROOT_PATH ou le code).",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Ne pas re-télécharger les CSV (utiliser les fichiers locaux data/raw/).",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Ne pas reconstruire les tables processed (utile pour debug ingestion seule).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Lance le pipeline d'ingestion Sackmann.

    Returns:
        Code de sortie (0 = succès, 1 = échec).
    """
    args = _parse_args(argv)
    project_root = args.root.resolve() if args.root else get_project_root()
    raw_dir = project_root / "data" / "raw"
    interim_dir = project_root / "data" / "interim"
    raw_dir.mkdir(parents=True, exist_ok=True)
    interim_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Ingestion : racine={} skip_download={}", project_root, args.skip_download)

    try:
        if not args.skip_download:
            download_atp_wta_matches(raw_dir)
            download_rankings(raw_dir)
            download_players(raw_dir)
        else:
            logger.info("Téléchargements ignorés (--skip-download)")

        materialize_interim_from_raw(raw_dir, interim_dir)

        if not args.skip_build:
            from transformation.pipeline import build_processed_tables

            build_processed_tables(project_root)
        else:
            logger.info("Build processed ignoré (--skip-build)")

        logger.info("Ingestion terminée avec succès.")
        return 0
    except Exception as exc:
        logger.exception("Ingestion échouée : {}", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
