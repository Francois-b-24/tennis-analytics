"""Publication (manifest, garde-fous) et synchronisation côté app.

La synchronisation est testée hors ligne via des URL `file://`.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from tennis_analytics import publish

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from components._bootstrap import _download_release


@pytest.fixture()
def processed(tmp_path: Path) -> Path:
    folder = tmp_path / "processed"
    (folder / "models").mkdir(parents=True)
    pd.DataFrame({"match_uid": ["a", "b"]}).to_parquet(folder / "matches.parquet")
    pd.DataFrame({"player_id": [1]}).to_parquet(folder / "players.parquet")
    pd.DataFrame({"player": [1]}).to_parquet(folder / "rankings.parquet")
    (folder / "models" / "logreg_calibrated.joblib").write_bytes(b"model")
    (folder / "metadata.json").write_text(json.dumps({"last_match_date": {"ATP": 20261116}}))
    return folder


def test_manifest_describes_files(processed: Path) -> None:
    manifest = publish.build_manifest(processed)
    assert manifest["rows"] == {"matches": 2, "players": 1}
    assert "models/logreg_calibrated.joblib" in manifest["files"]
    assert manifest["last_match_date"] == {"ATP": 20261116}


def test_metadata_does_not_change_data_hash(processed: Path) -> None:
    before = publish.build_manifest(processed)["data_hash"]
    (processed / "metadata.json").write_text(json.dumps({"generated_at": "plus tard"}))
    assert publish.build_manifest(processed)["data_hash"] == before


def test_regressions() -> None:
    previous = {"rows": {"matches": 1000}, "last_match_date": {"ATP": 20261116}}
    ok = {"rows": {"matches": 995}, "last_match_date": {"ATP": 20261117}}
    assert publish.regressions(ok, previous) == []
    shrunk = {"rows": {"matches": 800}, "last_match_date": {"ATP": 20261117}}
    assert len(publish.regressions(shrunk, previous)) == 1
    backwards = {"rows": {"matches": 1000}, "last_match_date": {"ATP": 20261101}}
    assert len(publish.regressions(backwards, previous)) == 1
    assert publish.regressions(ok, None) == []


def test_staleness_and_off_season() -> None:
    assert publish.staleness({"ATP": 20261001}, date(2026, 11, 1)) is not None
    assert publish.staleness({"ATP": 20261030}, date(2026, 11, 1)) is None
    # Intersaison : aucune alerte même sans match depuis des semaines.
    assert publish.staleness({"ATP": 20261122}, date(2026, 12, 20)) is None


def _release(tmp_path: Path, processed: Path) -> tuple[str, dict]:
    """Simule une Release : fichiers à plat + manifest."""
    release = tmp_path / "release"
    release.mkdir()
    manifest = publish.build_manifest(processed)
    for rel in manifest["files"]:
        (release / Path(rel).name).write_bytes((processed / rel).read_bytes())
    return release.as_uri(), manifest


def test_download_release_verifies_and_reuses(tmp_path: Path, processed: Path) -> None:
    base_url, manifest = _release(tmp_path, processed)
    cache = tmp_path / "cache"
    cache.mkdir()
    folder = _download_release(base_url, manifest, cache)
    assert (folder / "models" / "logreg_calibrated.joblib").read_bytes() == b"model"
    assert (folder / ".complete").exists()
    # Seconde lecture : aucun téléchargement (même dossier).
    assert _download_release("file:///nulle-part", manifest, cache) == folder


def test_download_release_rejects_partial_publication(tmp_path: Path, processed: Path) -> None:
    base_url, manifest = _release(tmp_path, processed)
    (tmp_path / "release" / "matches.parquet").write_bytes(b"version en cours d'envoi")
    cache = tmp_path / "cache"
    cache.mkdir()
    with pytest.raises(ValueError, match="Empreinte"):
        _download_release(base_url, manifest, cache)
    assert list(cache.iterdir()) == []
