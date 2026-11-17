# Tennis Analytics Platform

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://tennisanalytics.streamlit.app/)
[![CI](https://github.com/Francois-b-24/tennis-analytics/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Francois-b-24/tennis-analytics/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Plateforme personnelle d’**analytics tennis ATP/WTA** : statistiques descriptives, **Elo maison** (global et par surface), **résultats à jour toutes les 3 h**, **régression logistique calibrée** pour la probabilité de victoire et tendances long-terme — interface **Streamlit** en français, stockage **DuckDB + Parquet**.

## Démo en ligne

L'application est déployée sur Streamlit Cloud : **https://tennisanalytics.streamlit.app/**

## Stack

| Domaine | Choix |
| --- | --- |
| Langage | Python 3.11 |
| Interface | Streamlit 1.67 (navigation `st.navigation`, thèmes clair et sombre) |
| Données | Parquet + vues DuckDB |
| Sources | Archive Jeff Sackmann (2010 → mai 2026), tennis-data.co.uk, ESPN |
| Pipeline | GitHub Actions toutes les 3 h, publication en Release GitHub |
| ML | scikit-learn (LogisticRegression + calibration isotonique) |
| Ratings | Elo implémenté maison (`src/tennis_analytics/ratings/elo.py`) |
| Qualité | Ruff, Black, pytest (dont smoke tests `AppTest` de toutes les pages) |

## Sources de données

| Période | Source | Contenu |
| --- | --- | --- |
| 2010 → 25/05/2026 | Archive Sackmann (`data/reference/`, figée) | Matchs avec statistiques détaillées, joueurs, classements |
| Depuis juin 2026 | [tennis-data.co.uk](https://www.tennis-data.co.uk) | Résultats et classement au match (publication ~hebdomadaire) |
| Derniers jours | API publique ESPN | Résultats du jour, marqués **provisoires** jusqu'à confirmation ; classement officiel du jour |

Les dépôts `JeffSackmann/tennis_atp` et `tennis_wta` ont été retirés en juin 2026 ;
l'archive est reconstructible depuis un miroir (`tennis-ingest --rebuild-archive`).
Les noms des sources récentes sont rapprochés des identifiants Sackmann
(`ingestion/player_matching.py`, alias manuels dans `data/reference/player_aliases.csv`).

## Architecture

```text
data/reference    → Archive Sackmann figée + instantané tennis-data + alias (versionnés)
data/processed    → Parquet servis + modèle joblib (copie de secours versionnée)
data/state        → État entre exécutions (gitignored, publié dans la Release)
src/tennis_analytics/
    ingestion/      → Sackmann (archive), tennis-data, ESPN, rapprochement des joueurs
    transformation/ → Fusion des sources, ordre chronologique, Elo, modèle
    ratings/        → Moteur Elo
    modeling/       → Probabilité de victoire (split temporel) + variables d'inférence
    publish.py      → Manifest SHA-256, contrôles de non-régression et de fraîcheur
    db/             → Connexion DuckDB + vues `read_parquet`
app/Home.py       → Routeur (st.navigation), barre latérale commune
app/views/        → Pages : Accueil, Résultats, Classements, Joueurs, Face-à-face,
                    Tournois, Tendances, Styles de jeu, Prédictions, Méthodologie
app/components/   → Bootstrap (synchronisation des données), requêtes, widgets, thème
tests/            → pytest
```

## Automatisation

L'application ne demande **aucune manipulation manuelle** :

| Quoi | Comment | Fréquence |
|---|---|---|
| Mise à jour des données | `daily_ingest.yml` : sources récentes → Elo/modèle si changement → Release `data-latest` | toutes les 3 h |
| Rafraîchissement de l'app | L'app relit le manifest de la Release et bascule atomiquement (SHA-256 vérifiés) | ≤ 15 min, sans redéploiement |
| Copie de secours | Commit des parquets sur `main` si la dernière date de plus de 7 jours | hebdomadaire |
| Alertes | Issues `ingestion-echec`, `donnees-perimees` (aucun match depuis 10 j hors intersaison), `cron-arrete`, `indisponibilite` | automatiques |
| Disponibilité | `healthcheck.yml` (keep-alive) et `keepalive.yml` (réarme les crons) | 6 h / hebdo |

tennis-data.co.uk refuse les IP de GitHub Actions (HTTP 403) : en CI, l'ingestion
réutilise le dernier instantané tennis-data versionné et s'appuie sur ESPN pour
les résultats récents. Lancer `uv run tennis-ingest` depuis un poste local
rafraîchit cet instantané (à commiter).

## Installation

```bash
git clone https://github.com/Francois-b-24/tennis-analytics.git
cd tennis-analytics
uv sync --all-extras
cp .env.example .env   # adapter ROOT_PATH si besoin
```

## Utilisation locale

```bash
uv run tennis-ingest                     # sources récentes + archive → data/processed
uv run tennis-ingest --offline           # archive seule, sans réseau
uv run tennis-ingest --rebuild-archive   # régénère l'archive Sackmann (ponctuel)

uv run python -m tennis_analytics.transformation.build_elo
uv run python -m tennis_analytics.transformation.build_model

uv run streamlit run app/Home.py         # lit la Release ; TENNIS_DATA_RELEASE_URL="" = données locales
```

`make help` liste les raccourcis (`make check`, `make rebuild`, `make deps`…).

## Qualité et tests

```bash
make check     # ruff + black + pytest (dont smoke tests AppTest de chaque page)
```

## Garde-fous données

- Ingestion en échec **bruyant** : source obligatoire injoignable sans instantané, schéma modifié, > 10 % de joueurs non reconnus.
- Publication refusée si le volume chute de plus de 10 % ou si la date du dernier match recule.
- Reconstruction déterministe (tri stable) : une exécution sans nouveauté ne publie rien.
- La CI échoue si un parquet dépasse `MAX_PARQUET_BYTES` (100 Mo par défaut).

## Déploiement Streamlit Community Cloud

1. Dépôt public `Francois-b-24/tennis-analytics`, point d'entrée `app/Home.py`.
2. Dépendances installées via `requirements.txt` (`make deps` le régénère depuis `pyproject.toml`).
3. Les données viennent de la Release `data-latest` ; `data/processed` sert de repli.

## Roadmap (extraits)

- [ ] Statistiques détaillées (aces, durée) pour les matchs postérieurs à mai 2026.
- [ ] Tournois Challenger.
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
