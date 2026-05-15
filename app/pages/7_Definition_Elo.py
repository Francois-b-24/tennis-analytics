"""Page Définition Elo : affiche le contenu du PDF de définition du rating Elo."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parents[1]
_ROOT = Path(__file__).resolve().parents[2]

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")
os.environ.setdefault("ROOT_PATH", str(_ROOT))

_SRC = _ROOT / "src"
for path in (_APP_DIR, _ROOT, _SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import pandas as pd
import streamlit as st

from components.widgets import inject_global_css, page_info

st.set_page_config(page_title="Définition Elo — Tennis Analytics", layout="wide")
inject_global_css()

st.title("Définition du rating Elo")
page_info(
    "Document de référence détaillant le système de notation Elo appliqué au tennis : "
    "principes mathématiques, ajustements par surface, facteur K adaptatif et décroissance d'inactivité."
)

PDF_PATH = _ROOT / "docs" / "elo_tennis_definition.pdf"

if PDF_PATH.exists():
    with PDF_PATH.open("rb") as f:
        pdf_bytes = f.read()
    st.download_button(
        label="📄 Télécharger le PDF original",
        data=pdf_bytes,
        file_name="elo_tennis_definition.pdf",
        mime="application/pdf",
        type="secondary",
    )

st.divider()

# ── Section 1 — Définition ───────────────────────────────────────────────────
st.markdown("## 1. Définition")
st.markdown(
    """
Le **rating Elo** est un système de classement qui attribue un score numérique à
chaque joueur et met à jour ce score après chaque match en fonction du résultat
**et** de la force de l'adversaire affronté.

Inventé en 1960 par **Arpad Elo**, physicien hongrois et passionné d'échecs, ce
système visait à classer les joueurs d'échecs de manière plus juste que les
classements traditionnels.

Aujourd'hui, l'Elo est utilisé bien au-delà des échecs : tennis (FiveThirtyEight,
Tennis Abstract), football (Club Elo), jeux vidéo compétitifs (League of Legends,
Counter-Strike), et même certaines applications de rencontres.

**L'idée centrale en une phrase :** un joueur gagne plus de points en battant un
adversaire mieux noté, et en perd plus en s'inclinant face à un adversaire moins
bien noté.
"""
)

st.markdown(
    """
> *« L'Elo n'est pas un classement. C'est une mesure mathématique du niveau
> réel d'un compétiteur, qui apprend de chaque résultat. »*
"""
)

st.divider()

# ── Section 2 — Mécanique mathématique ───────────────────────────────────────
st.markdown("## 2. La mécanique mathématique")
st.markdown(
    """
Tout le système Elo tient en **deux formules**. C'est là sa beauté : une élégance
mathématique au service d'un objectif simple, mesurer le niveau d'un joueur à
partir de ses résultats.

### 2.1 Probabilité de victoire attendue

Avant le match, on calcule la probabilité que le joueur A batte le joueur B en
fonction de leur écart d'Elo :
"""
)

st.latex(r"P(A \text{ bat } B) = \frac{1}{1 + 10^{(Elo_B - Elo_A) / 400}}")

st.markdown(
    """
Le facteur **400** est une constante historique choisie par Arpad Elo. Elle
signifie qu'un écart de 400 points correspond à un rapport de force de 10 contre 1,
soit une probabilité de victoire de **91 %** pour le favori.
"""
)

st.info(
    "**Exemple concret** — Alcaraz est noté 2150 Elo, Djokovic 2080 Elo. "
    "La probabilité qu'Alcaraz gagne est ≈ **0,60** : Alcaraz est donc favori "
    "à environ **60 %**."
)

st.divider()

# ── Section 3 — Facteur K ────────────────────────────────────────────────────
st.markdown("## 3. Le facteur K : régler la vitesse d'apprentissage")
st.markdown(
    """
Le **facteur K** détermine la vitesse à laquelle le rating Elo s'ajuste après
chaque match. C'est le paramètre central à calibrer : un K élevé rend le rating
nerveux et réactif, un K faible le rend stable mais lent à réagir.
"""
)

df_k = pd.DataFrame({
    "Valeur K": ["K = 40", "K = 20", "K = 10"],
    "Comportement": ["Très nerveux", "Équilibré (standard)", "Très stable"],
    "Cible": [
        "Nouveaux joueurs (< 30 matchs)",
        "Joueurs établis (30 à 100 matchs)",
        "Joueurs vétérans (100+ matchs)",
    ],
    "Variation type": ["± 16 points", "± 8 points", "± 4 points"],
})
st.dataframe(df_k, use_container_width=True, hide_index=True)

st.markdown(
    """
### L'approche adaptative

Dans notre projet, nous utilisons un **K adaptatif** : 40 pour les nouveaux
joueurs, 20 après 30 matchs, puis 10 après 100 matchs. Les nouveaux entrants
trouvent rapidement leur niveau réel, tandis que les vétérans bénéficient d'une
stabilité statistique.

**Bonus Best-of-5 :** les matchs en trois sets gagnants (Grands Chelems) pèsent
1,1× plus que les matchs en deux sets gagnants, car ils sont plus représentatifs
du niveau réel.
"""
)

st.divider()

# ── Section 4 — Elo par surface ──────────────────────────────────────────────
st.markdown("## 4. L'Elo par surface : un raffinement essentiel")
st.markdown(
    """
Le tennis est unique parmi les sports majeurs : un même joueur peut être
**excellent sur une surface et médiocre sur une autre**. Un Elo unique gommerait
cette spécificité fondamentale du sport.

### L'exemple historique : Rafael Nadal

À son apogée, Nadal possédait un Elo estimé à environ **2 350 sur terre battue**
contre seulement **2 050 sur gazon**. Un écart de 300 points qui, traduit en
probabilité, signifie que Nadal gagnait environ **85 %** de ses matchs sur terre
contre seulement **50 %** sur gazon, face au même type d'adversaire.

C'est pourquoi notre projet calcule **quatre ratings Elo en parallèle** :
"""
)

df_surf = pd.DataFrame({
    "Type d'Elo": ["Elo global", "Elo dur", "Elo terre battue", "Elo gazon"],
    "Périmètre": [
        "Tous matchs confondus",
        "Matchs sur surface dure",
        "Matchs sur terre battue",
        "Matchs sur gazon",
    ],
    "Usage": [
        "Classement général tous terrains",
        "Spécialisation hard-court",
        "Spécialisation clay",
        "Spécialisation grass",
    ],
})
st.dataframe(df_surf, use_container_width=True, hide_index=True)

st.divider()

# ── Section 5 — Échelle indicative ───────────────────────────────────────────
st.markdown("## 5. Échelle indicative des ratings Elo")

df_echelle = pd.DataFrame({
    "Plage Elo": ["2 200 +", "2 000 – 2 200", "1 800 – 2 000", "1 500 – 1 750", "1 500 (base)"],
    "Niveau": [
        "Élite mondiale (Top 5)",
        "Top 20 mondial",
        "Circuit pro principal",
        "Circuit Challenger",
        "Niveau de départ",
    ],
    "Exemples": [
        "Sinner, Djokovic, Alcaraz, Świątek",
        "Joueurs établis ATP/WTA",
        "Top 100 mondial",
        "Niveau pro hors Top 100",
        "Nouveaux entrants",
    ],
})
st.dataframe(df_echelle, use_container_width=True, hide_index=True)

st.caption(
    "Ces ordres de grandeur restent approximatifs et dépendent de l'implémentation "
    "précise (choix du facteur K, gestion de l'inactivité, période d'observation). "
    "Ils fournissent toutefois une intuition robuste pour interpréter les ratings "
    "produits par notre plateforme."
)

st.divider()

# ── Section 6 — Décroissance d'inactivité ────────────────────────────────────
st.markdown("## 6. Décroissance d'inactivité")
st.markdown(
    """
Quand un joueur ne joue pas pendant **plus de 6 mois** (blessure, retraite
temporaire), son rating Elo glisse progressivement vers la valeur de base 1500,
suivant une décroissance exponentielle. Cela évite qu'un joueur absent conserve
indéfiniment un rating élevé qui ne reflète plus son niveau actuel.
"""
)

st.divider()

# ── Section 7 — Implémentation Python ────────────────────────────────────────
st.markdown("## 7. Implémentation Python simplifiée")
st.markdown(
    "Pour illustrer la simplicité du système, voici une fonction Python minimale "
    "qui applique les deux formules vues précédemment :"
)

st.code(
    """def mettre_a_jour_elo(
    elo_gagnant: float,
    elo_perdant: float,
    k: float = 20.0,
) -> tuple[float, float]:
    # Probabilité attendue de victoire du gagnant
    proba = 1 / (1 + 10 ** ((elo_perdant - elo_gagnant) / 400))
    # Ajustement basé sur l'écart entre attendu et observé
    ajustement = k * (1 - proba)
    return elo_gagnant + ajustement, elo_perdant - ajustement""",
    language="python",
)

st.markdown(
    """
Pour construire le rating Elo complet de tous les joueurs ATP et WTA, il suffit
ensuite d'appliquer cette fonction en boucle sur tous les matchs, par ordre
chronologique. Chaque joueur démarre à 1500 et son rating évolue au fil des
résultats.
"""
)

st.divider()

# ── Section 8 — Pour aller plus loin ─────────────────────────────────────────
st.markdown("## 8. Pour aller plus loin")
st.markdown(
    """
- **FiveThirtyEight** — Méthodologie complète de leur modèle Elo tennis publiée en ligne.
- **Tennis Abstract** *(Jeff Sackmann)* — Articles techniques sur les ratings tennis et leurs limites.
- **Betfair Hub** — Article *Tennis Elo Modelling*, référence pratique pour l'application au tennis.
- **Glicko et Glicko-2** *(Mark Glickman)* — Évolution moderne de l'Elo intégrant l'incertitude du rating.
"""
)

st.caption("*Tennis Analytics Platform — Document de référence interne · Projet personnel*")
