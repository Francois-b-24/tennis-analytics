"""Smoke tests des pages Streamlit (garde-fou de non-régression).

L'app est exécutée en mode headless via `AppTest`, sur les parquets réels de
`data/processed`, en passant par le routeur `app/Home.py` (st.navigation) :
chaque page est visitée et ne doit lever aucune exception. C'est le filet qui
manquait à `pytest`, qui ne chargeait jusqu'ici aucune page.
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

VIEWS = sorted(p.name for p in (APP_DIR / "views").glob("*.py") if p.name != "redirect_top20.py")


def _errors(at) -> str:
    return "\n".join("\n".join(e.stack_trace or []) or str(e.value) for e in at.exception)


def _app():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP_DIR / "Home.py"), default_timeout=180)
    at.run()
    assert not at.exception, _errors(at)
    return at


@pytest.mark.parametrize("view", VIEWS)
def test_view_renders_without_exception(view: str) -> None:
    """Chaque page s'exécute de bout en bout sans exception."""
    at = _app()
    at.switch_page(f"views/{view}")
    at.run()
    assert not at.exception, _errors(at)
    assert len(at.main.children) > 0


@pytest.mark.parametrize("circuit", ["ATP", "WTA"])
def test_views_render_for_each_circuit(circuit: str) -> None:
    """Le choix du circuit (commun aux pages) ne casse aucune page."""
    at = _app()
    at.session_state["circuit"] = circuit
    for view in VIEWS:
        at.switch_page(f"views/{view}")
        at.run()
        assert not at.exception, f"{view} ({circuit}) :\n{_errors(at)}"


def test_old_top20_url_redirects_to_rankings() -> None:
    """L'ancienne page « Top 20 » redirige vers les classements (favoris préservés)."""
    at = _app()
    at.switch_page("views/redirect_top20.py")
    at.run()
    assert not at.exception, _errors(at)
    assert any("Classements Elo" in t.value for t in at.title)
