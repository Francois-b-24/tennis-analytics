"""Sources récentes (tennis-data, ESPN) : conversion, rapprochement, dédoublonnage.

Tests hors ligne : fixtures synthétiques, aucun appel réseau.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tennis_analytics.ids import NEW_PLAYER_ID_START
from tennis_analytics.ingestion import espn_loader, tennis_data_loader
from tennis_analytics.ingestion.player_matching import PlayerMatcher, parse_initials_name
from tennis_analytics.ingestion.recent import drop_published_espn, weekly_rankings


@pytest.fixture
def matcher() -> PlayerMatcher:
    players = pd.DataFrame(
        [
            (1, "Taylor", "Fritz", "ATP"),
            (2, "Thiago Agustin", "Tirante", "ATP"),
            (3, "Juan Manuel", "Cerundolo", "ATP"),
            (4, "Francisco", "Cerundolo", "ATP"),
            (5, "Giovanni", "Mpetshi Perricard", "ATP"),
            (6, "Bu", "Yunchaokete", "ATP"),
            (7, "Old", "Fritz", "ATP"),
            (1_000_008, "Linda", "Noskova", "WTA"),
        ],
        columns=["player_id", "name_first", "name_last", "circuit"],
    )
    active = {1: 20261101, 2: 20261101, 3: 20261101, 4: 20261101, 5: 20261101}
    active.update({6: 20261101, 7: 20120101, 1_000_008: 20261101})
    return PlayerMatcher(
        players=players,
        last_active=active,
        aliases={("ATP", "fritzx"): 1},
        reference_date=20261117,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Tirante T.A.", ("Tirante", "t")),
        ("Tirante T. A.", ("Tirante", "t")),
        ("De Minaur A.", ("De Minaur", "a")),
        ("Zhang Zh.", ("Zhang", "z")),
    ],
)
def test_parse_initials_name(raw: str, expected: tuple[str, str]) -> None:
    assert parse_initials_name(raw) == expected


def test_matcher_variants(matcher: PlayerMatcher) -> None:
    assert matcher.resolve_initials("ATP", "Fritz T.").player_id == 1
    assert matcher.resolve_initials("ATP", "Tirante T. A.").player_id == 2
    assert matcher.resolve_initials("ATP", "Mpetshi G.").player_id == 5  # nom tronqué
    assert matcher.resolve_initials("ATP", "Bu Y.").player_id == 6  # ordre inversé
    assert matcher.resolve_initials("ATP", "Fritz X.").player_id == 1  # alias manuel
    assert matcher.resolve_full("ATP", "Juan Manuel Cerundolo").player_id == 3
    assert matcher.resolve_full("ATP", "Francisco Cerundolo").player_id == 4
    assert matcher.resolve_full("WTA", "Linda Noskova").player_id == 1_000_008


def test_unknown_player_gets_stable_new_id(matcher: PlayerMatcher) -> None:
    first = matcher.resolve_initials("ATP", "Jodar R.")
    again = matcher.resolve_full("ATP", "Rafael Jodar")
    assert first.is_new and again.is_new
    assert first.player_id == again.player_id
    assert NEW_PLAYER_ID_START["ATP"] <= first.player_id < NEW_PLAYER_ID_START["WTA"]
    frame = matcher.new_players_frame()
    assert frame.loc[frame["player_id"] == first.player_id, "name_first"].item() == "Rafael"


def test_inactive_homonym_is_not_matched(matcher: PlayerMatcher) -> None:
    # « Old Fritz » n'a plus joué depuis 2012 : un « Fritz O. » est un nouveau joueur.
    assert matcher.resolve_initials("ATP", "Fritz O.").is_new


def test_build_score_and_rounds() -> None:
    row = pd.Series({"W1": 6, "L1": 4, "W2": 3, "L2": "\t", "Comment": "Retired"})
    assert tennis_data_loader.build_score(row) == "6-4 RET"
    assert tennis_data_loader.build_score(pd.Series({"Comment": "Walkover"})) == "W/O"
    assert tennis_data_loader.round_code("1st Round", 64) == "R128"
    assert tennis_data_loader.round_code("Round 2", 12) == "R16"
    assert tennis_data_loader.round_code("The Final", 16) == "F"
    assert tennis_data_loader.round_code("Group Stage", 0) == "RR"


def test_monday_of_tournament() -> None:
    # Début un dimanche (Roland-Garros 2026) → lundi suivant, comme Sackmann.
    assert tennis_data_loader._monday_int(pd.Timestamp("2026-05-24")) == 20260525
    assert tennis_data_loader._monday_int(pd.Timestamp("2026-11-11")) == 20261109


def test_discover_files() -> None:
    html = '<a HREF="abc/2026/2026.xlsx">x</a><a href="abc/2026w/2026.xlsx">y</a>'
    files = tennis_data_loader.discover_files(html)
    assert [(f.circuit, f.year) for f in files] == [("ATP", 2026), ("WTA", 2026)]
    assert files[0].url.endswith("/abc/2026/2026.xlsx")


def _td_frame() -> pd.DataFrame:
    base = {
        "Location": "Stockholm",
        "Tournament": "Nordic Open",
        "Series": "ATP250",
        "Surface": "Hard",
        "Best of": 3,
        "WRank": 10,
        "LRank": 51,
        "WPts": 3285,
        "LPts": 1042,
        "Comment": "Completed",
    }
    return pd.DataFrame(
        [
            {
                **base,
                "Date": "2026-11-09",
                "Round": "1st Round",
                "Winner": "Fritz T.",
                "Loser": "Tirante T.A.",
                "W1": 6,
                "L1": 4,
                "W2": 6,
                "L2": 4,
            },
            {
                **base,
                "Date": "2026-11-14",
                "Round": "The Final",
                "Winner": "Fritz T.",
                "Loser": "Mpetshi G.",
                "W1": 7,
                "L1": 6,
                "W2": 6,
                "L2": 2,
            },
        ]
    )


def test_tennis_data_to_matches(matcher: PlayerMatcher) -> None:
    out = tennis_data_loader.to_matches(
        _td_frame(), "ATP", matcher, {("ATP", "Nordic Open"): "Stockholm"}, after_date=20260525
    )
    assert len(out) == 2
    assert set(out["tourney_name"]) == {"Stockholm"}
    assert out["tourney_date"].unique().tolist() == [20261109]
    assert out["round"].tolist() == ["R16", "F"]  # 1 seul match de 1er tour → tableau minimal
    assert out.loc[1, "winner_id"] == 1 and out.loc[1, "loser_id"] == 5
    assert out["w_ace"].isna().all()
    # Tournois déjà couverts par l'archive : ignorés.
    assert tennis_data_loader.to_matches(_td_frame(), "ATP", matcher, {}, 20261201).empty


def _espn_event() -> dict:
    def comp(round_name: str, slug: str, status: str, winner: str, loser: str) -> dict:
        return {
            "date": "2026-11-16T13:00Z",
            "type": {"slug": slug},
            "round": {"displayName": round_name},
            "status": {"type": {"completed": status != "STATUS_SCHEDULED", "name": status}},
            "venue": {"fullName": "Stockholm, Sweden"},
            "format": {"regulation": {"periods": 3}},
            "competitors": [
                {
                    "winner": True,
                    "athlete": {"displayName": winner},
                    "linescores": [{"value": 6}, {"value": 7, "tiebreak": 5}],
                },
                {
                    "winner": False,
                    "athlete": {"displayName": loser},
                    "linescores": [{"value": 3}, {"value": 6}],
                },
            ],
        }

    return {
        "name": "Bybit Stockholm Open",
        "groupings": [
            {
                "competitions": [
                    comp("Round 1", "mens-singles", "STATUS_FINAL", "Taylor Fritz", "Rafael Jodar"),
                    comp("Qualifying Final", "mens-singles", "STATUS_FINAL", "A B", "C D"),
                    comp("Round 1", "womens-singles", "STATUS_FINAL", "X Y", "Z W"),
                    comp("Round 2", "mens-singles", "STATUS_SCHEDULED", "Taylor Fritz", "E F"),
                ]
            }
        ],
    }


def test_espn_to_matches(matcher: PlayerMatcher) -> None:
    refs = pd.DataFrame(
        [
            {
                "circuit": "ATP",
                "city_norm": "stockholm",
                "tourney_name": "Stockholm",
                "surface": "Hard",
                "tourney_level": "A",
                "start": pd.Timestamp("2025-11-10"),
            }
        ]
    )
    out = espn_loader.to_matches(
        {"ATP": [_espn_event()], "WTA": []}, matcher, refs, {"ATP": 20260525, "WTA": 0}
    )
    assert len(out) == 1  # qualifs, simple dames et match à venir exclus
    row = out.iloc[0]
    assert row["score"] == "6-3 7-6(5)"
    assert row["source"] == "espn" and row["tourney_name"] == "Stockholm"
    assert row["winner_id"] == 1


def test_espn_rows_already_published_are_dropped() -> None:
    frame = pd.DataFrame(
        {
            "circuit": ["ATP", "ATP", "ATP"],
            "winner_id": [1, 2, 9],
            "loser_id": [2, 1, 8],
            "match_date": [20261114, 20261115, 20261116],
            "source": ["tennis-data", "espn", "espn"],
        }
    )
    out = drop_published_espn(frame)
    assert out["source"].tolist() == ["tennis-data", "espn"]
    assert out["winner_id"].tolist() == [1, 9]


def test_weekly_rankings_keep_latest_rank_of_week() -> None:
    frame = pd.DataFrame(
        {
            "circuit": ["ATP", "ATP"],
            "match_date": [20261110, 20261113],
            "winner_id": [1, 1],
            "loser_id": [2, 3],
            "winner_rank": [12.0, 10.0],
            "winner_rank_points": [3000.0, 3285.0],
            "loser_rank": [40.0, 50.0],
            "loser_rank_points": [1.0, 1.0],
        }
    )
    out = weekly_rankings(frame)
    assert out.loc[out["player"] == 1, "rank"].tolist() == [10]
    assert out["ranking_date"].unique().tolist() == [20261109]
