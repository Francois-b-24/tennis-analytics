"""Régénère `requirements.txt` à partir de `pyproject.toml`.

Streamlit Community Cloud installe les dépendances via pip et ne lit pas
`pyproject.toml` : `requirements.txt` doit donc exister. Plutôt que de maintenir
les deux à la main (et de les laisser diverger), ce script dérive le second du
premier — `pyproject.toml` reste l'unique source de vérité.

Usage :
    make deps
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ENTETE = """\
# ⚠️  FICHIER GÉNÉRÉ — NE PAS ÉDITER À LA MAIN.
#
# Source de vérité : la section [project.dependencies] de pyproject.toml.
# Ce fichier n'existe que pour Streamlit Community Cloud, qui installe via pip
# et ne lit pas pyproject.toml.
#
# Régénérer après toute modification des dépendances :
#     make deps
#
# L'application est installée en editable par Streamlit Cloud grâce à la
# dernière ligne (`-e .`), ce qui rend le package `tennis_analytics` importable.

"""

PIED = """
# Rend `tennis_analytics.*` importable depuis app/ sans bidouille de sys.path.
-e .
"""


def main() -> int:
    """Écrit `requirements.txt` et signale s'il était périmé.

    Returns:
        0 si le fichier était déjà à jour, 1 s'il vient d'être régénéré
        (utile pour faire échouer une CI qui détecterait une dérive).
    """
    racine = Path(__file__).resolve().parents[1]
    pyproject = racine / "pyproject.toml"
    cible = racine / "requirements.txt"

    donnees = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    dependances = donnees["project"]["dependencies"]

    contenu = ENTETE + "\n".join(sorted(dependances, key=str.lower)) + "\n" + PIED

    ancien = cible.read_text(encoding="utf-8") if cible.exists() else ""
    if ancien == contenu:
        print("requirements.txt déjà à jour.")
        return 0

    cible.write_text(contenu, encoding="utf-8")
    print(f"requirements.txt régénéré ({len(dependances)} dépendances).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
