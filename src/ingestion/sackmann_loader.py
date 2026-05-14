"""Téléchargement, validation et matérialisation des jeux Sackmann (ATP/WTA)."""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pandas as pd
from loguru import logger

from ingestion.schemas import MatchesSchema, PlayersSchema, RankingsSchema

RAW_GITHUB: Final[str] = "https://raw.githubusercontent.com"
ATP_REPO: Final[str] = "JeffSackmann/tennis_atp/master"
WTA_REPO: Final[str] = "JeffSackmann/tennis_wta/master"
MIN_TOURNEY_DATE: Final[int] = 20100101
USER_AGENT: Final[str] = (
    "tennis-analytics-ingestion/0.1 (+https://github.com/Francois-b-24/tennis-analytics)"
)


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """Résumé d'un téléchargement."""

    url: str
    destination: Path
    bytes_written: int


def get_project_root() -> Path:
    """Retourne la racine du projet depuis `ROOT_PATH` ou la découverte locale.

    Returns:
        Chemin absolu vers la racine du dépôt.
    """
    env = os.getenv("ROOT_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _build_url(repo_path: str, filename: str) -> str:
    return f"{RAW_GITHUB}/{repo_path}/{filename}"


def download_to(url: str, destination: Path, timeout_s: int = 60) -> DownloadResult:
    """Télécharge une ressource HTTP vers un fichier.

    Args:
        url: URL complète du fichier.
        destination: Chemin de sortie (création des dossiers parents).
        timeout_s: Délai max en secondes.

    Returns:
        Métadonnées d'écriture disque.

    Raises:
        urllib.error.HTTPError: Si le serveur retourne une erreur HTTP.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    logger.info("Téléchargement : {}", url)
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        payload = response.read()
    destination.write_bytes(payload)
    logger.info("Fichier écrit : {} ({} octets)", destination, len(payload))
    return DownloadResult(url=url, destination=destination, bytes_written=len(payload))


def download_with_retries(url: str, destination: Path, attempts: int = 3) -> DownloadResult | None:
    """Télécharge avec tentatives et backoff simple.

    Args:
        url: URL à récupérer.
        destination: Fichier cible.
        attempts: Nombre de tentatives.

    Returns:
        Résultat ou None si échec définitif (ex. 404).
    """
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return download_to(url, destination)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                logger.warning("Ressource introuvable (404) : {}", url)
                return None
            last_error = exc
            logger.warning("Échec HTTP (tentative {}/{}): {}", attempt, attempts, exc)
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last_error = exc
            logger.warning("Erreur réseau (tentative {}/{}): {}", attempt, attempts, exc)
        time.sleep(1.5 * attempt)
    if last_error:
        logger.error("Abandon du téléchargement après {} essais : {}", attempts, last_error)
    return None


def _filter_from_2010(frame: pd.DataFrame) -> pd.DataFrame:
    if "tourney_date" not in frame.columns:
        logger.error("Colonne `tourney_date` absente : impossible de filtrer 2010+")
        return frame
    coerced = pd.to_numeric(frame["tourney_date"], errors="coerce").fillna(0).astype("int64")
    mask = coerced >= MIN_TOURNEY_DATE
    return frame.loc[mask].copy()


def _validate_matches(frame: pd.DataFrame) -> pd.DataFrame:
    """Valide les matchs via Pandera et retourne le DataFrame typé."""
    checked = MatchesSchema.validate(frame, lazy=True)
    return pd.DataFrame(checked)


def _validate_players(frame: pd.DataFrame) -> pd.DataFrame:
    checked = PlayersSchema.validate(frame, lazy=True)
    return pd.DataFrame(checked)


def _validate_rankings(frame: pd.DataFrame) -> pd.DataFrame:
    checked = RankingsSchema.validate(frame, lazy=True)
    return pd.DataFrame(checked)


def _years_span() -> Iterable[int]:
    from datetime import datetime

    current = datetime.now().year
    return range(2010, current + 1)


def download_atp_wta_matches(raw_dir: Path) -> list[Path]:
    """Télécharge les fichiers de matchs ATP/WTA depuis 2010.

    Args:
        raw_dir: Dossier `data/raw`.

    Returns:
        Liste des fichiers CSV téléchargés.
    """
    saved: list[Path] = []
    for year in _years_span():
        for circuit, repo in (("ATP", ATP_REPO), ("WTA", WTA_REPO)):
            prefix = "atp" if circuit == "ATP" else "wta"
            filename = f"{prefix}_matches_{year}.csv"
            url = _build_url(repo, filename)
            dest = raw_dir / filename
            result = download_with_retries(url, dest)
            if result:
                saved.append(dest)
    return saved


def download_rankings(raw_dir: Path) -> list[Path]:
    """Télécharge les fichiers de classements par décennie + courant si disponible."""
    saved: list[Path] = []
    ranking_files = [
        ("atp_rankings_10s.csv", ATP_REPO),
        ("atp_rankings_20s.csv", ATP_REPO),
        ("atp_rankings_current.csv", ATP_REPO),
        ("wta_rankings_10s.csv", WTA_REPO),
        ("wta_rankings_20s.csv", WTA_REPO),
        ("wta_rankings_current.csv", WTA_REPO),
    ]
    for fname, repo in ranking_files:
        url = _build_url(repo, fname)
        dest = raw_dir / fname
        result = download_with_retries(url, dest)
        if result:
            saved.append(dest)
    return saved


def download_players(raw_dir: Path) -> list[Path]:
    """Télécharge les fichiers joueurs ATP/WTA."""
    saved: list[Path] = []
    for fname, repo in (("atp_players.csv", ATP_REPO), ("wta_players.csv", WTA_REPO)):
        url = _build_url(repo, fname)
        dest = raw_dir / fname
        result = download_with_retries(url, dest)
        if result is not None:
            saved.append(dest)
    return saved


def csv_to_parquet_filtered_matches(csv_path: Path, parquet_path: Path, circuit: str) -> None:
    """Lit un CSV matchs, filtre 2010+, valide et écrit un parquet intermédiaire."""
    frame = pd.read_csv(csv_path, low_memory=False)
    frame = _filter_from_2010(frame)
    frame["circuit"] = circuit
    frame = _validate_matches(frame)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(parquet_path, index=False)
    logger.info("Parquet matchs écrit : {} ({} lignes)", parquet_path, len(frame))


def csv_to_parquet_players(csv_path: Path, parquet_path: Path, circuit: str) -> None:
    frame = pd.read_csv(csv_path, low_memory=False)
    frame["circuit"] = circuit
    frame = _validate_players(frame)
    frame.to_parquet(parquet_path, index=False)
    logger.info("Parquet joueurs écrit : {} ({} lignes)", parquet_path, len(frame))


def csv_to_parquet_rankings(csv_path: Path, parquet_path: Path, circuit: str) -> None:
    frame = pd.read_csv(csv_path, low_memory=False)
    frame["circuit"] = circuit
    frame = _validate_rankings(frame)
    frame = frame.loc[frame["ranking_date"] >= MIN_TOURNEY_DATE].copy()
    frame.to_parquet(parquet_path, index=False)
    logger.info("Parquet classements écrit : {} ({} lignes)", parquet_path, len(frame))


def materialize_interim_from_raw(raw_dir: Path, interim_dir: Path) -> None:
    """Convertit les CSV bruts en parquets intermédiaires typés."""
    interim_dir.mkdir(parents=True, exist_ok=True)
    for csv_path in sorted(raw_dir.glob("atp_matches_*.csv")):
        year = csv_path.stem.split("_")[-1]
        csv_to_parquet_filtered_matches(
            csv_path, interim_dir / f"atp_matches_{year}.parquet", "ATP"
        )
    for csv_path in sorted(raw_dir.glob("wta_matches_*.csv")):
        year = csv_path.stem.split("_")[-1]
        csv_to_parquet_filtered_matches(
            csv_path, interim_dir / f"wta_matches_{year}.parquet", "WTA"
        )

    for fname, circuit in (("atp_players.csv", "ATP"), ("wta_players.csv", "WTA")):
        path = raw_dir / fname
        if path.exists():
            csv_to_parquet_players(path, interim_dir / fname.replace(".csv", ".parquet"), circuit)

    for fname, circuit in (
        ("atp_rankings_10s.csv", "ATP"),
        ("atp_rankings_20s.csv", "ATP"),
        ("atp_rankings_current.csv", "ATP"),
        ("wta_rankings_10s.csv", "WTA"),
        ("wta_rankings_20s.csv", "WTA"),
        ("wta_rankings_current.csv", "WTA"),
    ):
        path = raw_dir / fname
        if path.exists():
            csv_to_parquet_rankings(path, interim_dir / fname.replace(".csv", ".parquet"), circuit)


def run_ingestion_pipeline(root: Path | None = None) -> None:
    """Orchestre téléchargements, validations et écritures parquet intermédiaires."""
    project_root = root or get_project_root()
    raw_dir = project_root / "data" / "raw"
    interim_dir = project_root / "data" / "interim"
    raw_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Début de l'ingestion Sackmann (racine projet : {})", project_root)
    download_atp_wta_matches(raw_dir)
    download_rankings(raw_dir)
    download_players(raw_dir)
    materialize_interim_from_raw(raw_dir, interim_dir)

    from transformation.pipeline import build_processed_tables

    build_processed_tables(project_root)
    logger.info("Ingestion terminée.")
