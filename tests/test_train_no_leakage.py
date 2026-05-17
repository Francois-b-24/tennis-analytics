"""Vérifie que le fallback random_split (leakage temporel) a été supprimé."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def test_train_and_persist_raises_on_small_data(tmp_path: Path) -> None:
    """Avec des données insuffisantes, le pipeline ML doit lever ValueError
    (et NON pas retomber sur un train_test_split aléatoire qui causerait du leakage)."""
    from modeling.win_probability import train_and_persist

    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)

    matches = pd.DataFrame(
        {
            "winner_id": [1, 2],
            "loser_id": [2, 1],
            "tourney_date": [20100101, 20100102],
            "surface_norm": ["hard", "hard"],
            "match_uid": ["m1", "m2"],
        }
    )
    matches.to_parquet(processed / "matches.parquet", index=False)

    context = pd.DataFrame(
        {
            "match_uid": ["m1", "m2"],
            "tourney_date": [20100101, 20100102],
            "winner_id": [1, 2],
            "loser_id": [2, 1],
            "w_elo_g_pre": [1500.0, 1510.0],
            "l_elo_g_pre": [1500.0, 1490.0],
            "w_elo_surf_pre": [1500.0, 1510.0],
            "l_elo_surf_pre": [1500.0, 1490.0],
        }
    )
    context.to_parquet(processed / "match_elo_context.parquet", index=False)

    with pytest.raises(ValueError, match="leakage"):
        train_and_persist(tmp_path, split_date=20240101)
