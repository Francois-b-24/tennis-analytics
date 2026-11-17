"""Publication des données : manifest, détection de changement, garde-fous.

Les données servies par l'app sont publiées dans la Release GitHub
`data-latest` (et non plus commitées sur `main` à chaque ingestion) : le dépôt
ne grossit plus, et l'app les récupère sans redéploiement.

Le manifest décrit chaque fichier (taille, SHA-256) et porte deux empreintes :

- `input_hash` : tables issues de l'ingestion (matchs, joueurs, classements).
  S'il n'a pas changé, inutile de recalculer l'Elo et le modèle ni de publier.
- `data_hash` : tous les fichiers publiés ; c'est la clé de cache côté app.

Usage (workflow) :

    python -m tennis_analytics.publish changed --previous previous/manifest.json
    python -m tennis_analytics.publish check --previous previous/manifest.json
    python -m tennis_analytics.publish manifest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from loguru import logger

from tennis_analytics.ingestion.sackmann_loader import get_project_root

#: Tables issues de l'ingestion (déterminent s'il faut recalculer).
INPUT_FILES = ("matches.parquet", "players.parquet", "rankings.parquet")

#: Seuil de non-régression du volume (cf. ancien contrôle du workflow).
MIN_VOLUME_RATIO = 0.90

#: Au-delà, les données sont jugées périmées (hors intersaison).
STALE_AFTER_DAYS = 10


def published_files(processed: Path) -> list[Path]:
    """Fichiers publiés : parquets, modèle et métadonnées (hors manifest)."""
    files = sorted(processed.glob("*.parquet")) + sorted(processed.glob("models/*.joblib"))
    meta = processed / "metadata.json"
    if meta.exists():
        files.append(meta)
    return files


def sha256_file(path: Path) -> str:
    """Empreinte SHA-256 d'un fichier."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _combined(entries: dict[str, dict[str, Any]], names: list[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(names):
        digest.update(f"{name}:{entries[name]['sha256']}\n".encode())
    return digest.hexdigest()


def input_hash(processed: Path) -> str:
    """Empreinte des tables d'ingestion seules."""
    entries = {name: {"sha256": sha256_file(processed / name)} for name in INPUT_FILES}
    return _combined(entries, list(INPUT_FILES))


def build_manifest(processed: Path) -> dict[str, Any]:
    """Construit le manifest des fichiers publiés.

    `metadata.json` (horodaté à chaque exécution) est exclu de `data_hash`
    pour qu'une ingestion sans nouveauté ne change pas la clé de cache.
    """
    files: dict[str, dict[str, Any]] = {}
    for path in published_files(processed):
        rel = path.relative_to(processed).as_posix()
        files[rel] = {"sha256": sha256_file(path), "size": path.stat().st_size}
    metadata = {}
    if (processed / "metadata.json").exists():
        metadata = json.loads((processed / "metadata.json").read_text(encoding="utf-8"))
    rows = {
        name.removesuffix(".parquet"): pq.ParquetFile(processed / name).metadata.num_rows
        for name in ("matches.parquet", "players.parquet")
    }
    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "input_hash": input_hash(processed),
        "data_hash": _combined(files, [n for n in files if n != "metadata.json"]),
        "rows": rows,
        "last_match_date": metadata.get("last_match_date", {}),
        "files": files,
    }


def _read_previous(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def regressions(current: dict[str, Any], previous: dict[str, Any] | None) -> list[str]:
    """Liste les régressions bloquantes par rapport à la publication précédente.

    - chute de volume > 10 % (ingestion partielle) ;
    - date du dernier match qui recule (source amputée).
    """
    if not previous:
        return []
    errors = []
    for table, before in (previous.get("rows") or {}).items():
        after = current["rows"].get(table, 0)
        if before and after < before * MIN_VOLUME_RATIO:
            errors.append(f"{table} : chute anormale {before} → {after}")
    for circuit, before in (previous.get("last_match_date") or {}).items():
        after = current["last_match_date"].get(circuit, 0)
        if after < before:
            errors.append(f"{circuit} : dernier match recule {before} → {after}")
    return errors


def is_off_season(day: date) -> bool:
    """Intersaison : pas de tournoi entre fin novembre et la fin décembre."""
    return (day.month == 11 and day.day >= 25) or (day.month == 12 and day.day <= 27)


def staleness(last_match_date: dict[str, int], today: date) -> str | None:
    """Message d'alerte si aucun match récent hors intersaison, sinon None."""
    if not last_match_date or is_off_season(today):
        return None
    latest = max(last_match_date.values())
    age = (today - datetime.strptime(str(latest), "%Y%m%d").date()).days
    if age > STALE_AFTER_DAYS:
        return f"Aucun nouveau match depuis {age} jours (dernier : {latest})."
    return None


def _write_output(key: str, value: str) -> None:
    target = os.getenv("GITHUB_OUTPUT")
    if target:
        with Path(target).open("a", encoding="utf-8") as handle:
            handle.write(f"{key}={value}\n")
    print(f"{key}={value}")


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée CLI (cf. docstring du module)."""
    parser = argparse.ArgumentParser(prog="python -m tennis_analytics.publish")
    parser.add_argument("command", choices=["changed", "check", "manifest"])
    parser.add_argument("--previous", type=Path, default=None)
    args = parser.parse_args(argv)

    processed = get_project_root() / "data" / "processed"
    previous = _read_previous(args.previous)

    if args.command == "changed":
        changed = previous is None or previous.get("input_hash") != input_hash(processed)
        _write_output("changed", "true" if changed else "false")
        return 0

    manifest = build_manifest(processed)
    if args.command == "check":
        errors = regressions(manifest, previous)
        for error in errors:
            logger.error(error)
        stale = staleness(manifest["last_match_date"], date.today())
        _write_output("stale", stale or "")
        return 1 if errors else 0

    (processed / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    logger.info("Manifest écrit (data_hash={})", manifest["data_hash"][:12])
    return 0


if __name__ == "__main__":
    sys.exit(main())
