"""Source tennis-data.co.uk : résultats ATP/WTA consolidés (mise à jour ~hebdomadaire).

Les fichiers annuels `YYYY/YYYY.xlsx` (ATP) et `YYYYw/YYYY.xlsx` (WTA) sont
publiés sous un chemin variable : on le découvre sur la page `alldata.php`.
Chaque ligne est convertie au schéma `matches` de Sackmann ; les statistiques
de service et la durée ne sont pas fournies (colonnes laissées vides).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd
from loguru import logger

from tennis_analytics.ingestion.http import SourceUnavailableError, fetch_bytes
from tennis_analytics.ingestion.player_matching import (
    PlayerMatcher,
    normalize,
    parse_initials_name,
)

BASE_URL: Final[str] = "https://www.tennis-data.co.uk"
INDEX_URL: Final[str] = f"{BASE_URL}/alldata.php"

#: Niveaux tennis-data → codes `tourney_level` Sackmann.
LEVELS: Final[dict[str, dict[str, str]]] = {
    "ATP": {
        "ATP250": "A",
        "ATP500": "A",
        "Masters 1000": "M",
        "Grand Slam": "G",
        "Masters Cup": "F",
    },
    "WTA": {
        "WTA250": "I",
        "WTA500": "P",
        "WTA1000": "PM",
        "Grand Slam": "G",
        "Tour Championships": "F",
    },
}

#: Colonnes du schéma `matches` absentes de tennis-data (laissées vides).
STAT_COLUMNS: Final[tuple[str, ...]] = (
    "minutes",
    "w_ace",
    "w_df",
    "w_svpt",
    "w_1stIn",
    "w_1stWon",
    "w_2ndWon",
    "w_SvGms",
    "w_bpSaved",
    "w_bpFaced",
    "l_ace",
    "l_df",
    "l_svpt",
    "l_1stIn",
    "l_1stWon",
    "l_2ndWon",
    "l_SvGms",
    "l_bpSaved",
    "l_bpFaced",
)


@dataclass(frozen=True, slots=True)
class YearFile:
    """Fichier annuel tennis-data."""

    circuit: str
    year: int
    url: str


def discover_files(index_html: str) -> list[YearFile]:
    """Extrait les liens xlsx annuels de la page `alldata.php`."""
    found: dict[tuple[str, int], YearFile] = {}
    for href in re.findall(r'href="([^"]+\.xlsx)"', index_html, flags=re.IGNORECASE):
        match = re.search(r"/(\d{4})(w?)/\d{4}\.xlsx$", href)
        if not match:
            continue
        year = int(match.group(1))
        circuit = "WTA" if match.group(2) else "ATP"
        url = href if href.startswith("http") else f"{BASE_URL}/{href.lstrip('/')}"
        found[(circuit, year)] = YearFile(circuit, year, url)
    return sorted(found.values(), key=lambda f: (f.circuit, f.year))


def fetch_year_files(years: range) -> dict[tuple[str, int], pd.DataFrame]:
    """Télécharge les fichiers ATP/WTA des années demandées.

    Raises:
        SourceUnavailableError: Si l'index ou un fichier de l'année en cours est
            introuvable — source obligatoire, l'échec doit être visible.
    """
    index = fetch_bytes(INDEX_URL).decode("utf-8", errors="replace")
    files = {(f.circuit, f.year): f for f in discover_files(index)}
    frames: dict[tuple[str, int], pd.DataFrame] = {}
    for circuit in ("ATP", "WTA"):
        for year in years:
            meta = files.get((circuit, year))
            if meta is None:
                if year == max(years):
                    # Début janvier, le fichier de la nouvelle saison peut manquer.
                    logger.warning("tennis-data : pas encore de fichier {} {}", circuit, year)
                    continue
                raise SourceUnavailableError(f"tennis-data : fichier {circuit} {year} absent")
            payload = fetch_bytes(meta.url)
            frames[(circuit, year)] = pd.read_excel(io.BytesIO(payload))
            logger.info(
                "tennis-data {} {} : {} lignes", circuit, year, len(frames[(circuit, year)])
            )
    if not frames:
        raise SourceUnavailableError("tennis-data : aucun fichier lisible")
    return frames


def _clean_number(value: object) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        return np.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def build_score(row: pd.Series, n_sets: int = 5) -> str:
    """Score Sackmann (`6-4 7-6`) à partir des colonnes W1/L1… et du commentaire."""
    comment = str(row.get("Comment", "") or "").strip().lower()
    sets: list[str] = []
    for i in range(1, n_sets + 1):
        w = _clean_number(row.get(f"W{i}"))
        lo = _clean_number(row.get(f"L{i}"))
        if np.isnan(w) or np.isnan(lo):
            continue
        sets.append(f"{int(w)}-{int(lo)}")
    if comment.startswith("walkover"):
        return "W/O"
    score = " ".join(sets)
    if comment.startswith("retired"):
        score = f"{score} RET".strip()
    elif comment.startswith(("awarded", "disqualified", "def")):
        score = f"{score} DEF".strip()
    return score


def _best_of(value: object) -> int:
    number = _clean_number(value)
    return 3 if np.isnan(number) else int(number)


def round_code(label: str, first_round_matches: int) -> str:
    """Convertit un libellé de tour (`2nd Round`, `Round 2`, `Semifinals`…) en code Sackmann.

    Args:
        label: Libellé de la source.
        first_round_matches: Nombre de matchs (programmés) du premier tour,
            pour déduire la taille du tableau (byes compris).
    """
    text = label.strip().lower()
    if "robin" in text or "group" in text:
        return "RR"
    if text.startswith("quarter"):
        return "QF"
    if text.startswith("semi"):
        return "SF"
    if text in {"the final", "final", "finals", "championship"}:
        return "F"
    number = re.search(r"(\d+)", text)
    if number:
        n = int(number.group(1))
        draw = 1
        while draw < 2 * max(first_round_matches, 1):
            draw *= 2
        size = max(draw // (2 ** (n - 1)), 16)
        return f"R{size}"
    return label


def _monday_int(first_date: pd.Timestamp) -> int:
    """Lundi de la semaine du tournoi.

    Un tournoi qui débute le week-end (Roland-Garros, Wimbledon…) est daté du
    lundi suivant, comme dans Sackmann.
    """
    weekday = first_date.weekday()
    if weekday >= 5:
        start = first_date + pd.Timedelta(days=7 - weekday)
    else:
        start = first_date - pd.Timedelta(days=weekday)
    return int(start.strftime("%Y%m%d"))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def tournament_name_map(
    frames: dict[tuple[str, int], pd.DataFrame], archive: pd.DataFrame
) -> dict[tuple[str, str], str]:
    """Associe chaque tournoi tennis-data au nom utilisé par Sackmann.

    Sur la période où les deux sources se recouvrent, un tournoi tennis-data
    correspond à un tournoi Sackmann s'il commence la même semaine (±3 jours)
    et que la finale a le même vainqueur. Un nom Sackmann n'est attribué qu'à
    un seul tournoi tennis-data. Les palmarès de la page Tournois restent ainsi
    continus d'une source à l'autre.

    Returns:
        `{(circuit, tournoi tennis-data): tourney_name Sackmann}`.
    """
    finals = archive.loc[
        archive["round"] == "F", ["circuit", "tourney_date", "tourney_name", "winner_name"]
    ].copy()
    finals["last"] = finals["winner_name"].map(lambda n: normalize(str(n).split(" ")[-1]))
    finals["date"] = pd.to_datetime(finals["tourney_date"].astype(str), format="%Y%m%d")
    votes: dict[tuple[str, str], dict[str, int]] = {}
    for (circuit, _), frame in frames.items():
        dates = pd.to_datetime(frame["Date"], errors="coerce")
        starts = dates.groupby(frame["Tournament"]).min()
        td_finals = frame.loc[frame["Round"].astype(str).str.strip() == "The Final"]
        for row in td_finals.itertuples(index=False):
            last, _ = parse_initials_name(str(row.Winner))
            monday = pd.to_datetime(str(_monday_int(starts[row.Tournament])), format="%Y%m%d")
            cands = finals.loc[
                (finals["circuit"] == circuit)
                & (finals["last"] == normalize(last.split(" ")[-1]))
                & ((monday - finals["date"]).dt.days.abs() <= 3)
            ]
            for name in cands["tourney_name"]:
                key = (circuit, str(row.Tournament).strip())
                votes.setdefault(key, {}).setdefault(name, 0)
                votes[key][name] += 1
    ranked = sorted(
        ((key, *max(c.items(), key=lambda kv: (kv[1], kv[0]))) for key, c in votes.items()),
        key=lambda item: (-item[2], item[0]),
    )
    mapping: dict[tuple[str, str], str] = {}
    taken: set[tuple[str, str]] = set()
    for key, name, _count in ranked:
        if (key[0], name) in taken:
            continue
        mapping[key] = name
        taken.add((key[0], name))
    logger.info("Noms de tournois alignés sur Sackmann : {}", len(mapping))
    return mapping


def tourney_id_for(tourney_date: int, tourney_name: str) -> str:
    """Identifiant de tournoi des sources récentes (semaine + nom)."""
    return f"{tourney_date}-{_slug(tourney_name)}"


def to_matches(
    frame: pd.DataFrame,
    circuit: str,
    matcher: PlayerMatcher,
    name_map: dict[tuple[str, str], str],
    after_date: int,
) -> pd.DataFrame:
    """Convertit un fichier tennis-data au schéma `matches`.

    Args:
        frame: Fichier annuel brut.
        circuit: 'ATP' ou 'WTA'.
        matcher: Rapprochement des joueurs.
        name_map: Noms de tournois Sackmann (cf. :func:`tournament_name_map`).
        after_date: Seuls les tournois commencés **après** cette date (fin de
            l'archive Sackmann, AAAAMMJJ) sont retenus.

    Returns:
        Matchs au schéma Sackmann, `source="tennis-data"`.
    """
    df = frame.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Winner", "Loser"])
    level_col = "Series" if circuit == "ATP" else "Tier"
    rows: list[dict[str, object]] = []
    for (tournament, location), group in df.groupby(["Tournament", "Location"], sort=False):
        first_date = group["Date"].min()
        if int(first_date.strftime("%Y%m%d")) <= after_date:
            continue
        tourney_date = _monday_int(first_date)
        tourney_name = name_map.get((circuit, str(tournament).strip()), str(location).strip())
        tourney_id = tourney_id_for(tourney_date, tourney_name)
        rounds = group["Round"].astype(str)
        first_round = int((rounds.str.strip() == "1st Round").sum())
        level = LEVELS[circuit].get(str(group[level_col].iloc[0]).strip(), "A")
        for match_num, (_, row) in enumerate(group.iterrows(), start=1):
            winner = matcher.resolve_initials(circuit, str(row["Winner"]))
            loser = matcher.resolve_initials(circuit, str(row["Loser"]))
            rows.append(
                {
                    "tourney_id": tourney_id,
                    "tourney_name": tourney_name,
                    "surface": str(row["Surface"]).strip(),
                    "draw_size": np.nan,
                    "tourney_level": level,
                    "tourney_date": tourney_date,
                    "match_num": match_num,
                    "winner_id": winner.player_id,
                    "loser_id": loser.player_id,
                    "score": build_score(row),
                    "best_of": _best_of(row.get("Best of")),
                    "round": round_code(str(row["Round"]), first_round),
                    "winner_rank": _clean_number(row.get("WRank")),
                    "winner_rank_points": _clean_number(row.get("WPts")),
                    "loser_rank": _clean_number(row.get("LRank")),
                    "loser_rank_points": _clean_number(row.get("LPts")),
                    "match_date": int(row["Date"].strftime("%Y%m%d")),
                    "circuit": circuit,
                    "source": "tennis-data",
                }
            )
    out = pd.DataFrame(rows)
    for col in STAT_COLUMNS:
        out[col] = np.nan
    return out
