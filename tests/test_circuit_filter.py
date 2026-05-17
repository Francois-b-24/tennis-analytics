"""Tests de sécurité du filtre SQL circuit."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# app/ n'est pas un package : insérer dans sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from components.widgets import circuit_filter_sql


def test_circuit_filter_accepts_atp() -> None:
    assert circuit_filter_sql("ATP") == "AND circuit = 'ATP'"


def test_circuit_filter_accepts_wta() -> None:
    assert circuit_filter_sql("WTA") == "AND circuit = 'WTA'"


def test_circuit_filter_accepts_tous() -> None:
    assert circuit_filter_sql("Tous") == ""


def test_circuit_filter_rejects_injection() -> None:
    """Toute valeur hors allowlist doit lever ValueError (durcissement anti-injection)."""
    with pytest.raises(ValueError):
        circuit_filter_sql("'; DROP TABLE matches; --")


def test_circuit_filter_rejects_unknown_string() -> None:
    with pytest.raises(ValueError):
        circuit_filter_sql("FFT")
