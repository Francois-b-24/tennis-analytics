"""Bootstrap commun aux pages Streamlit.

Centralise :
- la résolution de ROOT_PATH (.env ou chemin fichier)
- l'injection des dossiers `app/`, racine et `src/` dans sys.path
- la création (cachée) de la connexion DuckDB

Usage dans chaque page :

    from components._bootstrap import init_app

    ROOT, connection = init_app()
"""

from __future__ import annotations

import os
import sys
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


@st.cache_resource(show_spinner=False)
def _cached_connection(root_str: str, fingerprint: str) -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB cachée par racine **et** empreinte des données.

    `fingerprint` n'est pas utilisé dans le corps : il fait partie de la clé de
    cache pour forcer une reconstruction des vues quand les parquets changent.
    """
    from tennis_analytics.db.duckdb_session import create_connection

    return create_connection(Path(root_str))


#: Séparateur interne des clés de cache (absent des chemins POSIX/Windows).
_KEY_SEP = "\x1f"


def data_key(root: str | Path) -> str:
    """Clé de cache combinant racine projet et empreinte des données.

    À passer aux fonctions `@st.cache_data` à la place de `str(_ROOT)` : elle
    change dès qu'un parquet est réécrit, ce qui purge les agrégations périmées.

    Args:
        root: Racine du projet.

    Returns:
        Clé opaque, à redonner à :func:`connection_for_key`.
    """
    root_str = str(root)
    return f"{root_str}{_KEY_SEP}{data_fingerprint(root_str)}"


def connection_for_key(key: str) -> duckdb.DuckDBPyConnection:
    """Retourne la connexion DuckDB associée à une clé produite par :func:`data_key`.

    Tolère une clé « nue » (simple racine) pour rester rétrocompatible.
    """
    root_str, _, fingerprint = key.partition(_KEY_SEP)
    return _cached_connection(root_str, fingerprint or data_fingerprint(root_str))


def init_app(
    caller_file: str | Path | None = None,
) -> tuple[Path, duckdb.DuckDBPyConnection]:
    """Initialise une page Streamlit : sys.path, env, connexion DuckDB.

    La connexion est invalidée automatiquement lorsque les parquets traités
    sont mis à jour (cf. `data_fingerprint`) — aucun redémarrage manuel requis.

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
    return root, _cached_connection(str(root), data_fingerprint(str(root)))
