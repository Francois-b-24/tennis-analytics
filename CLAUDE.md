# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commandes courantes

```bash
# Installation
uv sync --all-extras

# Ingestion Sackmann (téléchargement → parquets interim → tables processed)
uv run tennis-ingest                              # complet
uv run tennis-ingest --skip-download              # CSV déjà locaux dans data/raw/
uv run tennis-ingest --skip-download --skip-build # matérialisation interim seule

# Recalcul Elo + modèle ML (à lancer après ingestion ou après modif moteur Elo)
uv run python -m transformation.build_elo
uv run python -m transformation.build_model

# App Streamlit
uv run streamlit run app/Home.py

# Qualité
uv run ruff check src app tests
uv run black --check src app tests
uv run pytest                                     # toute la suite
uv run pytest tests/test_elo.py::test_adaptive_k_steps -v   # un seul test
uv run pytest --cov=src --cov-report=term-missing tests/    # couverture
```

Le script `.venv/bin/tennis-ingest` requiert le package installé en editable (`pip install -e .[dev]`). Si `ModuleNotFoundError: No module named 'ingestion'`, lancer via `PYTHONPATH=src python -m ingestion.cli`.

## Architecture — flux de données

```
data/raw/*.csv  →  data/interim/*.parquet  →  data/processed/*.parquet  →  DuckDB views  →  Streamlit
   (Sackmann)      (typé + validé pandera)    (matches, players, elo*)     (v_*)            (app/)
```

Le **runtime app ne lit pas pandas directement** : il passe par des vues DuckDB (`v_matches`, `v_players`, `v_elo_latest`, `v_player_names`) déclarées dans `src/db/duckdb_session.py:create_connection`. Modifier le schéma d'un parquet impose de réviser la vue correspondante.

## Pipeline ML — règles non-négociables

- **Split temporel obligatoire** (`temporal_train_test_split` dans `src/modeling/win_probability.py`). Un fallback `train_test_split` aléatoire a été retiré volontairement pour éviter le leakage : si le split temporel produit < 10 lignes, on lève `ValueError`. **Ne jamais réintroduire de shuffle**.
- Features assemblées en streaming dans `assemble_training_frame` : `h2h`, `surface_winrate`, `recent_form` sont calculées en ne regardant que les matchs antérieurs. L'ordre chronologique du DataFrame d'entrée est critique.
- Le bundle joblib (`data/processed/models/logreg_calibrated.joblib`) contient `{model, features, diagnostics}` — la page Prédictions affiche calibration + feature importance depuis `diagnostics`. Régénérer le bundle après chaque modif du modèle.

## Moteur Elo — points sensibles

- `src/ratings/elo.py::EloEngine.prepare_for_match` applique la décroissance d'inactivité **de façon idempotente** via `state.last_decay_date`. Ne pas retirer ce garde-fou : sans lui, deux appels successifs pour la même date décrémenteraient deux fois.
- `match_uid` utilise le séparateur Unicode `§` (absent des données Sackmann) pour éviter les collisions de concaténation. Un `assert is_unique` garde l'invariant après dédup dans `src/transformation/pipeline.py`.

## Conventions code (cf. `.cursorrules`)

- **Langue** : UI Streamlit (`app/`), docstrings et commentaires en **français** (style Google). Identifiants Python en **anglais** (PEP 8).
- **Visualisation** : Plotly uniquement dans `app/`, jamais matplotlib/altair. Thème centralisé via `app/components/plotly_theme.py::apply_tennis_theme(fig)`. Utiliser `st.plotly_chart(fig, use_container_width=True)`.
- **Logging** : `loguru` (messages français), jamais `print`.
- **Chemins** : `pathlib` + `ROOT_PATH` (cf. `.env.example`), jamais de chemins absolus codés en dur.
- **Cache Streamlit** : `@st.cache_data` pour lectures DuckDB et agrégations, `@st.cache_resource` pour la connexion DuckDB.
- **Bootstrap pages** : chaque page Streamlit appelle `init_app(__file__)` depuis `app/components/_bootstrap.py` (gère `sys.path`, `.env`, connexion DuckDB cachée). Ne pas dupliquer le bloc d'init.
- **Composants UI obligatoires** : utiliser `page_header()` (pas `st.title` + `page_info`), `kpi_row()` (pas `st.columns` + `st.metric` recopiés), `section()` (pas `st.subheader` brut), `df_styled()` (pas `st.dataframe` direct — auto-détecte les `column_config` Elo / dates / pourcentages). Tous exposés depuis `app/components/widgets.py`.
- **Requêtes SQL partagées** : centraliser dans `app/components/queries.py` (`player_options`, `tournaments_for_circuit`, `latest_match_per_circuit`). Ne jamais redéfinir `_player_options` dans une page.
- **Selectbox circuit unifié** : utiliser `circuit_selectbox()` de `app/components/widgets.py` (constante `CIRCUITS = ("Tous", "ATP", "WTA")`). Toute concaténation SQL passe par `circuit_filter_sql()` qui valide via allowlist.
- **Tests** : toute fonction de calcul métier (Elo, features, pipeline) doit avoir une couverture pytest.

## Git & CI

- Commits : **Conventional Commits en français** (`feat: …`, `fix: …`, `chore: …`).
- CI (`.github/workflows/ci.yml`) lance ruff + black + pytest avec `--cov-fail-under=40` sur Python 3.11. Si la CI fail sur le linter, fixer le code, **pas la config**.
- Workflow `daily_ingest.yml` actif (cron 04:00 UTC) : ouvre une PR `data/update-<run_id>` avec les nouveaux parquets.
- Les parquets de `data/processed/` sont **volontairement versionnés** (~21 Mo total) pour Streamlit Cloud. Surveiller : la CI échoue si un parquet dépasse `MAX_PARQUET_BYTES` (défaut 100 Mo).

## Notes environnement

Si le projet est sous `~/Desktop` ou autre dossier sync iCloud, les opérations git/mmap peuvent échouer avec `Operation canceled`. Dans ce cas : `brctl download .` pour forcer le téléchargement local, ou déplacer le projet hors iCloud (`~/dev/`, `~/Code/`).
