"""Implémentation maison des ratings Elo tennis (global + surfaces, K adaptatif)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import exp
from typing import Final, Literal

import pandas as pd

BASE_ELO: Final[float] = 1500.0
INACTIVITY_DAYS: Final[int] = 180
DECAY_LAMBDA: Final[float] = 0.05
BO5_K_MULTIPLIER: Final[float] = 1.1
SURFACE_WEIGHT: Final[float] = 1.0

SurfaceKey = Literal["hard", "clay", "grass"]


def adaptive_k(matches_played: int) -> float:
    """Retourne le facteur K en fonction de l'expérience (matchs déjà joués).

    Args:
        matches_played: Nombre de matchs officiels déjà comptabilisés avant le match courant.

    Returns:
        Valeur K (40, 20 ou 10).

    Note:
        Les règles s'inspirent des pratiques courantes de modélisation Elo tennis
        (voir ressources Betfair / FiveThirtyEight) sans reproduire à l'identique
        un modèle propriétaire.
    """
    if matches_played < 30:
        return 40.0
    if matches_played < 100:
        return 20.0
    return 10.0


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def _parse_date_int(value: int | float) -> datetime:
    """Convertit un entier YYYYMMDD en datetime (minuit)."""
    s = f"{int(value):08d}"
    return datetime.strptime(s, "%Y%m%d")


def _apply_inactivity_decay(elo: float, last_played: datetime | None, today: datetime) -> float:
    """Applique une décroissance lente vers 1500 après 6 mois sans compétition."""
    if last_played is None:
        return elo
    gap = today - last_played
    if gap <= timedelta(days=INACTIVITY_DAYS):
        return elo
    months_over = (gap - timedelta(days=INACTIVITY_DAYS)).days / 30.0
    decay = exp(-months_over * DECAY_LAMBDA)
    return float(BASE_ELO + (elo - BASE_ELO) * decay)


@dataclass(slots=True)
class PlayerState:
    """État interne d'un joueur pour la mise à jour séquentielle."""

    elo_global: float = BASE_ELO
    elo_hard: float = BASE_ELO
    elo_clay: float = BASE_ELO
    elo_grass: float = BASE_ELO
    matches_played: int = 0
    last_match_date: datetime | None = None


@dataclass
class EloEngine:
    """Moteur Elo tennis avec séries parallèles (global + surfaces)."""

    players: dict[int, PlayerState] = field(default_factory=dict)

    def _get_surface_key(self, surface: str | None) -> SurfaceKey:
        if surface in {"hard", "clay", "grass"}:
            return surface  # type: ignore[return-value]
        return "hard"

    def _surface_rating(self, state: PlayerState, surface: SurfaceKey) -> float:
        if surface == "hard":
            return state.elo_hard
        if surface == "clay":
            return state.elo_clay
        return state.elo_grass

    def _set_surface_rating(self, state: PlayerState, surface: SurfaceKey, value: float) -> None:
        if surface == "hard":
            state.elo_hard = value
        elif surface == "clay":
            state.elo_clay = value
        else:
            state.elo_grass = value

    def _ensure_player(self, player_id: int) -> PlayerState:
        if player_id not in self.players:
            self.players[player_id] = PlayerState()
        return self.players[player_id]

    def prepare_for_match(
        self,
        winner_id: int,
        loser_id: int,
        tourney_date: int,
        surface_norm: str | None,
    ) -> tuple[PlayerState, PlayerState, SurfaceKey]:
        """Applique la décroissance d'inactivité puis retourne les états pré-résultat."""
        today = _parse_date_int(tourney_date)
        surface = self._get_surface_key(surface_norm)

        w_state = self._ensure_player(winner_id)
        l_state = self._ensure_player(loser_id)

        for state in (w_state, l_state):
            state.elo_global = _apply_inactivity_decay(
                state.elo_global, state.last_match_date, today
            )
            for s in ("hard", "clay", "grass"):
                surf = s  # type: ignore[assignment]
                current = self._surface_rating(state, surf)
                updated = _apply_inactivity_decay(current, state.last_match_date, today)
                self._set_surface_rating(state, surf, updated)

        return w_state, l_state, surface

    def apply_match_result(
        self,
        w_state: PlayerState,
        l_state: PlayerState,
        surface: SurfaceKey,
        best_of: int | float | None,
        match_day: datetime,
    ) -> None:
        """Applique la mise à jour Elo après un résultat connu."""
        k_w = adaptive_k(w_state.matches_played)
        k_l = adaptive_k(l_state.matches_played)
        bo5 = False
        if best_of is not None:
            try:
                bo5 = int(float(best_of)) == 5
            except (TypeError, ValueError):
                bo5 = False
        mult = BO5_K_MULTIPLIER if bo5 else 1.0
        k_w_eff = k_w * mult
        k_l_eff = k_l * mult

        e_w = _expected_score(w_state.elo_global, l_state.elo_global)
        e_l = 1.0 - e_w

        w_state.elo_global = w_state.elo_global + k_w_eff * (1.0 - e_w)
        l_state.elo_global = l_state.elo_global + k_l_eff * (0.0 - e_l)

        w_surf = self._surface_rating(w_state, surface)
        l_surf = self._surface_rating(l_state, surface)
        e_ws = _expected_score(w_surf, l_surf)
        e_ls = 1.0 - e_ws

        delta_ws = SURFACE_WEIGHT * k_w_eff * (1.0 - e_ws)
        delta_ls = SURFACE_WEIGHT * k_l_eff * (0.0 - e_ls)

        self._set_surface_rating(w_state, surface, w_surf + delta_ws)
        self._set_surface_rating(l_state, surface, l_surf + delta_ls)

        w_state.matches_played += 1
        l_state.matches_played += 1
        w_state.last_match_date = match_day
        l_state.last_match_date = match_day

    def process_match(
        self,
        winner_id: int,
        loser_id: int,
        tourney_date: int,
        surface_norm: str | None,
        best_of: int | float | None,
    ) -> None:
        """Met à jour les Elo après un match (décroissance + résultat)."""
        w_state, l_state, surface = self.prepare_for_match(
            winner_id, loser_id, tourney_date, surface_norm
        )
        self.apply_match_result(
            w_state,
            l_state,
            surface,
            best_of,
            _parse_date_int(tourney_date),
        )


def compute_elo_from_matches(
    matches: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Calcule les séries Elo à partir d'un DataFrame de matchs triable.

    Args:
        matches: Table enrichie (`winner_id`, `loser_id`, `tourney_date`,
            `surface_norm`, `best_of`).

    Returns:
        Tuple (`history`, `latest`, `match_context`) où `match_context` contient
        les Elo **avant** chaque match pour le vainqueur et le perdant
        (global + surface du match).
    """
    frame = matches.copy()
    sort_cols = [c for c in ("tourney_date", "match_uid") if c in frame.columns]
    frame = frame.sort_values(sort_cols or ["tourney_date"]).reset_index(drop=True)

    engine = EloEngine()
    history_rows: list[dict[str, object]] = []
    match_rows: list[dict[str, object]] = []

    for row in frame.itertuples(index=False):
        winner_id = int(row.winner_id)
        loser_id = int(row.loser_id)
        tourney_date = int(row.tourney_date)
        surface_norm = getattr(row, "surface_norm", None)
        best_of = getattr(row, "best_of", None)

        w_state, l_state, surface = engine.prepare_for_match(
            winner_id, loser_id, tourney_date, surface_norm
        )
        w_surf_pre = engine._surface_rating(w_state, surface)
        l_surf_pre = engine._surface_rating(l_state, surface)

        match_rows.append(
            {
                "match_uid": getattr(row, "match_uid", None),
                "tourney_date": tourney_date,
                "winner_id": winner_id,
                "loser_id": loser_id,
                "surface_norm": surface,
                "w_elo_g_pre": w_state.elo_global,
                "l_elo_g_pre": l_state.elo_global,
                "w_elo_surf_pre": w_surf_pre,
                "l_elo_surf_pre": l_surf_pre,
            }
        )

        match_day = _parse_date_int(tourney_date)
        engine.apply_match_result(w_state, l_state, surface, best_of, match_day)

        for pid in (winner_id, loser_id):
            st = engine.players[pid]
            history_rows.append(
                {
                    "tourney_date": tourney_date,
                    "player_id": pid,
                    "elo_global": st.elo_global,
                    "elo_hard": st.elo_hard,
                    "elo_clay": st.elo_clay,
                    "elo_grass": st.elo_grass,
                }
            )

    history = pd.DataFrame(history_rows)
    match_context = pd.DataFrame(match_rows)
    if history.empty:
        latest = pd.DataFrame(
            columns=[
                "player_id",
                "elo_global",
                "elo_hard",
                "elo_clay",
                "elo_grass",
                "last_match_date",
            ]
        )
        return history, latest, match_context

    last_rows = history.sort_values("tourney_date").groupby("player_id", as_index=False).tail(1)
    latest = last_rows.rename(columns={"tourney_date": "last_match_date"})
    return history, latest, match_context
