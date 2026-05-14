# Changelog

Toutes les dates sont au format **JJ/MM/AAAA**. Ce projet suit une inspiration [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

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

[0.1.0]: https://github.com/Francois-b-24/tennis-analytics
