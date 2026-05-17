"""Tests des schémas pandera (validation stricte des données ingérées)."""

from __future__ import annotations

import pandas as pd
import pandera as pa
import pytest

from ingestion.schemas import MatchesSchema, PlayersSchema, RankingsSchema


def test_matches_schema_accepts_valid_row() -> None:
    df = pd.DataFrame(
        {
            "winner_id": [1],
            "loser_id": [2],
            "tourney_date": [20100101],
            "surface": ["Hard"],
            "circuit": ["ATP"],
        }
    )
    validated = MatchesSchema.validate(df)
    assert len(validated) == 1


def test_matches_schema_rejects_old_date() -> None:
    """Le filtre métier impose tourney_date >= 20100101."""
    df = pd.DataFrame(
        {
            "winner_id": [1],
            "loser_id": [2],
            "tourney_date": [20091231],
            "surface": ["Hard"],
            "circuit": ["ATP"],
        }
    )
    with pytest.raises(pa.errors.SchemaError):
        MatchesSchema.validate(df)


def test_matches_schema_rejects_unknown_surface() -> None:
    df = pd.DataFrame(
        {
            "winner_id": [1],
            "loser_id": [2],
            "tourney_date": [20200101],
            "surface": ["Sand"],
            "circuit": ["ATP"],
        }
    )
    with pytest.raises(pa.errors.SchemaError):
        MatchesSchema.validate(df)


def test_matches_schema_rejects_negative_player_id() -> None:
    df = pd.DataFrame(
        {
            "winner_id": [-1],
            "loser_id": [2],
            "tourney_date": [20200101],
            "surface": ["Hard"],
            "circuit": ["ATP"],
        }
    )
    with pytest.raises(pa.errors.SchemaError):
        MatchesSchema.validate(df)


def test_matches_schema_rejects_unknown_circuit() -> None:
    df = pd.DataFrame(
        {
            "winner_id": [1],
            "loser_id": [2],
            "tourney_date": [20200101],
            "surface": ["Hard"],
            "circuit": ["XYZ"],
        }
    )
    with pytest.raises(pa.errors.SchemaError):
        MatchesSchema.validate(df)


def test_players_schema_accepts_valid() -> None:
    df = pd.DataFrame({"player_id": [1, 2, 3], "circuit": ["ATP", "ATP", "WTA"]})
    assert len(PlayersSchema.validate(df)) == 3


def test_rankings_schema_accepts_valid() -> None:
    df = pd.DataFrame({"ranking_date": [20200101], "player": [1], "circuit": ["ATP"]})
    assert len(RankingsSchema.validate(df)) == 1
