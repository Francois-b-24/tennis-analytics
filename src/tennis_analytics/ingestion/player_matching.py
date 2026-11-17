"""Rapprochement des noms des sources récentes avec les identifiants Sackmann.

Les sources récentes n'ont pas d'identifiant commun avec Sackmann :

- tennis-data écrit « Nom Initiales. » (`Fritz T.`, `Auger-Aliassime F.`,
  `Tirante T.A.`) ;
- ESPN écrit le nom complet (`Taylor Fritz`, `Juan Manuel Cerundolo`).

On rapproche sur (circuit, nom normalisé, initiale du prénom) en préférant le
joueur actif le plus récemment. Un joueur inconnu reçoit un identifiant
**déterministe** (hash du nom) dans la plage réservée du circuit : il garde le
même identifiant d'une exécution à l'autre sans registre à maintenir.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from loguru import logger

from tennis_analytics.ids import NEW_PLAYER_ID_START

#: Taille des plages d'identifiants des nouveaux joueurs (par circuit).
NEW_PLAYER_ID_SPAN = 900_000

#: Un joueur inactif depuis plus longtemps n'est pas rapproché automatiquement
#: (évite d'attribuer les matchs d'un jeune joueur à un homonyme retraité).
MAX_INACTIVITY_DAYS = 4 * 365


def normalize(text: object) -> str:
    """Minuscules, sans accents ni ponctuation/espaces (`O'Connell` → `oconnell`)."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", ascii_only.lower())


_INITIALS = re.compile(r"^(?:[A-Za-z]{1,2}\.)+-?(?:[A-Za-z]{1,2}\.)*$")


def parse_initials_name(raw: str) -> tuple[str, str]:
    """Découpe un nom tennis-data (`De Minaur A.`, `Tirante T. A.`) en (nom, initiale).

    Les jetons finaux de la forme « X. » ou « Xy. » sont des initiales ; tout ce
    qui précède forme le nom de famille.

    Returns:
        Tuple (nom de famille tel qu'écrit, initiale du prénom en minuscule).
    """
    tokens = " ".join(str(raw).replace("\t", " ").split()).split(" ")
    initials: list[str] = []
    while len(tokens) > 1 and _INITIALS.match(tokens[-1]):
        initials.insert(0, tokens.pop())
    letters = normalize(initials[0]) if initials else ""
    return " ".join(tokens), letters[:1]


@dataclass(frozen=True, slots=True)
class Resolved:
    """Résultat d'un rapprochement."""

    player_id: int
    is_new: bool
    name_first: str
    name_last: str


@dataclass(slots=True)
class PlayerMatcher:
    """Index des joueurs connus, par circuit et nom normalisé."""

    players: pd.DataFrame
    last_active: dict[int, int]
    aliases: dict[tuple[str, str], int] = field(default_factory=dict)
    reference_date: int = 0
    _index: dict[tuple[str, str], list[tuple[int, str]]] = field(default_factory=dict)
    _swapped: dict[tuple[str, str], list[tuple[int, str]]] = field(default_factory=dict)
    new_players: dict[int, Resolved] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=lambda: {"matched": 0, "new": 0})
    _ioc: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for row in self.players.itertuples(index=False):
            key = (str(row.circuit), normalize(row.name_last))
            self._index.setdefault(key, []).append((int(row.player_id), normalize(row.name_first)))
            # Noms asiatiques parfois saisis dans l'ordre inverse (`Bu` / `Yunchaokete`).
            swapped = (str(row.circuit), normalize(row.name_first))
            self._swapped.setdefault(swapped, []).append(
                (int(row.player_id), normalize(row.name_last))
            )

    def _is_recent(self, player_id: int) -> bool:
        last = self.last_active.get(player_id)
        if last is None or not self.reference_date:
            return False
        last_ts = pd.to_datetime(str(last), format="%Y%m%d", errors="coerce")
        ref_ts = pd.to_datetime(str(self.reference_date), format="%Y%m%d", errors="coerce")
        if pd.isna(last_ts) or pd.isna(ref_ts):
            return False
        return (ref_ts - last_ts).days <= MAX_INACTIVITY_DAYS

    def _candidates(self, circuit: str, last_norm: str) -> list[tuple[int, str]]:
        exact = self._index.get((circuit, last_norm), [])
        if exact:
            return exact
        swapped = self._swapped.get((circuit, last_norm), [])
        if swapped or len(last_norm) < 4:
            return swapped
        # Repli : nom tronqué d'un côté (`Mpetshi` ↔ `Mpetshi Perricard`).
        found: list[tuple[int, str]] = []
        for (circ, name), items in self._index.items():
            prefix = name.startswith(last_norm) or last_norm.startswith(name)
            if circ == circuit and prefix and min(len(name), len(last_norm)) >= 4:
                found.extend(items)
        return found

    def _pick(self, circuit: str, last_norm: str, initial: str, first_norm: str = "") -> int | None:
        candidates = [
            (pid, first)
            for pid, first in self._candidates(circuit, last_norm)
            if (not initial or first.startswith(initial)) and self._is_recent(pid)
        ]
        if not candidates:
            return None
        if first_norm:
            exact_first = [c for c in candidates if c[1] == first_norm]
            candidates = exact_first or candidates
        # Le plus récemment actif, puis l'identifiant le plus grand (plus jeune).
        candidates.sort(key=lambda c: (self.last_active.get(c[0], 0), c[0]), reverse=True)
        return candidates[0][0]

    def _new_id(self, circuit: str, last_norm: str, initial: str) -> int:
        digest = hashlib.sha1(f"{circuit}|{last_norm}|{initial}".encode()).hexdigest()
        return NEW_PLAYER_ID_START[circuit] + int(digest, 16) % NEW_PLAYER_ID_SPAN

    def resolve(
        self,
        circuit: str,
        last_name: str,
        initial: str,
        first_name: str = "",
        source_name: str = "",
        ioc: str | None = None,
    ) -> Resolved:
        """Retourne l'identifiant du joueur (connu ou nouveau, déterministe)."""
        alias = self.aliases.get((circuit, normalize(source_name)))
        if alias is not None:
            self.stats["matched"] += 1
            return Resolved(alias, False, first_name, last_name)
        last_norm = normalize(last_name)
        pid = self._pick(circuit, last_norm, initial, normalize(first_name))
        if pid is not None:
            self.stats["matched"] += 1
            return Resolved(pid, False, first_name, last_name)
        new_id = self._new_id(circuit, last_norm, initial)
        self.stats["new"] += 1
        known = self.new_players.get(new_id)
        # On garde le prénom le plus complet vu (nom ESPN > initiale tennis-data).
        if known is None or len(first_name) > len(known.name_first):
            self.new_players[new_id] = Resolved(new_id, True, first_name, last_name)
        if ioc:
            self._ioc[new_id] = ioc
        return Resolved(new_id, True, first_name, last_name)

    def resolve_initials(self, circuit: str, raw: str) -> Resolved:
        """Rapproche un nom au format tennis-data (`Fritz T.`)."""
        last, initial = parse_initials_name(raw)
        return self.resolve(
            circuit,
            last,
            initial,
            first_name=f"{initial.upper()}." if initial else "",
            source_name=raw,
        )

    def resolve_full(self, circuit: str, full_name: str, ioc: str | None = None) -> Resolved:
        """Rapproche un nom complet ESPN (`Juan Manuel Cerundolo`).

        Essaie chaque découpage prénom/nom, du plus court nom de famille au plus
        long, et retient le premier qui correspond à un joueur connu.
        """
        tokens = " ".join(str(full_name).split()).split(" ")
        if len(tokens) == 1:
            return self.resolve(circuit, tokens[0], "", source_name=full_name, ioc=ioc)
        alias = self.aliases.get((circuit, normalize(full_name)))
        if alias is not None:
            self.stats["matched"] += 1
            return Resolved(alias, False, tokens[0], " ".join(tokens[1:]))
        for split in range(len(tokens) - 1, 0, -1):
            first = " ".join(tokens[:split])
            last = " ".join(tokens[split:])
            pid = self._pick(circuit, normalize(last), normalize(first)[:1], normalize(first))
            if pid is not None:
                self.stats["matched"] += 1
                return Resolved(pid, False, first, last)
        first, last = tokens[0], " ".join(tokens[1:])
        return self.resolve(circuit, last, normalize(first)[:1], first_name=first, ioc=ioc)

    def new_players_frame(self) -> pd.DataFrame:
        """Table `players` des joueurs découverts (schéma Sackmann minimal)."""
        rows = [
            {
                "player_id": r.player_id,
                "name_first": r.name_first,
                "name_last": r.name_last,
                "hand": None,
                "dob": None,
                "ioc": self._ioc.get(r.player_id),
                "height": None,
                "wikidata_id": None,
                "circuit": "ATP" if r.player_id < NEW_PLAYER_ID_START["WTA"] else "WTA",
            }
            for r in self.new_players.values()
        ]
        frame = pd.DataFrame(rows)
        if frame.empty:
            return frame
        frame["dob"] = frame["dob"].astype("float64")
        frame["height"] = frame["height"].astype("float64")
        return frame.sort_values("player_id", kind="mergesort").reset_index(drop=True)

    @property
    def unmatched_rate(self) -> float:
        """Part des rapprochements ayant créé un nouveau joueur."""
        total = self.stats["matched"] + self.stats["new"]
        return self.stats["new"] / total if total else 0.0


def load_aliases(path: Path) -> dict[tuple[str, str], int]:
    """Lit les correspondances manuelles `circuit,source_name,player_id`."""
    if not path.exists():
        return {}
    frame = pd.read_csv(path, comment="#")
    aliases = {
        (str(r.circuit), normalize(r.source_name)): int(r.player_id)
        for r in frame.itertuples(index=False)
    }
    logger.info("Alias joueurs chargés : {}", len(aliases))
    return aliases


def last_activity(matches: pd.DataFrame, rankings: pd.DataFrame | None = None) -> dict[int, int]:
    """Dernière date d'activité (match ou classement) par joueur."""
    parts = [
        matches[["winner_id", "tourney_date"]].rename(columns={"winner_id": "pid"}),
        matches[["loser_id", "tourney_date"]].rename(columns={"loser_id": "pid"}),
    ]
    if rankings is not None and not rankings.empty:
        parts.append(
            rankings[["player", "ranking_date"]].rename(
                columns={"player": "pid", "ranking_date": "tourney_date"}
            )
        )
    stacked = pd.concat(parts, ignore_index=True).dropna()
    grouped = stacked.groupby("pid")["tourney_date"].max()
    return {int(k): int(v) for k, v in grouped.items()}
