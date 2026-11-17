"""Identifiants joueurs globalement uniques (ATP et WTA).

Les identifiants Sackmann ATP et WTA se chevauchent (ATP > 200 000 depuis
2020, WTA entre 200 000 et 270 000) : un même entier peut désigner Paula Badosa
(WTA) et Alexander Vasilev (ATP). Pour que tout le code indexé par `player_id`
(moteur Elo, features, pages) reste correct sans clé composite, on décale les
identifiants WTA et on réserve des plages pour les joueurs découverts via les
sources récentes (tennis-data, ESPN).
"""

from __future__ import annotations

from typing import Final

import pandas as pd

#: Décalage appliqué aux identifiants WTA Sackmann.
WTA_ID_OFFSET: Final[int] = 1_000_000

#: Première valeur des identifiants attribués aux nouveaux joueurs, par circuit.
NEW_PLAYER_ID_START: Final[dict[str, int]] = {"ATP": 2_000_000, "WTA": 3_000_000}


def offset_for(circuit: str) -> int:
    """Décalage d'identifiant pour un circuit Sackmann ('ATP' ou 'WTA')."""
    return WTA_ID_OFFSET if circuit == "WTA" else 0


def globalize_ids(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    """Applique le décalage WTA aux colonnes d'identifiants d'une table Sackmann.

    Idempotent : une valeur déjà décalée (≥ `WTA_ID_OFFSET`) n'est pas re-décalée.

    Args:
        frame: Table contenant une colonne `circuit`.
        columns: Colonnes d'identifiants à décaler (ex. `winner_id`, `loser_id`).

    Returns:
        Copie de la table avec des identifiants globalement uniques.
    """
    out = frame.copy()
    is_wta = out["circuit"] == "WTA"
    for col in columns:
        if col not in out.columns:
            continue
        values = pd.to_numeric(out[col], errors="coerce").astype("Int64")
        needs = is_wta & (values < WTA_ID_OFFSET)
        out[col] = values.where(~needs, values + WTA_ID_OFFSET)
    return out
