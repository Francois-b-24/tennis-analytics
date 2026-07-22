"""Tests de l'invalidation automatique du cache de données.

Ces tests protègent l'invariant central du déploiement : l'application doit
servir les données fraîches dès que l'ingestion quotidienne réécrit les
parquets, **sans redémarrage manuel**. Une régression ici est silencieuse en
production (l'app affiche simplement des chiffres périmés), d'où la couverture.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# app/ n'est pas un package : insérer dans sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from components._bootstrap import _KEY_SEP, data_fingerprint, data_key

# `data_fingerprint` est décorée par @st.cache_data ; on teste la fonction nue
# pour éviter que le cache Streamlit ne masque les changements de mtime.
_empreinte = data_fingerprint.__wrapped__


@pytest.fixture()
def projet(tmp_path: Path) -> Path:
    """Crée une arborescence minimale avec un parquet factice."""
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "matches.parquet").write_bytes(b"donnees-v1")
    return tmp_path


def test_empreinte_stable_sans_changement(projet: Path) -> None:
    """Deux lectures consécutives sans modification donnent la même empreinte."""
    assert _empreinte(str(projet)) == _empreinte(str(projet))


def test_empreinte_change_si_contenu_modifie(projet: Path) -> None:
    """Réécrire un parquet (taille différente) change l'empreinte."""
    avant = _empreinte(str(projet))
    (projet / "data" / "processed" / "matches.parquet").write_bytes(b"donnees-v2-plus-longue")
    assert _empreinte(str(projet)) != avant


def test_empreinte_change_si_mtime_modifie(projet: Path) -> None:
    """Une réécriture à taille identique est détectée via le mtime.

    Cas réel : l'ingestion régénère un parquet dont le volume n'a pas bougé.
    """
    chemin = projet / "data" / "processed" / "matches.parquet"
    avant = _empreinte(str(projet))
    stat = chemin.stat()
    os.utime(chemin, (stat.st_atime, stat.st_mtime + 120))
    assert _empreinte(str(projet)) != avant


def test_empreinte_detecte_nouveau_fichier(projet: Path) -> None:
    """L'ajout d'un parquet (ex. nouvelle table) change l'empreinte."""
    avant = _empreinte(str(projet))
    (projet / "data" / "processed" / "players.parquet").write_bytes(b"joueurs")
    assert _empreinte(str(projet)) != avant


def test_empreinte_prend_en_compte_les_modeles(projet: Path) -> None:
    """Le bundle joblib du modèle ML fait partie de l'empreinte."""
    modeles = projet / "data" / "processed" / "models"
    modeles.mkdir()
    avant = _empreinte(str(projet))
    (modeles / "logreg_calibrated.joblib").write_bytes(b"modele")
    assert _empreinte(str(projet)) != avant


def test_empreinte_ignore_fichiers_non_pertinents(projet: Path) -> None:
    """Un fichier annexe (.gitkeep, log) ne doit pas invalider le cache."""
    avant = _empreinte(str(projet))
    (projet / "data" / "processed" / ".gitkeep").write_text("")
    (projet / "data" / "processed" / "notes.txt").write_text("bla")
    assert _empreinte(str(projet)) == avant


def test_empreinte_repertoire_absent(tmp_path: Path) -> None:
    """Sans dossier `data/processed`, l'empreinte est explicite et ne lève pas."""
    assert _empreinte(str(tmp_path)) == "absent"


def test_empreinte_repertoire_vide(tmp_path: Path) -> None:
    """Dossier présent mais sans parquet : empreinte explicite."""
    (tmp_path / "data" / "processed").mkdir(parents=True)
    assert _empreinte(str(tmp_path)) == "vide"


def test_data_key_contient_racine_et_empreinte(projet: Path) -> None:
    """La clé de cache combine la racine et l'empreinte, séparées par `_KEY_SEP`."""
    cle = data_key(projet)
    racine, separateur, empreinte = cle.partition(_KEY_SEP)
    assert racine == str(projet)
    assert separateur == _KEY_SEP
    assert empreinte


def test_data_key_differe_entre_deux_projets(tmp_path: Path) -> None:
    """Deux racines distinctes ne partagent jamais la même clé de cache."""
    a, b = tmp_path / "a", tmp_path / "b"
    for racine in (a, b):
        (racine / "data" / "processed").mkdir(parents=True)
        (racine / "data" / "processed" / "matches.parquet").write_bytes(b"x")
    assert data_key(a) != data_key(b)
