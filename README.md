# Tennis Analytics Platform

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://tennisanalytics.streamlit.app/)
[![CI](https://github.com/Francois-b-24/tennis-analytics/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Francois-b-24/tennis-analytics/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Plateforme personnelle d’**analytics tennis ATP/WTA** : statistiques descriptives, **Elo maison** (global et par surface), **régression logistique calibrée** pour la probabilité de victoire, et **insights** sur les tendances long-terme — interface **Streamlit** en français, stockage **DuckDB + Parquet**.

## Démo en ligne

L'application est déployée sur Streamlit Cloud : **https://tennisanalytics.streamlit.app/**

## Stack

| Domaine | Choix |
| --- | --- |
| Langage | Python 3.11+ |
| Interface | Streamlit |
| Données | Parquet + vues DuckDB |
| Pipeline | GitHub Actions (cron + PR données) |
| ML | scikit-learn (LogisticRegression + calibration isotonique) |
| Ratings | Elo implémenté maison (`src/ratings/elo.py`) |
| Qualité | Ruff, Black, pytest + couverture |
| Logs | loguru |
| Validation | pandera (schémas critiques) |

## Architecture

```text
data/raw          → CSV Sackmann (gitignored)
data/interim      → Parquet typés post-validation
data/processed    → Parquet consommés par DuckDB + modèles joblib
src/ingestion     → Téléchargement et validation
src/transformation→ Consolidation, Elo, entraînement modèle
src/db            → Connexion DuckDB + vues `read_parquet`
app/              → Streamlit (FR), thème Plotly centralisé
```

## Prérequis

- [uv](https://docs.astral.sh/uv/) (recommandé) ou pip équivalent
- Compte GitHub pour cloner / pousser le dépôt `tennis-analytics`

## Installation

```bash
git clone https://github.com/Francois-b-24/tennis-analytics.git
cd tennis-analytics
uv sync --all-extras
cp .env.example .env   # adapter ROOT_PATH si besoin
```

## Utilisation locale

```bash
# Ingestion complète (télécharge les CSV Sackmann, filtre 2010+, écrit les parquets)
uv run tennis-ingest

# Recalcul des Elo et contexte pré-match
uv run python -m transformation.build_elo

# Entraînement + export du modèle calibré
uv run python -m transformation.build_model

# Application Streamlit
uv run streamlit run app/Home.py
```

## Qualité et tests

```bash
uv run ruff check src app tests
uv run black --check src app tests
uv run pytest
```

## Secrets GitHub (optionnels)

| Secret | Usage |
| --- | --- |
| `CODECOV_TOKEN` | Couverture détaillée (Codecov), si vous l’activez |
| `SLACK_WEBHOOK_URL` | Notification d’échec d’ingestion (non câblé par défaut) |
| `MAX_PARQUET_BYTES` | Variable dépôt (`vars`) pour le seuil de taille en CI |

Les jeux Sackmann sont **publics** : aucun secret n’est requis pour l’ingestion.

## Garde-fous données

- Les parquets volumineux peuvent alourdir le dépôt : le workflow **CI** échoue si un fichier de `data/processed/` dépasse le plafond (par défaut **100 Mo**, surchargeable via `MAX_PARQUET_BYTES`).
- `.gitattributes` marque `*.parquet` en **binary** pour des diffs propres.
- L’ingestion quotidienne ouvre une **PR** (`peter-evans/create-pull-request`) plutôt que de pousser directement sur `main`.

## Déploiement Streamlit Community Cloud

1. Connecter le dépôt public `Francois-b-24/tennis-analytics`.
2. Point d’entrée : `app/Home.py`.
3. S’assurer que les **parquets** nécessaires sont présents sur la branche déployée (ou lancer une ingestion manuelle / merger une PR data).

Badge dédié (à activer après premier déploiement) :

```markdown
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/<votre-app>)
```

## Roadmap (extraits)

- [ ] Pages Joueurs, Tournois, Elo comparés, Prédictions (UI complète).
- [ ] Enrichissements tactiques (momentum, clutch, clustering).
- [ ] DVC ou release d’artefacts si la taille Git devient problématique.
- [ ] MLflow optionnel pour la traçabilité des expériences.

## Contribution

Voir [CONTRIBUTING.md](CONTRIBUTING.md). Même en projet perso, les conventions (Conventional Commits en français, PR template) servent de vitrine.

## Licence et contact

- Licence **MIT** : voir [LICENSE](LICENSE) (François B.).
- Contact : via GitHub [@Francois-b-24](https://github.com/Francois-b-24).

---

## Bloc Git / GitHub (initialisation dépôt)

```bash
cd /chemin/vers/tennis-analytics
git init
git branch -M main

git add .
git commit -m "chore: bootstrap du projet tennis-analytics"

# Création du dépôt distant + premier push (GitHub CLI)
gh repo create Francois-b-24/tennis-analytics \
  --public \
  --description "Plateforme d'analytics tennis ATP/WTA : stats, ratings Elo et prédictions ML, propulsée par Streamlit et DuckDB" \
  --source=. \
  --remote=origin \
  --push

# Topics (répéter --add-topic autant que nécessaire)
gh repo edit Francois-b-24/tennis-analytics \
  --add-topic tennis \
  --add-topic data-science \
  --add-topic streamlit \
  --add-topic duckdb \
  --add-topic machine-learning \
  --add-topic sports-analytics \
  --add-topic elo-rating \
  --add-topic python

# Branche de développement
git checkout -b develop
git push -u origin develop
```

Configurer la branche par défaut sur `main` et, si besoin, la protection de branche dans l’UI GitHub (**Settings → Branches**).

---

## Checklist de publication (ordre suggéré)

1. `cd /Users/f.b/Desktop/Data_Science/Data_Science/Projets/tennis`
2. `git init` (si premier usage) puis `git branch -M main`
3. `uv sync --all-extras` puis `uv run pytest` / `uv run ruff check` / `uv run black --check`
4. `git add .` puis `git commit -m "chore: bootstrap du projet tennis-analytics"`
5. `gh repo create Francois-b-24/tennis-analytics --public --description "Plateforme d'analytics tennis ATP/WTA : stats, ratings Elo et prédictions ML, propulsée par Streamlit et DuckDB" --source=. --remote=origin --push`
6. `gh repo edit Francois-b-24/tennis-analytics --add-topic tennis --add-topic data-science --add-topic streamlit --add-topic duckdb --add-topic machine-learning --add-topic sports-analytics --add-topic elo-rating --add-topic python`
7. `git checkout -b develop` puis `git push -u origin develop`
8. Activer Streamlit Cloud sur `main` ou `develop` selon votre flux de release.
