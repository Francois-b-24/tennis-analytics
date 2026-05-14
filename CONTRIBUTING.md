# Guide de contribution

Merci de votre intérêt pour **tennis-analytics**. Ce dépôt est avant tout un laboratoire personnel ; les contributions externes restent possibles (issues, PR).

## Principe général

1. Ouvrir une **issue** (bug ou feature) avec le template GitHub.
2. Fork + branche dédiée : `feature/...` ou `fix/...`.
3. Commits au format **Conventional Commits en français**  
   Exemples : `feat: ajoute un graphique Elo comparatif`, `fix: corrige le filtre surface H2H`.
4. PR vers `develop` (ou `main` si flux simplifié), description complète via le template.

## Environnement local

```bash
uv sync --all-extras
uv run ruff check src app tests
uv run black src app tests
uv run pytest
```

## Conventions code

- **UI Streamlit** : français (titres, labels, messages).
- **Docstrings / commentaires** : français, style Google.
- **Identifiants Python** : anglais, type hints sur les API publiques.
- **Logs** : `loguru`, pas de `print`.
- **Chemins** : `pathlib` + `ROOT_PATH` (voir `.env.example`).
- **Visualisation dans `app/`** : Plotly uniquement ; thème via `app/components/plotly_theme.py`.
- **Tests** : toute fonction de calcul métier doit avoir une couverture pytest minimale.

## Données

Ne jamais committer de **secrets** ni de CSV bruts volumineux non nécessaires. Les parquets de `data/processed/` sont versionnés volontairement pour la démo ; surveillez la taille du dépôt.

## Licence

En contribuant, vous acceptez que vos apports soient sous licence **MIT** (voir [LICENSE](LICENSE)).
