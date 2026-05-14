"""Tests du pipeline de transformation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from transformation.pipeline import build_processed_tables


def test_build_processed_tables_writes_parquet(tmp_path: Path) -> None:
    interim = tmp_path / "data" / "interim"
    processed = tmp_path / "data" / "processed"
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
    output = processed / "matches.parquet"
    assert output.exists()
    rebuilt = pd.read_parquet(output)
    assert "surface_norm" in rebuilt.columns
    assert "match_uid" in rebuilt.columns
