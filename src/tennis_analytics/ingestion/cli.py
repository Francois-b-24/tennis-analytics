"""Point d'entrée CLI de l'ingestion.

Modes :

- `tennis-ingest` : collecte les sources récentes puis reconstruit
  `data/processed` à partir de l'archive Sackmann figée + ces sources.
- `tennis-ingest --rebuild-archive` : retélécharge les CSV Sackmann (miroir
  d'archive) et régénère `data/reference/sackmann_*.parquet`. Opération
  ponctuelle : l'archive ne change plus.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from tennis_analytics.ingestion.sackmann_loader import (
    download_atp_wta_matches,
    download_players,
    download_rankings,
    get_project_root,
    materialize_interim_from_raw,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tennis-ingest",
        description="Ingestion ATP/WTA : archive Sackmann + sources récentes → data/processed.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Racine du projet (par défaut : auto-détectée depuis ROOT_PATH ou le code).",
    )
    parser.add_argument(
        "--rebuild-archive",
        action="store_true",
        help="Régénère l'archive Sackmann (data/reference) depuis le miroir CSV.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Avec --rebuild-archive : réutilise les CSV déjà présents dans data/raw/.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Ne pas reconstruire les tables processed.",
    )
    return parser.parse_args(argv)


def rebuild_archive(project_root: Path, *, skip_download: bool = False) -> None:
    """Télécharge les CSV Sackmann et fige l'archive de référence.

    Raises:
        RuntimeError: Si aucun fichier de matchs n'a pu être obtenu.
    """
    from tennis_analytics.transformation.pipeline import build_sackmann_archive

    raw_dir = project_root / "data" / "raw"
    interim_dir = project_root / "data" / "interim"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if not skip_download:
        saved = download_atp_wta_matches(raw_dir)
        if not saved:
            raise RuntimeError("Aucun CSV de matchs téléchargé : source d'archive injoignable.")
        download_rankings(raw_dir)
        download_players(raw_dir)
    materialize_interim_from_raw(raw_dir, interim_dir)
    build_sackmann_archive(project_root)


def main(argv: list[str] | None = None) -> int:
    """Lance l'ingestion.

    Returns:
        Code de sortie (0 = succès, 1 = échec). Un échec est **toujours**
        signalé par un code non nul : un job vert doit signifier des données
        réellement à jour.
    """
    args = _parse_args(argv)
    project_root = args.root.resolve() if args.root else get_project_root()
    logger.info("Ingestion : racine={} rebuild_archive={}", project_root, args.rebuild_archive)

    try:
        if args.rebuild_archive:
            rebuild_archive(project_root, skip_download=args.skip_download)

        if not args.skip_build:
            from tennis_analytics.transformation.pipeline import build_processed_tables

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
