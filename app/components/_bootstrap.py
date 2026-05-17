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


@st.cache_resource(show_spinner=False)
def _cached_connection(root_str: str) -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB cachée par chemin racine."""
    from db.duckdb_session import create_connection

    return create_connection(Path(root_str))


def init_app(
    caller_file: str | Path | None = None,
) -> tuple[Path, duckdb.DuckDBPyConnection]:
    """Initialise une page Streamlit : sys.path, env, connexion DuckDB.

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
    return root, _cached_connection(str(root))
