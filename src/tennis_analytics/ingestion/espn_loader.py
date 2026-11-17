"""Source ESPN (API publique non officielle) : résultats des tournois en cours.

tennis-data ne publie qu'environ une fois par semaine. ESPN permet d'afficher
les résultats du jour, avec quelques heures de retard. Ces lignes sont
**provisoires** (`source="espn"`) : dès que tennis-data publie le même match,
c'est sa version qui est conservée. Si ESPN est indisponible ou change de
format, l'ingestion continue avec tennis-data seul.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Final

import numpy as np
import pandas as pd
from loguru import logger

from tennis_analytics.ingestion.http import fetch_bytes
from tennis_analytics.ingestion.player_matching import PlayerMatcher, normalize
from tennis_analytics.ingestion.tennis_data_loader import (
    LEVELS,
    STAT_COLUMNS,
    _monday_int,
    round_code,
    tourney_id_for,
)

SCOREBOARD_URL: Final[str] = (
    "https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard"
)
SINGLES_SLUG: Final[dict[str, str]] = {"ATP": "mens-singles", "WTA": "womens-singles"}
FINAL_STATUSES: Final[set[str]] = {"STATUS_FINAL", "STATUS_RETIRED", "STATUS_WALKOVER"}
FINALS_NAME: Final[dict[str, str]] = {"ATP": "Tour Finals", "WTA": "WTA Finals"}

#: Écart maximal (jours dans l'année) pour reconnaître un tournoi d'une saison à l'autre.
MAX_CALENDAR_GAP_DAYS: Final[int] = 30


def fetch_events(today: date, days: int = 7) -> dict[str, list[dict[str, Any]]]:
    """Récupère les événements ESPN couvrant les `days` derniers jours.

    Returns:
        `{circuit: [événements]}`, dédoublonnés par identifiant ESPN.

    Raises:
        SourceUnavailableError: Si ESPN ne répond pas.
    """
    events: dict[str, dict[str, dict[str, Any]]] = {"ATP": {}, "WTA": {}}
    for circuit in ("ATP", "WTA"):
        url = SCOREBOARD_URL.format(tour=circuit.lower())
        for offset in range(days):
            day = (today - timedelta(days=offset)).strftime("%Y%m%d")
            payload = json.loads(fetch_bytes(f"{url}?dates={day}", timeout_s=30))
            for event in payload.get("events", []):
                events[circuit][str(event.get("id"))] = event
    return {c: list(v.values()) for c, v in events.items()}


RANKINGS_URL: Final[str] = "https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/rankings"


def fetch_rankings(matcher: PlayerMatcher, today: date) -> pd.DataFrame:
    """Classement officiel du jour (top 150 ATP et WTA) au schéma `rankings`.

    tennis-data ne fournit le classement qu'au moment des matchs ; ESPN donne
    le classement en vigueur, daté du lundi de la semaine courante.
    """
    monday = today - timedelta(days=today.weekday())
    rows = []
    for circuit in ("ATP", "WTA"):
        payload = json.loads(fetch_bytes(RANKINGS_URL.format(tour=circuit.lower()), timeout_s=30))
        ranking = (payload.get("rankings") or [{}])[0]
        for item in ranking.get("ranks", []):
            athlete = item.get("athlete") or {}
            name = athlete.get("displayName")
            if not name or item.get("current") is None:
                continue
            player = matcher.resolve_full(circuit, name, _ioc(athlete))
            rows.append(
                {
                    "ranking_date": int(monday.strftime("%Y%m%d")),
                    "rank": int(item["current"]),
                    "player": player.player_id,
                    "points": float(item.get("points") or 0.0),
                    "circuit": circuit,
                }
            )
    return pd.DataFrame(rows)


def _calendar_gap(a: pd.Timestamp, b: pd.Timestamp) -> int:
    diff = abs(a.day_of_year - b.day_of_year)
    return min(diff, 365 - diff)


def _tournament_info(
    circuit: str,
    event_name: str,
    city: str,
    start: pd.Timestamp,
    references: pd.DataFrame,
) -> dict[str, str] | None:
    """Retrouve nom, surface et niveau d'un événement ESPN.

    `references` liste les tournois connus (circuit, ville, nom, surface,
    niveau, date de début) issus de tennis-data et de l'archive.
    """
    lowered = event_name.lower()
    is_tour_finals = "finals" in lowered and not any(
        word in lowered for word in ("cup", "next gen", "qualif", "united")
    )
    if is_tour_finals:
        cands = references.loc[
            (references["circuit"] == circuit) & (references["tourney_level"] == "F")
        ]
        if cands.empty:
            return {"tourney_name": FINALS_NAME[circuit], "surface": "Hard", "tourney_level": "F"}
    else:
        cands = references.loc[
            (references["circuit"] == circuit) & (references["city_norm"] == normalize(city))
        ]
    if cands.empty:
        return None
    gaps = cands["start"].map(lambda d: _calendar_gap(d, start))
    best = cands.loc[gaps.idxmin()]
    if gaps.min() > MAX_CALENDAR_GAP_DAYS:
        return None
    return {
        "tourney_name": str(best["tourney_name"]),
        "surface": str(best["surface"]),
        "tourney_level": str(best["tourney_level"]),
    }


def _score(competitors: list[dict[str, Any]], status: str) -> str:
    if status == "STATUS_WALKOVER":
        return "W/O"
    winner = next(c for c in competitors if c.get("winner"))
    loser = next(c for c in competitors if not c.get("winner"))
    sets = []
    for w_set, l_set in zip(
        winner.get("linescores") or [], loser.get("linescores") or [], strict=False
    ):
        w_val, l_val = w_set.get("value"), l_set.get("value")
        if w_val is None or l_val is None:
            continue
        text = f"{int(w_val)}-{int(l_val)}"
        tiebreak = w_set.get("tiebreak", l_set.get("tiebreak"))
        if tiebreak is not None:
            text += f"({int(tiebreak)})"
        sets.append(text)
    score = " ".join(sets)
    return f"{score} RET".strip() if status == "STATUS_RETIRED" else score


def _ioc(athlete: dict[str, Any]) -> str | None:
    citizenship = athlete.get("citizenshipCountry")
    if isinstance(citizenship, str) and len(citizenship) == 3:
        return citizenship.upper()
    flag = athlete.get("flag") or ""
    href = flag.get("href", "") if isinstance(flag, dict) else str(flag)
    code = href.rsplit("/", 1)[-1].split(".")[0]
    return code.upper() if len(code) == 3 else None


def to_matches(
    events: dict[str, list[dict[str, Any]]],
    matcher: PlayerMatcher,
    references: pd.DataFrame,
    after_date: dict[str, int],
) -> pd.DataFrame:
    """Convertit les événements ESPN au schéma `matches` (simples, tableau final).

    Les qualifications et les événements non reconnus (Challenger, WTA 125…,
    hors du périmètre Sackmann/tennis-data) sont ignorés.
    """
    rows: list[dict[str, object]] = []
    for circuit, circuit_events in events.items():
        for event in circuit_events:
            comps = [
                c
                for g in event.get("groupings", [])
                for c in g.get("competitions", [])
                if (c.get("type") or {}).get("slug") == SINGLES_SLUG[circuit]
                and not str((c.get("round") or {}).get("displayName", "")).startswith("Qualif")
            ]
            if not comps:
                continue
            dates = pd.to_datetime([c.get("date") for c in comps], utc=True, errors="coerce")
            start = dates.min().tz_localize(None).normalize()
            city = str((comps[0].get("venue") or {}).get("fullName", "")).split(",")[0]
            info = _tournament_info(circuit, str(event.get("name", "")), city, start, references)
            if info is None:
                logger.info("ESPN : événement ignoré (hors périmètre) : {}", event.get("name"))
                continue
            tourney_date = _monday_int(start)
            first_round = sum(
                1 for c in comps if str((c.get("round") or {}).get("displayName")) == "Round 1"
            )
            for num, comp in enumerate(comps, start=1):
                status = (comp.get("status") or {}).get("type") or {}
                if not status.get("completed") or status.get("name") not in FINAL_STATUSES:
                    continue
                competitors = comp.get("competitors") or []
                if len(competitors) != 2 or not all("athlete" in c for c in competitors):
                    continue
                if sum(bool(c.get("winner")) for c in competitors) != 1:
                    continue
                match_date = pd.Timestamp(comp.get("date")).tz_convert(None)
                if int(match_date.strftime("%Y%m%d")) <= after_date[circuit]:
                    continue
                win = next(c for c in competitors if c.get("winner"))
                los = next(c for c in competitors if not c.get("winner"))
                w = matcher.resolve_full(
                    circuit, win["athlete"]["displayName"], _ioc(win["athlete"])
                )
                lo = matcher.resolve_full(
                    circuit, los["athlete"]["displayName"], _ioc(los["athlete"])
                )
                periods = ((comp.get("format") or {}).get("regulation") or {}).get("periods")
                rows.append(
                    {
                        "tourney_id": tourney_id_for(tourney_date, info["tourney_name"]),
                        "tourney_name": info["tourney_name"],
                        "surface": info["surface"],
                        "draw_size": np.nan,
                        "tourney_level": info["tourney_level"],
                        "tourney_date": tourney_date,
                        "match_num": 10_000 + num,
                        "winner_id": w.player_id,
                        "loser_id": lo.player_id,
                        "score": _score(competitors, str(status.get("name"))),
                        "best_of": int(periods) if periods in (3, 5) else 3,
                        "round": round_code(str(comp["round"]["displayName"]), first_round),
                        "winner_rank": np.nan,
                        "winner_rank_points": np.nan,
                        "loser_rank": np.nan,
                        "loser_rank_points": np.nan,
                        "match_date": int(match_date.strftime("%Y%m%d")),
                        "circuit": circuit,
                        "source": "espn",
                    }
                )
    out = pd.DataFrame(rows)
    for col in STAT_COLUMNS:
        out[col] = np.nan
    return out


def reference_tournaments(
    td_frames: dict[tuple[str, int], pd.DataFrame],
    name_map: dict[tuple[str, str], str],
) -> pd.DataFrame:
    """Table (circuit, ville, nom, surface, niveau, début) des tournois tennis-data."""
    rows = []
    for (circuit, _), frame in td_frames.items():
        level_col = "Series" if circuit == "ATP" else "Tier"
        dates = pd.to_datetime(frame["Date"], errors="coerce")
        grouped = frame.assign(_d=dates).groupby(["Tournament", "Location"], sort=False)
        for (tournament, location), group in grouped:
            rows.append(
                {
                    "circuit": circuit,
                    "city_norm": normalize(location),
                    "tourney_name": name_map.get(
                        (circuit, str(tournament).strip()), str(location).strip()
                    ),
                    "surface": str(group["Surface"].iloc[0]).strip(),
                    "tourney_level": LEVELS[circuit].get(
                        str(group[level_col].iloc[0]).strip(), "A"
                    ),
                    "start": group["_d"].min(),
                }
            )
    return pd.DataFrame(rows)
