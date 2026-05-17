"""Schémas Pandera pour valider les extractions Sackmann (matchs, joueurs, classements)."""

from __future__ import annotations

import pandera as pa
from pandera.typing import Series

# YYYYMMDD : 8 chiffres entiers (utilisés partout côté Sackmann)
DATE_INT = pa.Int64
MIN_DATE = 20100101  # filtre métier post-2010 (cf. sackmann_loader._filter_from_2010)
MAX_DATE = 20991231

VALID_SURFACES = {"Hard", "Clay", "Grass", "Carpet", "hard", "clay", "grass", "carpet"}


VALID_CIRCUITS = {"ATP", "WTA"}


class MatchesSchema(pa.DataFrameModel):
    """Schéma des matchs Sackmann post-filtre 2010."""

    winner_id: Series[DATE_INT] = pa.Field(coerce=True, nullable=False, ge=1)
    loser_id: Series[DATE_INT] = pa.Field(coerce=True, nullable=False, ge=1)
    tourney_date: Series[DATE_INT] = pa.Field(coerce=True, nullable=False, ge=MIN_DATE, le=MAX_DATE)
    surface: Series[str] = pa.Field(
        coerce=True,
        nullable=True,
        isin=VALID_SURFACES,
    )
    circuit: Series[str] = pa.Field(coerce=True, nullable=False, isin=VALID_CIRCUITS)

    class Config:
        coerce = True
        # On accepte les colonnes extras de Sackmann (best_of, score, etc.) sans
        # les filtrer — sinon on perdrait round, minutes, w_ace, etc.
        strict = False
        add_missing_columns = False


class PlayersSchema(pa.DataFrameModel):
    """Schéma des joueurs (player_id obligatoire et positif)."""

    player_id: Series[DATE_INT] = pa.Field(coerce=True, nullable=False, ge=1)
    circuit: Series[str] = pa.Field(coerce=True, nullable=False, isin=VALID_CIRCUITS)

    class Config:
        coerce = True
        strict = False


class RankingsSchema(pa.DataFrameModel):
    """Schéma des classements ATP/WTA."""

    ranking_date: Series[DATE_INT] = pa.Field(coerce=True, nullable=False, ge=MIN_DATE, le=MAX_DATE)
    player: Series[DATE_INT] = pa.Field(coerce=True, nullable=False, ge=1)
    circuit: Series[str] = pa.Field(coerce=True, nullable=False, isin=VALID_CIRCUITS)

    class Config:
        coerce = True
        strict = False
