# Changelog

Toutes les dates sont au format **JJ/MM/AAAA**. Ce projet suit une inspiration [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

## [1.0.0] — 15/05/2026

### Ajouté

- Application Streamlit complète avec **6 pages fonctionnelles** : Accueil (KPIs + navigation), Joueurs (fiche + Elo timeline), Face à Face (H2H + radar), Tournois (palmarès + top vainqueurs), Classements Elo (Top N par surface), Prédictions (probabilité ML), Insights (tendances long-terme).
- **Tooltip pédagogique Elo** au survol sur la page d'accueil.
- **Encarts descriptifs** sur chaque page expliquant son rôle.
- **Design responsive mobile** (CSS media queries injectées globalement, colonnes empilées sur petit écran).
- **Filtre circuit ATP/WTA** persistant en sidebar.
- Affichage du **dernier tournoi ATP et WTA** indexé sur la home.
- **Déploiement Streamlit Cloud** : https://tennisanalytics.streamlit.app/

### Modifié

- `requirements.txt` réduit aux dépendances strictement nécessaires à l'app (élimination des dépendances de pipeline `pandera`, etc.).
- `src/db/duckdb_session.py` : `get_project_root()` défini localement pour éviter la cascade d'imports vers `ingestion/`.
- Pinning de Python 3.11 via `.python-version` et `runtime.txt` pour Streamlit Cloud.

### Corrigé

- Reconstruction de `players.parquet` depuis les noms présents dans `matches.parquet` (les CSV Sackmann `atp_players` / `wta_players` n'avaient pas été téléchargés).
- Cast `winner_seed` / `loser_seed` en numérique dans le pipeline (valeurs `WC`/`Q`/`LL` cassaient PyArrow).
- Compatibilité `multimethod < 2.0` pour `pandera 0.21.1`.
- Gestion `NaN` sur les pages Joueurs et Face à Face (helper `_safe_float`/`_safe_int`).

## [0.1.0] — 14/05/2026

### Ajouté

- Structure monorepo (`src/`, `app/`, `data/`, `tests/`, `.github/`).
- Ingestion Sackmann ATP/WTA avec validation **pandera** et export **parquet**.
- Pipeline de transformation vers `matches`, `players`, `rankings`.
- Moteur **Elo** global + surfaces (K adaptatif, BO5 ×1,1, décroissance après inactivité).
- Module **probabilité de victoire** (logistique + calibration isotonique + backtest).
- Application Streamlit : **accueil** + page **Face à Face** (H2H, radar Plotly).
- CI GitHub Actions (Python 3.11 / 3.12, Ruff, Black, pytest + contrôle taille parquets).
- Workflow quotidien d’ingestion ouvrant une **PR** de mise à jour des données.
- Documentation : README, CONTRIBUTING, templates d’issues/PR, `.cursorrules`.

[1.0.0]: https://github.com/Francois-b-24/tennis-analytics
[0.1.0]: https://github.com/Francois-b-24/tennis-analytics
