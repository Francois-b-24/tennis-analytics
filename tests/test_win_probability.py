"""Tests du module de probabilité de victoire."""

from __future__ import annotations

import numpy as np
import pandas as pd

from modeling.win_probability import (
    assemble_training_frame,
    calibration_plot_data,
    evaluate_backtest,
    train_calibrated_model,
)


def test_assemble_training_frame_symmetry() -> None:
    matches = pd.DataFrame(
        {
            "winner_id": [1],
            "loser_id": [2],
            "tourney_date": [20100101],
            "surface_norm": ["hard"],
            "match_uid": ["m1"],
        }
    )
    context = pd.DataFrame(
        {
            "match_uid": ["m1"],
            "tourney_date": [20100101],
            "winner_id": [1],
            "loser_id": [2],
            "w_elo_g_pre": [1600.0],
            "l_elo_g_pre": [1500.0],
            "w_elo_surf_pre": [1580.0],
            "l_elo_surf_pre": [1520.0],
        }
    )
    frame = assemble_training_frame(matches, context, None)
    assert len(frame) == 2
    assert set(frame["y_win"]) == {0, 1}


def test_train_and_evaluate_small_dataset() -> None:
    rng = np.random.default_rng(42)
    rows = 20
    features = pd.DataFrame(
        {
            "diff_elo_surface": rng.normal(size=rows),
            "diff_elo_global": rng.normal(size=rows),
            "diff_rank": rng.normal(size=rows),
            "diff_age": rng.normal(size=rows),
            "h2h_ratio": rng.random(size=rows),
            "surface_winrate_diff": rng.normal(size=rows),
            "recent_form_diff": rng.normal(size=rows),
        }
    )
    target = pd.Series(rng.integers(0, 2, size=rows))
    model = train_calibrated_model(features, target)
    metrics = evaluate_backtest(model, features, target)
    assert metrics.n_samples == rows
    assert 0.0 <= metrics.brier <= 1.0


def test_calibration_plot_data_shapes() -> None:
    y = np.array([0, 1, 0, 1, 1, 0] * 5)
    p = np.linspace(0.1, 0.9, len(y))
    x_pred, y_true = calibration_plot_data(y, p, n_bins=5)
    assert len(x_pred) == len(y_true)
