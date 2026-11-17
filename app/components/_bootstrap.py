"""Bootstrap commun aux pages Streamlit.

Centralise :
- la résolution de ROOT_PATH (.env ou chemin fichier)
- l'injection des dossiers `app/`, racine et `src/` dans sys.path
- la synchronisation des données publiées (Release GitHub `data-latest`)
- la création (cachée) de la connexion DuckDB

Usage dans chaque page :

    from components._bootstrap import init_app

    ROOT, connection = init_app()
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

import duckdb
import streamlit as st
from dotenv import load_dotenv


def _resolve_root(caller_file: Path | None = None) -> Path:
    """Détermine la racine du projet à partir du fichier appelant.

    Cherche le premier ancêtre contenant `pyproject.toml` (rapide et robuste).
    """
    start = caller_file or Path(__file__)
    for parent in start.resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback : 2 niveaux au-dessus de app/components/
    return Path(__file__).resolve().parents[2]


def _ensure_sys_path(root: Path) -> None:
    app_dir = root / "app"
    src_dir = root / "src"
    for path in (app_dir, root, src_dir):
        sp = str(path)
        if sp not in sys.path:
            sys.path.insert(0, sp)


#: Durée (secondes) de mise en cache de l'empreinte des données.
#: Au-delà, on relit les mtime des parquets pour détecter une mise à jour.
DATA_FINGERPRINT_TTL = 300


@st.cache_data(ttl=DATA_FINGERPRINT_TTL, show_spinner=False)
def data_fingerprint(root_str: str) -> str:
    """Empreinte des parquets traités (nom, taille, mtime).

    Sert de clé de cache : dès que l'ingestion quotidienne réécrit un parquet,
    l'empreinte change, ce qui invalide automatiquement la connexion DuckDB et
    les agrégations dérivées. Sans elle, l'app sert indéfiniment les données
    chargées au démarrage et impose un redémarrage manuel.

    Args:
        root_str: Racine du projet.

    Returns:
        Empreinte stable, recalculée au plus toutes les `DATA_FINGERPRINT_TTL` s.
    """
    processed = Path(root_str) / "data" / "processed"
    if not processed.exists():
        return "absent"
    parts: list[str] = []
    for path in sorted(processed.rglob("*")):
        if path.suffix not in {".parquet", ".joblib"}:
            continue
        stat = path.stat()
        parts.append(f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}")
    return "|".join(parts) if parts else "vide"


#: Release où le workflow d'ingestion publie les données (toutes les 3 h).
#: `TENNIS_DATA_RELEASE_URL=""` désactive la synchronisation (tests, hors ligne).
DEFAULT_RELEASE_URL = (
    "https://github.com/Francois-b-24/tennis-analytics/releases/download/data-latest"
)

#: Fréquence (secondes) de vérification d'une nouvelle publication.
DATA_SYNC_TTL = 900

_HTTP_TIMEOUT = 20


def _release_url() -> str:
    return os.getenv("TENNIS_DATA_RELEASE_URL", DEFAULT_RELEASE_URL).rstrip("/")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "tennis-analytics-app"})
    with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as response:
        return response.read()


def _download_release(base_url: str, manifest: dict, cache_root: Path) -> Path:
    """Télécharge une publication complète dans `cache_root/<data_hash>`.

    Chaque fichier est vérifié (SHA-256) avant que le dossier ne soit rendu
    visible par un renommage atomique : l'app ne lit jamais une publication
    partielle.
    """
    target = cache_root / manifest["data_hash"][:16]
    if (target / ".complete").exists():
        return target
    staging = cache_root / f".tmp-{uuid.uuid4().hex}"
    try:
        for rel, meta in manifest["files"].items():
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(_fetch(f"{base_url}/{Path(rel).name}"))
            if _sha256(dest) != meta["sha256"]:
                raise ValueError(f"Empreinte incorrecte pour {rel} (publication en cours ?)")
        (staging / ".complete").write_text(manifest["data_hash"])
        try:
            staging.rename(target)
        except OSError:
            # Une autre session a terminé le même téléchargement entre-temps.
            shutil.rmtree(staging, ignore_errors=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    # Ménage : on ne garde que la publication courante.
    for old in cache_root.iterdir():
        if old.is_dir() and old != target and not old.name.startswith(".tmp-"):
            shutil.rmtree(old, ignore_errors=True)
    return target


@st.cache_data(ttl=DATA_SYNC_TTL, show_spinner=False)
def resolve_data_dir(root_str: str) -> tuple[str, str]:
    """Dossier des données à servir et son empreinte.

    1. Publication la plus récente de la Release (relue toutes les 15 min) ;
    2. à défaut (réseau, publication incomplète), copie de secours versionnée
       dans `data/processed`.

    Returns:
        (dossier des parquets, empreinte servant de clé de cache).
    """
    base_url = _release_url()
    local = (str(Path(root_str) / "data" / "processed"), data_fingerprint(root_str))
    if not base_url:
        return local
    try:
        # Paramètre anti-cache : une réponse intermédiaire périmée ferait servir
        # indéfiniment une ancienne publication.
        manifest = json.loads(_fetch(f"{base_url}/manifest.json?t={int(time.time())}"))
        cache_root = Path(tempfile.gettempdir()) / "tennis-analytics-data"
        cache_root.mkdir(parents=True, exist_ok=True)
        folder = _download_release(base_url, manifest, cache_root)
        from loguru import logger

        logger.info(
            "Données servies : publication du {} ({})",
            manifest.get("generated_at"),
            manifest["data_hash"][:12],
        )
        return str(folder), f"release:{manifest['data_hash']}"
    except Exception as exc:  # tout échec (réseau, publication partielle) → copie locale
        from loguru import logger

        logger.warning("Release de données injoignable, copie locale servie : {}", exc)
        return local


def processed_dir(root: str | Path) -> Path:
    """Dossier des données actuellement servies (Release ou copie locale)."""
    return Path(resolve_data_dir(str(root))[0])


def load_metadata(root: str | Path) -> dict:
    """Métadonnées de fraîcheur (`metadata.json`) des données servies."""
    path = processed_dir(root) / "metadata.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@st.cache_resource(ttl=24 * 3600, show_spinner=False)
def _cached_connection(data_dir: str, fingerprint: str) -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB cachée par dossier **et** empreinte des données.

    `fingerprint` n'est pas utilisé dans le corps : il fait partie de la clé de
    cache pour forcer une reconstruction des vues quand les données changent.
    """
    from tennis_analytics.db.duckdb_session import create_connection

    return create_connection(processed_dir=Path(data_dir))


#: Séparateur interne des clés de cache (absent des chemins POSIX/Windows).
_KEY_SEP = "\x1f"


def data_key(root: str | Path) -> str:
    """Clé de cache combinant racine projet et empreinte des données servies.

    À passer en premier argument des fonctions `@st.cache_data` (paramètre
    `cache_key`, jamais préfixé `_`) : elle change dès qu'une nouvelle
    publication est disponible, ce qui purge les agrégations périmées.

    Args:
        root: Racine du projet.

    Returns:
        Clé opaque, à redonner à :func:`connection_for_key`.
    """
    root_str = str(root)
    return f"{root_str}{_KEY_SEP}{resolve_data_dir(root_str)[1]}"


def connection_for_key(key: str) -> duckdb.DuckDBPyConnection:
    """Retourne la connexion DuckDB associée à une clé produite par :func:`data_key`."""
    root_str, _, _ = key.partition(_KEY_SEP)
    folder, fingerprint = resolve_data_dir(root_str)
    return _cached_connection(folder, fingerprint)


def init_app(
    caller_file: str | Path | None = None,
) -> tuple[Path, duckdb.DuckDBPyConnection]:
    """Initialise une page Streamlit : sys.path, env, connexion DuckDB.

    La connexion est invalidée automatiquement à chaque nouvelle publication
    des données (cf. :func:`resolve_data_dir`) — aucun redémarrage requis.

    Args:
        caller_file: `__file__` de la page appelante (optionnel mais recommandé).

    Returns:
        (racine du projet, connexion DuckDB cachée).
    """
    caller = Path(caller_file) if caller_file is not None else None
    root = _resolve_root(caller)
    load_dotenv(root / ".env")
    os.environ.setdefault("ROOT_PATH", str(root))
    _ensure_sys_path(root)
    folder, fingerprint = resolve_data_dir(str(root))
    return root, _cached_connection(folder, fingerprint)
