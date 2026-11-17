"""Variables d'inférence (page Prédictions) : cohérence avec l'entraînement."""

from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd
import pytest

from tennis_analytics.modeling.inference import head_to_head, matchup_features, player_context
from tennis_analytics.modeling.win_probability import FEATURE_COLUMNS, rank_gap


def test_rank_gap_is_log_scaled_and_antisymmetric() -> None:
    assert rank_gap(1, 2) == pytest.approx(-rank_gap(2, 1))
    assert rank_gap(50, 100) == pytest.approx(rank_gap(1, 2))
    assert rank_gap(1, 10) > 0  # A mieux classé → positif
    assert rank_gap(None, 10) == 0.0
    assert rank_gap(float("nan"), 3) == 0.0


@pytest.fixture()
def conn() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    matches = pd.DataFrame(
        {
            "winner_id": [1, 1, 2, 1],
            "loser_id": [2, 3, 1, 3],
            "tourney_date": [20260101, 20260201, 20260301, 20260401],
            "round": ["F", "F", "F", "SF"],
            "surface_norm": ["hard", "hard", "clay", "hard"],
        }
    )
    connection.register("m", matches)
    connection.execute("CREATE VIEW v_matches AS SELECT * FROM m")
    connection.register(
        "e",
        pd.DataFrame(
            {
                "player_id": [1, 2],
                "elo_global": [1800.0, 1700.0],
                "elo_hard": [1850.0, 1650.0],
                "elo_clay": [1700.0, 1750.0],
                "elo_grass": [1600.0, 1600.0],
                "last_match_date": [20260401, 20200101],
            }
        ),
    )
    connection.execute("CREATE VIEW v_elo_latest AS SELECT * FROM e")
    connection.register("p", pd.DataFrame({"player_id": [1, 2], "dob": [20000101.0, None]}))
    connection.execute("CREATE VIEW v_players AS SELECT * FROM p")
    connection.register(
        "r",
        pd.DataFrame({"player": [1, 2], "rank": [3, 40], "ranking_date": [20260406, 20260406]}),
    )
    connection.execute("CREATE VIEW v_rankings AS SELECT * FROM r")
    return connection


def test_player_context_and_features(conn: duckdb.DuckDBPyConnection) -> None:
    today = date(2026, 4, 10)
    a = player_context(conn, 1, "hard", today)
    b = player_context(conn, 2, "hard", today)
    assert a.elo_surface == 1850.0  # actif : pas de décroissance
    assert 1500 < b.elo_surface < 1650  # inactif depuis 2020 : ramené vers 1500
    assert a.surface_winrate == 1.0 and a.surface_matches == 3
    assert a.age == 26 and b.age == 27  # âge inconnu → valeur neutre
    assert head_to_head(conn, 1, 2) == (1, 1)
    features = matchup_features(a, b, head_to_head(conn, 1, 2))
    assert list(features) == FEATURE_COLUMNS
    assert features["diff_rank"] > 0
    assert features["h2h_ratio"] == 0.5
    # Symétrie : inverser A et B inverse les écarts.
    reverse = matchup_features(b, a, head_to_head(conn, 2, 1))
    for name in FEATURE_COLUMNS:
        if name != "h2h_ratio":
            assert reverse[name] == pytest.approx(-features[name])
