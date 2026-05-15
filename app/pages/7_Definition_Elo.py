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

if not PDF_PATH.exists():
    st.error(
        "Le document PDF est introuvable. "
        "Vérifiez la présence du fichier `docs/elo_tennis_definition.pdf`."
    )
    st.stop()

# Bouton de téléchargement en haut
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

# ── Contenu lisible directement (extrait du PDF) ─────────────────────────────
st.markdown("""
# Le rating Elo au tennis

> *« L'Elo n'est pas un classement. C'est une mesure mathématique du niveau réel d'un compétiteur, qui apprend de chaque résultat. »*

---

## 1. Définition

Le **rating Elo** est un système de classement qui attribue un score numérique à chaque joueur et met à jour ce score après chaque match en fonction du résultat **et** de la force de l'adversaire affronté.

Inventé en 1960 par **Arpad Elo**, physicien hongrois et passionné d'échecs, ce système visait à classer les joueurs d'échecs de manière plus juste que les classements traditionnels.

Aujourd'hui, l'Elo est utilisé bien au-delà des échecs : tennis (par FiveThirtyEight, Tennis Abstract et la plupart des analystes data), football (Club Elo), jeux vidéo compétitifs (League of Legends, Counter-Strike), et même certaines applications de rencontres. Sa simplicité mathématique et sa puissance prédictive en font la métrique de référence pour comparer des compétiteurs.

**L'idée centrale en une phrase :** un joueur gagne plus de points en battant un adversaire mieux noté, et en perd plus en s'inclinant face à un adversaire moins bien noté.

---

## 2. La mécanique mathématique

Tout le système Elo tient en **deux formules**. C'est là sa beauté : une élégance mathématique au service d'un objectif simple, mesurer le niveau d'un joueur à partir de ses résultats.

### 2.1 Probabilité de victoire attendue

Avant le match, on calcule la probabilité que le joueur A batte le joueur B en fonction de leur écart d'Elo :

$$
P(A \\text{ bat } B) = \\frac{1}{1 + 10^{(Elo_B - Elo_A) / 400}}
$$

Le facteur **400** est une constante historique choisie par Arpad Elo. Elle signifie qu'un écart de 400 points correspond à un rapport de force de 10 contre 1, soit une probabilité de victoire de **91 %** pour le favori.

> **Exemple concret**
> Alcaraz est noté 2150 Elo, Djokovic 2080 Elo. La probabilité qu'Alcaraz gagne est :
> $P(\\text{Alcaraz}) = 1 / (1 + 10^{(2080 - 2150) / 400}) ≈ 0{,}60$
> Alcaraz est donc favori à environ **60 %**.

---

## 3. Le facteur K : régler la vitesse d'apprentissage

Le **facteur K** détermine la vitesse à laquelle le rating Elo s'ajuste après chaque match. C'est le paramètre central à calibrer dans tout système Elo. Un K élevé rend le rating nerveux et réactif, un K faible le rend stable mais lent à réagir.

| Valeur K | Comportement | Cible | Variation type |
|---|---|---|---|
| **K = 40** | Très nerveux | Nouveaux joueurs (< 30 matchs) | ± 16 points |
| **K = 20** | Équilibré (standard) | Joueurs établis (30 à 100 matchs) | ± 8 points |
| **K = 10** | Très stable | Joueurs vétérans (100+ matchs) | ± 4 points |

### L'approche adaptative

Dans notre projet, nous utilisons un **K adaptatif** qui démarre à 40 pour les nouveaux joueurs, descend à 20 après 30 matchs, puis à 10 après 100 matchs. Cette approche permet aux nouveaux entrants de trouver rapidement leur niveau réel, tandis que les vétérans bénéficient d'une stabilité statistique acquise après des centaines de matchs.

**Bonus Best-of-5 :** les matchs en trois sets gagnants (Grands Chelems) pèsent 1.1× plus que les matchs en deux sets gagnants, car ils sont plus représentatifs du niveau réel.

---

## 4. L'Elo par surface : un raffinement essentiel

Le tennis est unique parmi les sports majeurs : un même joueur peut être **excellent sur une surface et médiocre sur une autre**. Un Elo unique gommerait cette spécificité fondamentale du sport.

### L'exemple historique : Rafael Nadal

À son apogée, Nadal possédait un Elo estimé à environ **2 350 sur terre battue** contre seulement **2 050 sur gazon**. Un écart de 300 points qui, traduit en probabilité, signifie que Nadal gagnait environ **85 %** de ses matchs sur terre contre seulement **50 %** sur gazon, face au même type d'adversaire. Aucun Elo global ne pourrait capturer cette dualité.

C'est pourquoi notre projet **Tennis Analytics** calcule **quatre ratings Elo en parallèle** pour chaque joueur :

| Type d'Elo | Périmètre | Usage |
|---|---|---|
| **Elo global** | Tous matchs confondus | Classement général tous terrains |
| **Elo dur** | Matchs sur surface dure | Spécialisation hard-court |
| **Elo terre battue** | Matchs sur terre battue | Spécialisation clay |
| **Elo gazon** | Matchs sur gazon | Spécialisation grass |

---

## 5. Échelle indicative des ratings Elo

| Plage Elo | Niveau | Exemples |
|---|---|---|
| **2 200 +** | Élite mondiale (Top 5) | Sinner, Djokovic, Alcaraz, Świątek |
| **2 000 – 2 200** | Top 20 mondial | Joueurs établis du circuit ATP/WTA |
| **1 800 – 2 000** | Circuit pro principal | Top 100 mondial |
| **1 500 – 1 750** | Circuit Challenger | Niveau pro hors Top 100 |
| **1 500** (base) | Niveau de départ | Nouveaux entrants |

Ces ordres de grandeur restent approximatifs et dépendent de l'implémentation précise (choix du facteur K, gestion de l'inactivité, période d'observation). Ils fournissent toutefois une intuition robuste pour interpréter les ratings produits par notre plateforme.

---

## 6. Décroissance d'inactivité

Quand un joueur ne joue pas pendant **plus de 6 mois** (blessure, retraite temporaire), son rating Elo glisse progressivement vers la valeur de base 1500, suivant une décroissance exponentielle. Cela évite qu'un joueur absent conserve indéfiniment un rating élevé qui ne reflète plus son niveau actuel.

---

## 7. Implémentation Python simplifiée

Pour illustrer la simplicité du système, voici une fonction Python minimale qui applique les deux formules vues précédemment :

```python
def mettre_a_jour_elo(
    elo_gagnant: float,
    elo_perdant: float,
    k: float = 20.0,
) -> tuple[float, float]:
    # Probabilité attendue de victoire du gagnant
    proba = 1 / (1 + 10 ** ((elo_perdant - elo_gagnant) / 400))
    # Ajustement basé sur l'écart entre attendu et observé
    ajustement = k * (1 - proba)
    return elo_gagnant + ajustement, elo_perdant - ajustement
```

Pour construire le rating Elo complet de tous les joueurs ATP et WTA, il suffit ensuite d'appliquer cette fonction en boucle sur tous les matchs, par ordre chronologique. Chaque joueur démarre à 1500 et son rating évolue au fil des résultats.

---

## 8. Pour aller plus loin

- **FiveThirtyEight** — Méthodologie complète de leur modèle Elo tennis publiée en ligne.
- **Tennis Abstract** *(Jeff Sackmann)* — Articles techniques sur les ratings tennis et leurs limites.
- **Betfair Hub** — Article *Tennis Elo Modelling*, référence pratique pour l'application au tennis.
- **Glicko et Glicko-2** *(Mark Glickman)* — Évolution moderne de l'Elo intégrant l'incertitude du rating.

---

*Tennis Analytics Platform — Document de référence interne · Projet personnel*
""")
