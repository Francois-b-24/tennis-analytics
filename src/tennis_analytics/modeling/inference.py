"""Variables d'entrée du modèle pour une confrontation à venir (inférence).

Mêmes définitions qu'à l'entraînement (:func:`assemble_training_frame`) :
écarts d'Elo (surface et global), d'âge, de classement, ratio des
confrontations directes, écart de taux de victoire sur la surface et de forme
récente (10 derniers matchs). Isolé ici pour être testé et partagé, plutôt
que recopié dans la page Streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

import duckdb

#: Colonne Elo selon la surface normalisée.
SURFACE_ELO: Final[dict[str, str]] = {
    "hard": "elo_hard",
    "clay": "elo_clay",
    "grass": "elo_grass",
}

#: Valeurs neutres quand une information manque.
DEFAULT_ELO: Final[float] = 1500.0
DEFAULT_AGE: Final[float] = 27.0
RECENT_FORM_WINDOW: Final[int] = 10

#: Ordre des tours (départage les matchs d'un même tournoi).
_ROUND_ORDER_SQL: Final[str] = """
    CASE round WHEN 'F' THEN 18 WHEN 'BR' THEN 17 WHEN 'SF' THEN 16 WHEN 'QF' THEN 15
         WHEN 'RR' THEN 14 WHEN 'R16' THEN 13 WHEN 'R32' THEN 12 WHEN 'R64' THEN 11
         WHEN 'R128' THEN 10 ELSE 9 END
"""


@dataclass(frozen=True, slots=True)
class PlayerContext:
    """Informations d'un joueur utiles à la prédiction."""

    elo_surface: float
    elo_global: float
    age: float
    rank: float | None
    surface_winrate: float
    surface_matches: int
    recent_form: float


def _scalar(conn: duckdb.DuckDBPyConnection, sql: str, params: list) -> object:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def player_context(
    conn: duckdb.DuckDBPyConnection,
    player_id: int,
    surface_norm: str,
    today: date | None = None,
) -> PlayerContext:
    """Rassemble Elo, âge, classement, réussite sur la surface et forme d'un joueur."""
    today = today or date.today()
    elo_col = SURFACE_ELO.get(surface_norm, "elo_global")
    elo = conn.execute(
        f"SELECT {elo_col}, elo_global FROM v_elo_latest WHERE player_id = ?", [player_id]
    ).fetchone()
    elo_surface = float(elo[0]) if elo and elo[0] is not None else DEFAULT_ELO
    elo_global = float(elo[1]) if elo and elo[1] is not None else DEFAULT_ELO

    dob = _scalar(conn, "SELECT dob FROM v_players WHERE player_id = ?", [player_id])
    try:
        age = float(today.year - int(str(int(float(dob)))[:4])) if dob else DEFAULT_AGE
    except (TypeError, ValueError):
        age = DEFAULT_AGE

    rank = _scalar(
        conn,
        "SELECT arg_max(rank, ranking_date) FROM v_rankings WHERE player = ?",
        [player_id],
    )
    surface = conn.execute(
        """
        SELECT SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END), COUNT(*)
        FROM v_matches WHERE surface_norm = ? AND (winner_id = ? OR loser_id = ?)
        """,
        [player_id, surface_norm, player_id, player_id],
    ).fetchone()
    surface_matches = int(surface[1] or 0) if surface else 0
    surface_winrate = float(surface[0]) / surface_matches if surface_matches else 0.5

    recent = conn.execute(
        f"""
        SELECT AVG(CASE WHEN winner_id = ? THEN 1.0 ELSE 0.0 END) FROM (
            SELECT winner_id FROM v_matches WHERE winner_id = ? OR loser_id = ?
            ORDER BY tourney_date DESC, {_ROUND_ORDER_SQL} DESC
            LIMIT {RECENT_FORM_WINDOW}
        )
        """,
        [player_id, player_id, player_id],
    ).fetchone()
    form = float(recent[0]) if recent and recent[0] is not None else 0.5

    return PlayerContext(
        elo_surface=elo_surface,
        elo_global=elo_global,
        age=age,
        rank=float(rank) if rank is not None else None,
        surface_winrate=surface_winrate,
        surface_matches=surface_matches,
        recent_form=form,
    )


def head_to_head(conn: duckdb.DuckDBPyConnection, player_a: int, player_b: int) -> tuple[int, int]:
    """Victoires de A et de B dans leurs confrontations directes."""
    row = conn.execute(
        """
        SELECT SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END),
               SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END)
        FROM v_matches
        WHERE (winner_id = ? AND loser_id = ?) OR (winner_id = ? AND loser_id = ?)
        """,
        [player_a, player_b, player_a, player_b, player_b, player_a],
    ).fetchone()
    return (int(row[0] or 0), int(row[1] or 0)) if row else (0, 0)


def matchup_features(a: PlayerContext, b: PlayerContext, h2h: tuple[int, int]) -> dict[str, float]:
    """Variables du modèle pour « A bat B » (écarts A - B).

    Le classement n'est utilisé que si les deux joueurs en ont un (sinon 0,
    valeur neutre).
    """
    wins_a, wins_b = h2h
    total = wins_a + wins_b
    diff_rank = 0.0
    if a.rank is not None and b.rank is not None:
        # Un meilleur classement est un nombre plus petit : écart B - A positif
        # quand A est mieux classé.
        diff_rank = b.rank - a.rank
    return {
        "diff_elo_surface": a.elo_surface - b.elo_surface,
        "diff_elo_global": a.elo_global - b.elo_global,
        "diff_rank": diff_rank,
        "diff_age": a.age - b.age,
        "h2h_ratio": wins_a / total if total else 0.5,
        "surface_winrate_diff": a.surface_winrate - b.surface_winrate,
        "recent_form_diff": a.recent_form - b.recent_form,
    }
