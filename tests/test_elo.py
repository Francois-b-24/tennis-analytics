"""Tests unitaires du moteur Elo."""

from __future__ import annotations

import pandas as pd

from ratings.elo import EloEngine, adaptive_k, compute_elo_from_matches


def test_adaptive_k_steps() -> None:
    assert adaptive_k(0) == 40.0
    assert adaptive_k(29) == 40.0
    assert adaptive_k(30) == 20.0
    assert adaptive_k(99) == 20.0
    assert adaptive_k(100) == 10.0


def test_process_match_updates_winner_higher() -> None:
    engine = EloEngine()
    engine.process_match(1, 2, 20100101, "hard", 3)
    assert engine.players[1].elo_global > engine.players[2].elo_global


def test_bo5_increases_update_magnitude() -> None:
    engine_bo3 = EloEngine()
    engine_bo3.process_match(10, 11, 20100101, "hard", 3)
    delta_bo3 = engine_bo3.players[10].elo_global - 1500.0

    engine_bo5 = EloEngine()
    engine_bo5.process_match(10, 11, 20100102, "hard", 5)
    delta_bo5 = engine_bo5.players[10].elo_global - 1500.0
    assert abs(delta_bo5) > abs(delta_bo3)


def test_inactivity_decay_function() -> None:
    from datetime import datetime, timedelta

    from ratings.elo import _apply_inactivity_decay

    last_played = datetime(2010, 1, 1)
    today = last_played + timedelta(days=400)
    decayed = _apply_inactivity_decay(1650.0, last_played, today)
    assert decayed < 1650.0


def test_prepare_for_match_is_idempotent() -> None:
    """Deux appels consécutifs de prepare_for_match pour la même date ne doivent
    pas appliquer la décroissance d'inactivité deux fois (idempotence)."""
    engine = EloEngine()
    engine.process_match(1, 2, 20100101, "hard", 3)

    # 400 jours plus tard, sans match entre temps
    engine.prepare_for_match(1, 2, 20110206, "hard")
    elo_after_first = engine.players[1].elo_global

    # Second appel pour la même date : doit être un no-op
    engine.prepare_for_match(1, 2, 20110206, "hard")
    elo_after_second = engine.players[1].elo_global

    assert elo_after_first == elo_after_second


def test_compute_elo_outputs_shapes() -> None:
    matches = pd.DataFrame(
        {
            "winner_id": [1, 2],
            "loser_id": [2, 1],
            "tourney_date": [20100101, 20100201],
            "surface_norm": ["hard", "hard"],
            "best_of": [3, 3],
            "match_uid": ["m1", "m2"],
        }
    )
    history, latest, context = compute_elo_from_matches(matches)
    assert not history.empty
    assert not latest.empty
    assert len(context) == 2
