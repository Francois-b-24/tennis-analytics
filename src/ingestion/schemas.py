"""Schémas Pandera pour valider les extractions Sackmann (matchs, joueurs, classements)."""

from __future__ import annotations

import pandera as pa
from pandera.typing import Series

DATE_INT = pa.Int64


class MatchesSchema(pa.DataFrameModel):
    """Schéma minimal des matchs Sackmann (colonnes strictes + extras autorisées)."""

    winner_id: Series[DATE_INT] = pa.Field(coerce=True, nullable=False)
    loser_id: Series[DATE_INT] = pa.Field(coerce=True, nullable=False)
    tourney_date: Series[DATE_INT] = pa.Field(coerce=True, nullable=False)
    surface: Series[str] = pa.Field(coerce=True, nullable=True)

    class Config:
        coerce = True
        strict = False
        add_missing_columns = False


class PlayersSchema(pa.DataFrameModel):
    """Schéma minimal des joueurs."""

    player_id: Series[DATE_INT] = pa.Field(coerce=True, nullable=False)

    class Config:
        coerce = True
        strict = False


class RankingsSchema(pa.DataFrameModel):
    """Schéma minimal des classements."""

    ranking_date: Series[DATE_INT] = pa.Field(coerce=True, nullable=False)
    player: Series[DATE_INT] = pa.Field(coerce=True, nullable=False)

    class Config:
        coerce = True
        strict = False
