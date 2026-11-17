"""Ordre chronologique des matchs, partagé par le moteur Elo et le modèle.

Sackmann date chaque match par le **début** du tournoi (`tourney_date`) : tous
les matchs d'un tournoi partagent la même date. Trier sur
`(tourney_date, match_uid)` revenait à départager par `winner_id`, si bien
qu'une finale pouvait être traitée avant le premier tour — fuite de résultats
futurs dans l'Elo « pré-match » et dans les features. On départage donc par
tournoi, puis par tour, puis par numéro de match.
"""

from __future__ import annotations

from typing import Final

import pandas as pd

#: Rang chronologique de chaque tour (qualifications → finale).
ROUND_ORDER: Final[dict[str, int]] = {
    "Q1": 0,
    "Q2": 1,
    "Q3": 2,
    "Q4": 3,
    "ER": 5,
    "R128": 10,
    "R64": 11,
    "R32": 12,
    "R16": 13,
    "RR": 14,
    "QF": 15,
    "SF": 16,
    "BR": 17,
    "F": 18,
}

_UNKNOWN_ROUND: Final[int] = 9


def round_order(rounds: pd.Series) -> pd.Series:
    """Convertit une colonne `round` en rang chronologique (entier)."""
    return rounds.map(ROUND_ORDER).fillna(_UNKNOWN_ROUND).astype("int64")


def sort_chronologically(frame: pd.DataFrame) -> pd.DataFrame:
    """Trie les matchs dans l'ordre où ils ont été joués.

    Clés (si présentes) : `tourney_date`, `match_date`, `tourney_id`, tour,
    `match_num`, `match_uid`. Le tri est stable : deux exécutions sur les mêmes
    données produisent exactement le même ordre (et donc les mêmes Elo).

    Args:
        frame: Table de matchs.

    Returns:
        Copie triée, index réinitialisé.
    """
    out = frame.copy()
    keys: list[str] = []
    for col in ("tourney_date", "tourney_id"):
        if col in out.columns:
            keys.append(col)
    if "round" in out.columns:
        out["_round_order"] = round_order(out["round"])
        keys.append("_round_order")
    for col in ("match_date", "match_num", "match_uid"):
        if col in out.columns:
            keys.append(col)
    if not keys:
        return out.reset_index(drop=True)
    out = out.sort_values(keys, kind="mergesort", na_position="last").reset_index(drop=True)
    return out.drop(columns=["_round_order"], errors="ignore")
