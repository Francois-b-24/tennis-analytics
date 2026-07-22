"""Tests de la liste de joueurs proposée dans les selectbox.

Invariant protégé : **tout joueur proposé doit exister dans les données**. Le
fichier joueurs de Sackmann contient ~122 800 entrées (juniors, qualifiés,
homonymes) contre ~3 500 ayant réellement joué depuis 2010. Sans filtrage, 97 %
des noms de la liste n'ont ni statistiques ni historique Elo, et les pages
affichent « Historique Elo indisponible » dès l'ouverture — un faux négatif qui
donne l'impression que le pipeline est cassé alors que les données sont saines.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

# app/ n'est pas un package : insérer dans sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from components.queries import player_options

# `player_options` est décorée par @st.cache_data ; on teste la fonction nue.
_options = player_options.__wrapped__


@pytest.fixture()
def connexion(monkeypatch: pytest.MonkeyPatch) -> duckdb.DuckDBPyConnection:
    """Base en mémoire : 2 joueurs ayant joué, 1 fantôme sans aucun match."""
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE VIEW v_players AS SELECT * FROM (VALUES
            (101, 'Alice', 'Active', 'FRA', 'WTA'),
            (102, 'Bob',   'Actif',  'ESP', 'ATP'),
            (999, 'Carl',  'Fantome','USA', 'ATP')
        ) AS t(player_id, name_first, name_last, ioc, circuit);
        """
    )
    conn.execute(
        """
        CREATE VIEW v_matches AS SELECT * FROM (VALUES
            (101, 102, 'WTA'),
            (102, 101, 'ATP')
        ) AS t(winner_id, loser_id, circuit);
        """
    )
    monkeypatch.setattr("components.queries._shared_connection", lambda _cle: conn)
    return conn


def test_exclut_les_joueurs_sans_match(connexion: duckdb.DuckDBPyConnection) -> None:
    """Un joueur du fichier Sackmann sans aucun match ne doit pas être proposé."""
    ids = set(_options("cle", "Tous")["player_id"])
    assert ids == {101, 102}
    assert 999 not in ids, "le joueur fantôme ne doit jamais apparaître dans la liste"


def test_filtre_par_circuit(connexion: duckdb.DuckDBPyConnection) -> None:
    """Le filtre circuit s'applique aux matchs, pas seulement à la fiche joueur."""
    assert set(_options("cle", "ATP")["player_id"]) == {102}
    assert set(_options("cle", "WTA")["player_id"]) == {101}


def test_liste_triee_par_nom(connexion: duckdb.DuckDBPyConnection) -> None:
    """La liste est triée alphabétiquement (ordre stable dans les selectbox)."""
    noms = _options("cle", "Tous")["full_name"].tolist()
    assert noms == sorted(noms)


def test_colonnes_attendues(connexion: duckdb.DuckDBPyConnection) -> None:
    """Le contrat de colonnes est respecté (consommé par `player_selectbox`)."""
    assert list(_options("cle", "Tous").columns) == ["player_id", "full_name", "ioc"]


def test_vue_absente_renvoie_frame_vide(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans les vues DuckDB, la fonction dégrade proprement au lieu de lever."""
    conn = duckdb.connect(":memory:")
    monkeypatch.setattr("components.queries._shared_connection", lambda _cle: conn)
    resultat = _options("cle", "Tous")
    assert isinstance(resultat, pd.DataFrame)
    assert resultat.empty
