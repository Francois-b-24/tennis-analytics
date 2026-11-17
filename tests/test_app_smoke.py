"""Smoke tests des pages Streamlit (garde-fou de non-régression).

Chaque page est exécutée en mode headless via `AppTest`, sur les parquets réels
de `data/processed`. On vérifie seulement qu'aucune exception n'est levée et
qu'un contenu minimal est rendu : c'est le filet qui manquait à `pytest`, qui
ne chargeait jusqu'ici aucune page.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
PROCESSED = ROOT / "data" / "processed"

pytestmark = pytest.mark.skipif(
    not (PROCESSED / "matches.parquet").exists(),
    reason="Parquets traités absents : smoke tests ignorés.",
)

PAGES = [APP_DIR / "Home.py", *sorted((APP_DIR / "pages").glob("*.py"))]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem)
def test_page_renders_without_exception(page: Path) -> None:
    """La page s'exécute de bout en bout sans exception."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(page), default_timeout=120)
    at.run()
    assert not at.exception, "\n".join(
        "\n".join(e.stack_trace or []) or str(e.value) for e in at.exception
    )
    assert len(at.main.children) > 0
