"""Point d'entrée CLI pour lancer l'ingestion complète."""

from __future__ import annotations

from ingestion.sackmann_loader import run_ingestion_pipeline


def main() -> None:
    """Lance le pipeline d'ingestion Sackmann."""
    run_ingestion_pipeline()


if __name__ == "__main__":
    main()
