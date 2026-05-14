"""Entraîne et persiste le modèle de probabilité de victoire."""

from __future__ import annotations

from loguru import logger

from ingestion.sackmann_loader import get_project_root
from modeling.win_probability import train_and_persist


def main() -> None:
    """Entraîne le modèle si les données préparées sont disponibles."""
    root = get_project_root()
    metrics, path = train_and_persist(root)
    logger.info(
        "Backtest — Brier={:.4f}, log loss={:.4f}, exactitude={:.3f}, n={}",
        metrics.brier,
        metrics.log_loss,
        metrics.accuracy,
        metrics.n_samples,
    )
    logger.info("Artefact : {}", path)


if __name__ == "__main__":
    main()
