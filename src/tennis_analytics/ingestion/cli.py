"""Point d'entrée CLI de l'ingestion.

Modes :

- `tennis-ingest` : collecte les sources récentes (tennis-data, ESPN) puis
  reconstruit `data/processed` à partir de l'archive Sackmann figée + ces
  sources, et écrit `data/processed/metadata.json`.
- `tennis-ingest --offline` : reconstruit depuis l'archive seule.
- `tennis-ingest --rebuild-archive` : retélécharge les CSV Sackmann (miroir
  d'archive) et régénère `data/reference/sackmann_*.parquet`. Opération
  ponctuelle : l'archive ne change plus.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
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
        "--offline",
        action="store_true",
        help="N'interroge aucune source récente : reconstruit depuis l'archive seule.",
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


def write_metadata(project_root: Path, matches: pd.DataFrame, report: dict) -> Path:
    """Écrit `data/processed/metadata.json` (fraîcheur affichée par l'app).

    Contient la date du dernier match par circuit, le volume par source et le
    nombre de résultats provisoires (ESPN, pas encore confirmés par tennis-data).
    """
    played = matches["match_date"] if "match_date" in matches.columns else None
    day = matches["tourney_date"] if played is None else played.fillna(matches["tourney_date"])
    frame = matches.assign(_day=day.astype("int64"))
    sources = matches["source"].fillna("sackmann") if "source" in matches.columns else None
    metadata = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "last_match_date": {c: int(g["_day"].max()) for c, g in frame.groupby("circuit")},
        "matches_by_source": (
            {k: int(v) for k, v in sources.value_counts().items()} if sources is not None else {}
        ),
        "provisional_matches": int((sources == "espn").sum()) if sources is not None else 0,
        "archive_cutoff": report.get("cutoff", {}),
        "new_players": report.get("new_players", []),
        "espn_error": report.get("espn_error"),
    }
    path = project_root / "data" / "processed" / "metadata.json"
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("Métadonnées écrites : {}", metadata["last_match_date"])
    return path


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

            recent = None
            if not args.offline:
                from tennis_analytics.ingestion.recent import collect_recent

                recent = collect_recent(project_root)
            matches = build_processed_tables(
                project_root,
                recent_matches=recent.matches if recent else None,
                recent_players=recent.players if recent else None,
                recent_rankings=recent.rankings if recent else None,
            )
            write_metadata(project_root, matches, recent.report if recent else {})
        else:
            logger.info("Build processed ignoré (--skip-build)")

        logger.info("Ingestion terminée avec succès.")
        return 0
    except Exception as exc:
        logger.exception("Ingestion échouée : {}", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
