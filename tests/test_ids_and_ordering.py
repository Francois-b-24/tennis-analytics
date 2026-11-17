"""Identifiants globaux, ordre chronologique et règles de cache Streamlit."""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd

from tennis_analytics.ids import WTA_ID_OFFSET, globalize_ids
from tennis_analytics.ratings.elo import compute_elo_from_matches
from tennis_analytics.transformation.ordering import sort_chronologically

ROOT = Path(__file__).resolve().parents[1]


def test_globalize_ids_separates_circuits_and_is_idempotent() -> None:
    frame = pd.DataFrame(
        {"circuit": ["ATP", "WTA"], "winner_id": [211651, 211651], "loser_id": [1, 2]}
    )
    once = globalize_ids(frame, ("winner_id", "loser_id"))
    assert once["winner_id"].tolist() == [211651, 211651 + WTA_ID_OFFSET]
    twice = globalize_ids(once, ("winner_id", "loser_id"))
    assert twice["winner_id"].tolist() == once["winner_id"].tolist()


def _tournament(final_first: bool) -> pd.DataFrame:
    rows = [
        # La finale a un winner_id plus petit : l'ancien tri la plaçait en tête.
        {"round": "F", "winner_id": 1, "loser_id": 3, "match_num": 3},
        {"round": "SF", "winner_id": 1, "loser_id": 2, "match_num": 1},
        {"round": "SF", "winner_id": 3, "loser_id": 4, "match_num": 2},
    ]
    if not final_first:
        rows = rows[1:] + rows[:1]
    frame = pd.DataFrame(rows)
    frame["tourney_date"] = 20240101
    frame["tourney_id"] = "2024-001"
    frame["surface_norm"] = "hard"
    frame["best_of"] = 3
    frame["match_uid"] = (
        "ATP§20240101§" + frame["winner_id"].astype(str) + "§" + frame["loser_id"].astype(str)
    )
    return frame


def test_rounds_are_processed_in_order() -> None:
    ordered = sort_chronologically(_tournament(final_first=True))
    assert ordered["round"].tolist() == ["SF", "SF", "F"]


def test_elo_pre_match_of_final_reflects_semifinals() -> None:
    _, latest, context = compute_elo_from_matches(_tournament(final_first=True))
    final = context.loc[(context["winner_id"] == 1) & (context["loser_id"] == 3)].iloc[0]
    # Les deux finalistes ont gagné leur demie : leur Elo pré-finale dépasse 1500.
    assert final["w_elo_g_pre"] > 1500
    assert final["l_elo_g_pre"] > 1500
    # Résultat identique quel que soit l'ordre d'entrée.
    _, latest_2, _ = compute_elo_from_matches(_tournament(final_first=False))
    pd.testing.assert_frame_equal(latest, latest_2)


def test_latest_is_final_state() -> None:
    history, latest, _ = compute_elo_from_matches(_tournament(final_first=True))
    champion = latest.loc[latest["player_id"] == 1, "elo_global"].iloc[0]
    assert champion == history.loc[history["player_id"] == 1, "elo_global"].iloc[-1]
    assert latest["player_id"].is_monotonic_increasing


def _cached_functions() -> list[tuple[Path, ast.FunctionDef]]:
    found = []
    for path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for deco in node.decorator_list:
                target = deco.func if isinstance(deco, ast.Call) else deco
                if isinstance(target, ast.Attribute) and target.attr == "cache_data":
                    found.append((path, node))
    return found


def test_cache_data_first_argument_is_hashed() -> None:
    """Streamlit ignore les arguments préfixés `_` : la clé de données serait perdue."""
    functions = _cached_functions()
    assert functions
    offenders = [
        f"{path.name}:{fn.name}"
        for path, fn in functions
        if fn.args.args and fn.args.args[0].arg.startswith("_")
    ]
    assert not offenders, offenders
