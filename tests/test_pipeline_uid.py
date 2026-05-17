"""Tests d'unicité de match_uid et garanties de non-collision."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from transformation.pipeline import build_processed_tables


def test_match_uid_unique_after_pipeline(tmp_path: Path) -> None:
    """match_uid doit être unique même avec des winner_id/loser_id ambigus."""
    interim = tmp_path / "data" / "interim"
    interim.mkdir(parents=True)

    # Cas piège : ids '1_2' vs '12_' qui collisionneraient avec un séparateur '_'
    matches = pd.DataFrame(
        {
            "winner_id": [1, 12, 1, 1],
            "loser_id": [2, 0, 2, 2],
            "tourney_date": [20200101, 20200101, 20200101, 20200102],
            "surface": ["Hard", "Hard", "Hard", "Hard"],
            "circuit": ["ATP", "ATP", "ATP", "ATP"],
            "round": ["R32", "R32", "R16", "R32"],
        }
    )
    matches.to_parquet(interim / "atp_matches_2020.parquet", index=False)

    build_processed_tables(tmp_path)
    out = pd.read_parquet(tmp_path / "data" / "processed" / "matches.parquet")

    assert out["match_uid"].is_unique
    assert len(out) == 4


def test_match_uid_handles_missing_round_column(tmp_path: Path) -> None:
    """Pipeline doit tolérer un parquet sans colonne 'round' (cas test_transformation)."""
    interim = tmp_path / "data" / "interim"
    interim.mkdir(parents=True)

    matches = pd.DataFrame(
        {
            "winner_id": [1],
            "loser_id": [2],
            "tourney_date": [20100101],
            "surface": ["Hard"],
            "circuit": ["ATP"],
        }
    )
    matches.to_parquet(interim / "atp_matches_2010.parquet", index=False)

    build_processed_tables(tmp_path)
    out = pd.read_parquet(tmp_path / "data" / "processed" / "matches.parquet")
    assert "match_uid" in out.columns
    assert out["match_uid"].is_unique
