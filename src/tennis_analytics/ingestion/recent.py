"""Collecte des résultats postérieurs à l'archive Sackmann (tennis-data + ESPN).

Orchestration :

1. tennis-data (obligatoire) : tournois commencés après la fin de l'archive ;
2. ESPN (facultatif) : résultats des derniers jours, provisoires ;
3. dédoublonnage ESPN ↔ tennis-data (priorité tennis-data) ;
4. enrichissement joueurs (nom, pays, main, taille, âge) ;
5. classements hebdomadaires reconstitués à partir des classements au match.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from tennis_analytics.ingestion import espn_loader, tennis_data_loader
from tennis_analytics.ingestion.http import SourceUnavailableError
from tennis_analytics.ingestion.player_matching import (
    PlayerMatcher,
    last_activity,
    load_aliases,
)
from tennis_analytics.ingestion.schemas import MatchesSchema

#: Fenêtre (jours) dans laquelle un match ESPN est considéré comme déjà publié
#: par tennis-data (dates UTC et fuseaux différents).
DEDUP_WINDOW_DAYS = 2

#: Au-delà de cette part de joueurs non reconnus, la source a probablement
#: changé de format : on échoue plutôt que de polluer les données.
MAX_NEW_PLAYER_SHARE = 0.10


@dataclass(slots=True)
class RecentData:
    """Résultats récents prêts à fusionner avec l'archive."""

    matches: pd.DataFrame
    players: pd.DataFrame
    rankings: pd.DataFrame
    report: dict[str, Any] = field(default_factory=dict)


def drop_published_espn(matches: pd.DataFrame) -> pd.DataFrame:
    """Retire les matchs ESPN déjà présents dans tennis-data.

    Clé : même circuit, même paire de joueurs, dates à ±`DEDUP_WINDOW_DAYS`.
    """
    if matches.empty or "source" not in matches.columns:
        return matches
    out = matches.copy()
    out["_pair"] = [
        f"{c}|{min(a, b)}|{max(a, b)}"
        for c, a, b in zip(out["circuit"], out["winner_id"], out["loser_id"], strict=False)
    ]
    out["_day"] = pd.to_datetime(out["match_date"].astype(str), format="%Y%m%d")
    td = out.loc[out["source"] != "espn", ["_pair", "_day"]]
    espn = out.loc[out["source"] == "espn"]
    if espn.empty:
        return out.drop(columns=["_pair", "_day"])
    merged = espn.reset_index().merge(td, on="_pair", how="left", suffixes=("", "_td"))
    close = (merged["_day"] - merged["_day_td"]).abs().dt.days <= DEDUP_WINDOW_DAYS
    published = set(merged.loc[close, "index"])
    # Un même match ESPN peut aussi apparaître dans deux réponses (jours voisins).
    keep = out.drop(index=list(published))
    keep = keep.drop_duplicates(subset=["_pair", "_day", "source"], keep="first")
    if published:
        logger.info("ESPN : {} matchs déjà publiés par tennis-data écartés", len(published))
    return keep.drop(columns=["_pair", "_day"])


def enrich_players(matches: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """Ajoute nom, pays, main, taille et âge des joueurs (colonnes Sackmann)."""
    info = players.set_index("player_id")
    full = (
        info["name_first"].fillna("").astype(str) + " " + info["name_last"].fillna("").astype(str)
    ).str.strip()
    dob = pd.to_datetime(
        info["dob"].dropna().astype("int64").astype(str), format="%Y%m%d", errors="coerce"
    )
    out = matches.copy()
    match_day = pd.to_datetime(out["match_date"].astype(str), format="%Y%m%d")
    for side in ("winner", "loser"):
        ids = out[f"{side}_id"]
        out[f"{side}_name"] = ids.map(full)
        out[f"{side}_ioc"] = ids.map(info["ioc"])
        out[f"{side}_hand"] = ids.map(info["hand"])
        out[f"{side}_ht"] = ids.map(info["height"]).astype("float64")
        born = ids.map(dob)
        out[f"{side}_age"] = ((match_day - born).dt.days / 365.25).round(1)
        out[f"{side}_seed"] = np.nan
        out[f"{side}_entry"] = None
    return out


def weekly_rankings(matches: pd.DataFrame) -> pd.DataFrame:
    """Classements hebdomadaires reconstitués (dernier classement vu chaque semaine)."""
    parts = []
    for side in ("winner", "loser"):
        part = matches[
            ["circuit", "match_date", f"{side}_id", f"{side}_rank", f"{side}_rank_points"]
        ]
        parts.append(part.set_axis(["circuit", "match_date", "player", "rank", "points"], axis=1))
    stacked = pd.concat(parts, ignore_index=True).dropna(subset=["rank"])
    if stacked.empty:
        return pd.DataFrame(columns=["ranking_date", "rank", "player", "points", "circuit"])
    day = pd.to_datetime(stacked["match_date"].astype(str), format="%Y%m%d")
    monday = day - pd.to_timedelta(day.dt.weekday, unit="D")
    stacked["ranking_date"] = monday.dt.strftime("%Y%m%d").astype("int64")
    stacked = stacked.sort_values(["ranking_date", "match_date"], kind="mergesort")
    latest = stacked.groupby(["circuit", "ranking_date", "player"], as_index=False).tail(1)
    out = latest[["ranking_date", "rank", "player", "points", "circuit"]].copy()
    out["rank"] = out["rank"].astype("int64")
    out["player"] = out["player"].astype("int64")
    return out.reset_index(drop=True)


#: Fichiers d'état conservés d'une exécution à l'autre.
TD_MATCHES = "tennis_data_matches.parquet"
TD_REFERENCES = "tennis_data_tournaments.parquet"
TD_PLAYERS = "tennis_data_players.parquet"
ESPN_MATCHES = "espn_matches.parquet"


def _load_state(name: str, state_dir: Path, seed_dir: Path) -> pd.DataFrame | None:
    """Lit un fichier d'état (exécution précédente) ou, à défaut, l'instantané versionné."""
    for folder in (state_dir, seed_dir):
        path = folder / name
        if path.exists():
            return pd.read_parquet(path)
    return None


def _save_state(frame: pd.DataFrame, name: str, *dirs: Path) -> None:
    for folder in dirs:
        folder.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(folder / name, index=False)


def _as_int(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in ("match_date", "tourney_date", "winner_id", "loser_id", "match_num"):
        if col in out.columns:
            out[col] = out[col].astype("int64")
    return out


def merge_espn_history(previous: pd.DataFrame | None, latest: pd.DataFrame) -> pd.DataFrame:
    """Cumule les résultats ESPN : la fenêtre de l'API ne couvre que 7 jours.

    Un match vu lors d'une exécution précédente est conservé (jusqu'à sa
    publication par tennis-data) ; la version la plus récente l'emporte.
    """
    frames = [f for f in (previous, latest) if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    merged = _as_int(pd.concat(frames, ignore_index=True))
    pair = [
        f"{c}|{min(a, b)}|{max(a, b)}|{d}"
        for c, a, b, d in zip(
            merged["circuit"],
            merged["winner_id"],
            merged["loser_id"],
            merged["match_date"],
            strict=True,
        )
    ]
    merged = merged.assign(_key=pair).drop_duplicates(subset=["_key"], keep="last")
    return merged.drop(columns=["_key"]).reset_index(drop=True)


def collect_recent(
    project_root: Path,
    today: date | None = None,
    state_dir: Path | None = None,
) -> RecentData:
    """Collecte et normalise les résultats postérieurs à l'archive.

    tennis-data bloque les IP des serveurs d'intégration continue (Cloudflare,
    HTTP 403). Quand il est injoignable, on réutilise le dernier instantané
    réussi (`data/reference/recent/` ou l'état de l'exécution précédente) ;
    ESPN apporte alors les résultats des derniers jours, cumulés d'une
    exécution à l'autre.

    Args:
        project_root: Racine du dépôt.
        today: Date de référence (tests).
        state_dir: Dossier d'état entre exécutions (défaut : `data/state`).

    Raises:
        SourceUnavailableError: Aucune source récente (ni tennis-data ni
            instantané, ou ni tennis-data ni ESPN).
        RuntimeError: Trop de joueurs non reconnus (format de source modifié).
    """
    today = today or date.today()
    ref = project_root / "data" / "reference"
    seed_dir = ref / "recent"
    state_dir = state_dir or project_root / "data" / "state"
    archive = pd.read_parquet(ref / "sackmann_matches.parquet")
    archive_players = pd.read_parquet(ref / "sackmann_players.parquet")
    archive_rankings = pd.read_parquet(
        ref / "sackmann_rankings.parquet", columns=["player", "ranking_date"]
    )
    cutoff = archive.groupby("circuit")["tourney_date"].max().astype("int64").to_dict()
    first_year = min(cutoff.values()) // 10000 - 1
    years = range(first_year, today.year + 1)

    matcher = PlayerMatcher(
        players=archive_players,
        last_active=last_activity(archive, archive_rankings),
        aliases=load_aliases(ref / "player_aliases.csv"),
        reference_date=int(today.strftime("%Y%m%d")),
    )

    # 1. tennis-data : direct, sinon dernier instantané.
    td_status = "live"
    try:
        frames = tennis_data_loader.fetch_year_files(years)
        name_map = tennis_data_loader.tournament_name_map(frames, archive)
        td = _as_int(
            pd.concat(
                [
                    tennis_data_loader.to_matches(
                        frame, circuit, matcher, name_map, cutoff[circuit]
                    )
                    for (circuit, _), frame in sorted(frames.items())
                ],
                ignore_index=True,
            )
        )
        refs = espn_loader.reference_tournaments(frames, name_map)
        td_players = matcher.new_players_frame()
        # L'instantané versionné n'est rafraîchi que depuis un poste où le site répond.
        _save_state(td, TD_MATCHES, state_dir, seed_dir)
        _save_state(refs, TD_REFERENCES, state_dir, seed_dir)
        _save_state(td_players, TD_PLAYERS, state_dir, seed_dir)
    except SourceUnavailableError as exc:
        td_status = "snapshot"
        td = _load_state(TD_MATCHES, state_dir, seed_dir)
        refs = _load_state(TD_REFERENCES, state_dir, seed_dir)
        td_players = _load_state(TD_PLAYERS, state_dir, seed_dir)
        if td is None or refs is None:
            raise SourceUnavailableError(
                f"tennis-data injoignable et aucun instantané : {exc}"
            ) from exc
        logger.warning("tennis-data injoignable ({}) : instantané réutilisé", exc)
    td_players = td_players if td_players is not None else pd.DataFrame()

    # 2. ESPN : derniers jours, cumulés avec les exécutions précédentes.
    espn_error: str | None = None
    espn_rankings = pd.DataFrame()
    espn_latest = pd.DataFrame()
    try:
        events = espn_loader.fetch_events(today)
        espn_latest = espn_loader.to_matches(events, matcher, refs, cutoff)
        espn_rankings = espn_loader.fetch_rankings(matcher, today)
    except (SourceUnavailableError, AttributeError, KeyError, ValueError, TypeError) as exc:
        espn_error = str(exc)
        logger.warning("ESPN indisponible : {}", exc)
        if td_status == "snapshot":
            raise SourceUnavailableError(
                "Aucune source récente joignable (tennis-data et ESPN)"
            ) from exc
    espn = merge_espn_history(_load_state(ESPN_MATCHES, state_dir, state_dir), espn_latest)

    frames_recent = [_as_int(f) for f in (td, espn) if not f.empty and "match_date" in f.columns]
    recent = drop_published_espn(pd.concat(frames_recent, ignore_index=True))
    if not espn.empty:
        _save_state(recent.loc[recent["source"] == "espn", espn.columns], ESPN_MATCHES, state_dir)
    # Garde-fou de schéma : une source qui change de format doit faire échouer le job.
    recent = pd.DataFrame(MatchesSchema.validate(recent, lazy=True))

    known_ids = set(archive_players["player_id"])
    distinct = set(recent["winner_id"]) | set(recent["loser_id"])
    new_players = pd.concat([td_players, matcher.new_players_frame()], ignore_index=True)
    if not new_players.empty:
        new_players = (
            new_players.sort_values("name_first", key=lambda s: s.fillna("").str.len())
            .drop_duplicates(subset=["player_id"], keep="last")
            .loc[lambda f: f["player_id"].isin(distinct)]
            .sort_values("player_id", kind="mergesort")
            .reset_index(drop=True)
        )
    new_share = len(distinct - known_ids) / max(len(distinct), 1)
    logger.info(
        "Joueurs récents : {} distincts, {} nouveaux ({:.1%})",
        len(distinct),
        len(distinct - known_ids),
        new_share,
    )
    if new_share > MAX_NEW_PLAYER_SHARE:
        raise RuntimeError(
            f"{new_share:.1%} de joueurs non reconnus (> {MAX_NEW_PLAYER_SHARE:.0%}) : "
            "format de source probablement modifié."
        )

    all_players = pd.concat([archive_players, new_players], ignore_index=True)
    recent = enrich_players(recent, all_players)
    rankings = weekly_rankings(recent.loc[recent["source"] == "tennis-data"])
    if not espn_rankings.empty:
        rankings = pd.concat([rankings, espn_rankings], ignore_index=True)

    report = {
        "cutoff": {k: int(v) for k, v in cutoff.items()},
        "tennis_data": td_status,
        "tennis_data_last_match": {c: int(g["match_date"].max()) for c, g in td.groupby("circuit")},
        "rows": {k: int(v) for k, v in recent["source"].value_counts().items()},
        "last_match_date": {c: int(g["match_date"].max()) for c, g in recent.groupby("circuit")},
        "new_players": sorted(
            f"{r.circuit} {r.name_first} {r.name_last}" for r in new_players.itertuples()
        ),
        "espn_error": espn_error,
    }
    return RecentData(matches=recent, players=new_players, rankings=rankings, report=report)
