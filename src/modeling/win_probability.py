"""Probabilité de victoire match : features, régression logistique et calibration isotonique."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.model_selection import train_test_split


@dataclass(slots=True)
class BacktestMetrics:
    """Métriques d'évaluation sur jeu de test temporel."""

    brier: float
    log_loss: float
    accuracy: float
    n_samples: int


def _merge_matches_context(matches: pd.DataFrame, match_context: pd.DataFrame) -> pd.DataFrame:
    """Joint les matchs et le contexte Elo sur des clés robustes."""
    if (
        "match_uid" in matches.columns
        and "match_uid" in match_context.columns
        and match_context["match_uid"].notna().any()
    ):
        return matches.merge(match_context, on="match_uid", how="inner", suffixes=("", "_ctx"))
    return matches.merge(
        match_context,
        on=["tourney_date", "winner_id", "loser_id"],
        how="inner",
        suffixes=("", "_ctx"),
    )


def _surface_from_row(row: Any) -> str:
    for attr in ("surface_norm_ctx", "surface_norm"):
        if hasattr(row, attr):
            value = getattr(row, attr)
            if value is not None and not (isinstance(value, float) and np.isnan(value)):
                return str(value)
    return "hard"


def _age_from_dob(dob_value: object, season_year: int) -> float:
    """Estime l'âge approximatif à partir d'une date de naissance Sackmann."""
    if dob_value is None or (isinstance(dob_value, float) and np.isnan(dob_value)):
        return 27.0
    token = str(dob_value).split(".")[0]
    if len(token) < 4:
        return 27.0
    try:
        birth_year = int(token[:4])
    except ValueError:
        return 27.0
    return float(season_year - birth_year)


def assemble_training_frame(
    matches: pd.DataFrame,
    match_context: pd.DataFrame,
    players: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Construit le jeu de données tabulaire pour entraîner le modèle.

    Args:
        matches: Table `matches` enrichie (ordre chronologique recommandé).
        match_context: Sortie `compute_elo_from_matches` (Elo pré-match).
        players: Table `players` pour l'âge (optionnelle).

    Returns:
        DataFrame avec la cible `y_win` (1 si victoire du joueur A) et les features différentielles.
    """
    base = _merge_matches_context(matches, match_context)
    sort_cols = [c for c in ("tourney_date", "match_uid") if c in base.columns]
    base = base.sort_values(sort_cols or ["tourney_date"]).reset_index(drop=True)

    h2h: dict[tuple[int, int], list[int]] = {}
    surface_wins: dict[tuple[int, str], int] = {}
    surface_total: dict[tuple[int, str], int] = {}
    recent: dict[int, list[int]] = {}

    dob_map: dict[int, object] = {}
    if players is not None and not players.empty and "dob" in players.columns:
        for row in players.itertuples(index=False):
            dob_map[int(row.player_id)] = getattr(row, "dob", None)

    rows: list[dict[str, Any]] = []
    for row in base.itertuples(index=False):
        w_id = int(row.winner_id)
        l_id = int(row.loser_id)
        surface = _surface_from_row(row)
        date = int(row.tourney_date)
        season_year = date // 10000

        key_ordered = (min(w_id, l_id), max(w_id, l_id))
        prior = h2h.get(key_ordered, [])
        wins_w_vs_l = sum(1 for x in prior if x == w_id)
        total_h2h = len(prior)
        h2h_ratio_w = (wins_w_vs_l / total_h2h) if total_h2h > 0 else 0.5
        h2h_ratio_l = ((total_h2h - wins_w_vs_l) / total_h2h) if total_h2h > 0 else 0.5

        sw_w = surface_wins.get((w_id, surface), 0)
        st_w = surface_total.get((w_id, surface), 0)
        sw_l = surface_wins.get((l_id, surface), 0)
        st_l = surface_total.get((l_id, surface), 0)
        wr_w = sw_w / st_w if st_w > 0 else 0.5
        wr_l = sw_l / st_l if st_l > 0 else 0.5
        surface_winrate_diff = wr_w - wr_l

        form_w = recent.get(w_id, [])
        form_l = recent.get(l_id, [])
        recent_form_diff = (sum(form_w) / len(form_w) if form_w else 0.5) - (
            sum(form_l) / len(form_l) if form_l else 0.5
        )

        diff_elo_surface = float(row.w_elo_surf_pre - row.l_elo_surf_pre)
        diff_elo_global = float(row.w_elo_g_pre - row.l_elo_g_pre)

        diff_age = _age_from_dob(dob_map.get(w_id), season_year) - _age_from_dob(
            dob_map.get(l_id), season_year
        )
        diff_rank = 0.0

        rows.append(
            {
                "tourney_date": date,
                "player_a": w_id,
                "player_b": l_id,
                "y_win": 1,
                "diff_elo_surface": diff_elo_surface,
                "diff_elo_global": diff_elo_global,
                "diff_rank": diff_rank,
                "diff_age": diff_age,
                "h2h_ratio": h2h_ratio_w,
                "surface_winrate_diff": surface_winrate_diff,
                "recent_form_diff": recent_form_diff,
            }
        )

        rows.append(
            {
                "tourney_date": date,
                "player_a": l_id,
                "player_b": w_id,
                "y_win": 0,
                "diff_elo_surface": -diff_elo_surface,
                "diff_elo_global": -diff_elo_global,
                "diff_rank": -diff_rank,
                "diff_age": -diff_age,
                "h2h_ratio": h2h_ratio_l,
                "surface_winrate_diff": -surface_winrate_diff,
                "recent_form_diff": -recent_form_diff,
            }
        )

        prior.append(w_id)
        h2h[key_ordered] = prior

        surface_wins[(w_id, surface)] = sw_w + 1
        surface_total[(w_id, surface)] = st_w + 1
        surface_total[(l_id, surface)] = st_l + 1

        fw = recent.get(w_id, [])
        fw.append(1)
        recent[w_id] = fw[-10:]
        fl = recent.get(l_id, [])
        fl.append(0)
        recent[l_id] = fl[-10:]

    return pd.DataFrame(rows)


def train_calibrated_model(
    features: pd.DataFrame,
    target: pd.Series,
) -> CalibratedClassifierCV:
    """Entraîne une régression logistique calibrée (isotonique avec CV interne).

    Args:
        features: Matrice des variables explicatives.
        target: Cible binaire.

    Returns:
        Modèle scikit-learn calibré.
    """
    folds = 2
    base = LogisticRegression(max_iter=500, solver="lbfgs")
    calibrated = CalibratedClassifierCV(base, method="isotonic", cv=folds)
    calibrated.fit(features, target)
    return calibrated


def temporal_train_test_split(
    frame: pd.DataFrame,
    split_date: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Découpe temporelle simple sur `tourney_date`."""
    feature_cols = [
        "diff_elo_surface",
        "diff_elo_global",
        "diff_rank",
        "diff_age",
        "h2h_ratio",
        "surface_winrate_diff",
        "recent_form_diff",
    ]
    train = frame.loc[frame["tourney_date"] < split_date].copy()
    test = frame.loc[frame["tourney_date"] >= split_date].copy()
    return train[feature_cols], test[feature_cols], train["y_win"], test["y_win"]


def evaluate_backtest(
    model: CalibratedClassifierCV,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> BacktestMetrics:
    """Calcule Brier, log loss et exactitude."""
    proba = model.predict_proba(X_test)[:, 1]
    preds = (proba >= 0.5).astype(int)
    return BacktestMetrics(
        brier=float(brier_score_loss(y_test, proba)),
        log_loss=float(log_loss(y_test, proba)),
        accuracy=float(accuracy_score(y_test, preds)),
        n_samples=int(len(y_test)),
    )


def calibration_plot_data(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> tuple[np.ndarray, np.ndarray]:
    """Prépare les coordonnées pour une courbe de calibration Plotly."""
    prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy="uniform")
    return prob_pred, prob_true


def train_and_persist(
    project_root: Path,
    split_date: int = 20240101,
) -> tuple[BacktestMetrics, Path]:
    """Charge les tables traitées, entraîne le modèle et persiste `joblib` + métriques.

    Args:
        project_root: Racine du dépôt.
        split_date: Date de coupure train/test (YYYYMMDD).

    Returns:
        Tuple métriques et chemin du modèle sauvegardé.
    """
    processed = project_root / "data" / "processed"
    matches = pd.read_parquet(processed / "matches.parquet")
    context = pd.read_parquet(processed / "match_elo_context.parquet")
    players_path = processed / "players.parquet"
    players = pd.read_parquet(players_path) if players_path.exists() else None

    frame = assemble_training_frame(matches, context, players)
    if frame.empty:
        raise ValueError("Jeu d'entraînement vide : vérifiez les sources parquet.")

    feature_cols = [
        "diff_elo_surface",
        "diff_elo_global",
        "diff_rank",
        "diff_age",
        "h2h_ratio",
        "surface_winrate_diff",
        "recent_form_diff",
    ]

    X_train, X_test, y_train, y_test = temporal_train_test_split(frame, split_date)
    if len(X_test) < 10 or len(X_train) < 10:
        X = frame[feature_cols]
        y = frame["y_win"]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.25, random_state=42, stratify=y
        )

    model = train_calibrated_model(X_train, y_train)
    metrics = evaluate_backtest(model, X_test, y_test)

    out_dir = processed / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "logreg_calibrated.joblib"
    joblib.dump({"model": model, "features": feature_cols}, out_path)
    logger.info("Modèle sauvegardé : {}", out_path)
    return metrics, out_path
