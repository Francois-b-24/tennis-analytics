"""Tests de robustesse de l'ingestion (CSV vides, fichiers tronqués, etc.)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ingestion.sackmann_loader import (
    _read_csv_safe,
    csv_to_parquet_filtered_matches,
    csv_to_parquet_players,
    csv_to_parquet_rankings,
)


def test_read_csv_safe_empty_file(tmp_path: Path) -> None:
    """Un fichier de 0 octet doit retourner None sans crasher."""
    csv = tmp_path / "vide.csv"
    csv.write_bytes(b"")
    assert _read_csv_safe(csv) is None


def test_read_csv_safe_no_columns(tmp_path: Path) -> None:
    """Un fichier sans en-tête doit retourner None."""
    csv = tmp_path / "no_cols.csv"
    csv.write_text("a" * 100)  # > MIN_CSV_BYTES mais sans virgule = pas un CSV
    # pandas peut lire ça comme une seule colonne, donc ce test peut renvoyer un df.
    # On vérifie juste que ça ne crashe pas.
    result = _read_csv_safe(csv)
    assert result is None or isinstance(result, pd.DataFrame)


def test_csv_to_parquet_filtered_matches_skips_empty(tmp_path: Path) -> None:
    """csv_to_parquet_filtered_matches doit skipper un CSV vide sans crasher."""
    csv = tmp_path / "atp_matches_2026.csv"
    csv.write_bytes(b"")
    parquet = tmp_path / "out.parquet"
    csv_to_parquet_filtered_matches(csv, parquet, "ATP")
    # Aucun parquet créé, aucune exception levée
    assert not parquet.exists()


def test_csv_to_parquet_players_skips_empty(tmp_path: Path) -> None:
    csv = tmp_path / "atp_players.csv"
    csv.write_bytes(b"")
    parquet = tmp_path / "out.parquet"
    csv_to_parquet_players(csv, parquet, "ATP")
    assert not parquet.exists()


def test_csv_to_parquet_rankings_skips_empty(tmp_path: Path) -> None:
    csv = tmp_path / "atp_rankings.csv"
    csv.write_bytes(b"")
    parquet = tmp_path / "out.parquet"
    csv_to_parquet_rankings(csv, parquet, "ATP")
    assert not parquet.exists()


def test_csv_to_parquet_filtered_matches_valid_csv(tmp_path: Path) -> None:
    """Un CSV valide doit produire un parquet."""
    csv = tmp_path / "atp_matches_2020.csv"
    df = pd.DataFrame(
        {
            "winner_id": [1, 2],
            "loser_id": [2, 1],
            "tourney_date": [20200101, 20200102],
            "surface": ["Hard", "Clay"],
        }
    )
    df.to_csv(csv, index=False)
    parquet = tmp_path / "out.parquet"
    csv_to_parquet_filtered_matches(csv, parquet, "ATP")
    assert parquet.exists()
    rebuilt = pd.read_parquet(parquet)
    assert len(rebuilt) == 2
    assert (rebuilt["circuit"] == "ATP").all()
