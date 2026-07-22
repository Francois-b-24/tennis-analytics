# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commandes courantes

Un `Makefile` enveloppe les tâches usuelles (`make help` pour la liste) :
`make install`, `make app`, `make rebuild` (ingestion + Elo + modèle),
`make check` (lint + tests avant commit), `make deps` (régénère
`requirements.txt` depuis `pyproject.toml`). Les commandes brutes équivalentes :

```bash
# Installation
uv sync --all-extras

# Ingestion Sackmann (téléchargement → parquets interim → tables processed)
uv run tennis-ingest                              # complet
uv run tennis-ingest --skip-download              # CSV déjà locaux dans data/raw/
uv run tennis-ingest --skip-download --skip-build # matérialisation interim seule

# Recalcul Elo + modèle ML (à lancer après ingestion ou après modif moteur Elo)
uv run python -m tennis_analytics.transformation.build_elo
uv run python -m tennis_analytics.transformation.build_model

# App Streamlit
uv run streamlit run app/Home.py

# Qualité
uv run ruff check src app tests
uv run black --check src app tests
uv run pytest                                     # toute la suite
uv run pytest tests/test_elo.py::test_adaptive_k_steps -v   # un seul test
uv run pytest --cov=src --cov-report=term-missing tests/    # couverture
```

Le script `tennis-ingest` requiert le package installé en editable (`uv sync` ou `pip install -e .[dev]`). Si `ModuleNotFoundError: No module named 'tennis_analytics'`, lancer via `PYTHONPATH=src python -m tennis_analytics.ingestion.cli`.

## Structure du dépôt

Layout `src/` de type cookiecutter-data-science. **Tout le code métier vit dans le
package unique `src/tennis_analytics/`** (`ingestion`, `transformation`, `ratings`,
`modeling`, `db`, `analytics`) — les imports sont toujours qualifiés
(`from tennis_analytics.ratings.elo import ...`).

`app/` n'est **pas** un package installé : les pages Streamlit l'atteignent via le
`sys.path.insert` en tête de fichier, suivi de `init_app(__file__)`. C'est la raison
du `# ruff: E402` toléré sur `app/**` — les imports après le bootstrap sont voulus.

`data/raw` et `data/interim` sont gitignorés ; **`data/processed` est versionné**
(~22 Mo) car Streamlit Cloud n'exécute pas le pipeline.

## Architecture — flux de données

```
data/raw/*.csv  →  data/interim/*.parquet  →  data/processed/*.parquet  →  DuckDB views  →  Streamlit
   (Sackmann)      (typé + validé pandera)    (matches, players, elo*)     (v_*)            (app/)
```

Le **runtime app ne lit pas pandas directement** : il passe par des vues DuckDB (`v_matches`, `v_players`, `v_elo_latest`, `v_player_names`) déclarées dans `src/tennis_analytics/db/duckdb_session.py:create_connection`. Modifier le schéma d'un parquet impose de réviser la vue correspondante.

## Pipeline ML — règles non-négociables

- **Split temporel obligatoire** (`temporal_train_test_split` dans `src/tennis_analytics/modeling/win_probability.py`). Un fallback `train_test_split` aléatoire a été retiré volontairement pour éviter le leakage : si le split temporel produit < 10 lignes, on lève `ValueError`. **Ne jamais réintroduire de shuffle**.
- Features assemblées en streaming dans `assemble_training_frame` : `h2h`, `surface_winrate`, `recent_form` sont calculées en ne regardant que les matchs antérieurs. L'ordre chronologique du DataFrame d'entrée est critique.
- Le bundle joblib (`data/processed/models/logreg_calibrated.joblib`) contient `{model, features, diagnostics}` — la page Prédictions affiche calibration + feature importance depuis `diagnostics`. Régénérer le bundle après chaque modif du modèle.

## Moteur Elo — points sensibles

- `src/tennis_analytics/ratings/elo.py::EloEngine.prepare_for_match` applique la décroissance d'inactivité **de façon idempotente** via `state.last_decay_date`. Ne pas retirer ce garde-fou : sans lui, deux appels successifs pour la même date décrémenteraient deux fois.
- `match_uid` utilise le séparateur Unicode `§` (absent des données Sackmann) pour éviter les collisions de concaténation. Un `assert is_unique` garde l'invariant après dédup dans `src/tennis_analytics/transformation/pipeline.py`.

## Conventions code (cf. `.cursorrules`)

- **Langue** : UI Streamlit (`app/`), docstrings et commentaires en **français** (style Google). Identifiants Python en **anglais** (PEP 8).
- **Visualisation** : Plotly uniquement dans `app/`, jamais matplotlib/altair. Thème centralisé via `app/components/plotly_theme.py::apply_tennis_theme(fig)`. Utiliser `st.plotly_chart(fig, use_container_width=True)`.
- **Logging** : `loguru` (messages français), jamais `print`.
- **Chemins** : `pathlib` + `ROOT_PATH` (cf. `.env.example`), jamais de chemins absolus codés en dur.
- **Cache Streamlit** : `@st.cache_data` pour lectures DuckDB et agrégations, `@st.cache_resource` pour la connexion DuckDB. **Toujours un `ttl=`** — un cache sans TTL fige les données jusqu'au redémarrage.
- **Fraîcheur des données (non négociable)** : toute fonction `@st.cache_data` lisant DuckDB prend `_DATA_KEY` (issu de `data_key(_ROOT)`) comme première clé de cache, **jamais `str(_ROOT)`**. `_ROOT` est constant : l'utiliser comme clé fait servir des données périmées après l'ingestion quotidienne. Cf. `app/components/_bootstrap.py::data_fingerprint` et `tests/test_data_freshness.py`.
- **Connexion DuckDB** : une seule par page, celle rendue par `init_app()` (`_ROOT, _CONNECTION = init_app(__file__)`). Ne jamais redéclarer un `@st.cache_resource def _connection()` local — il court-circuite l'invalidation.
- **Bootstrap pages** : chaque page Streamlit appelle `init_app(__file__)` depuis `app/components/_bootstrap.py` (gère `sys.path`, `.env`, connexion DuckDB cachée). Ne pas dupliquer le bloc d'init.
- **Composants UI obligatoires** : utiliser `page_header()` (pas `st.title` + `page_info`), `kpi_row()` (pas `st.columns` + `st.metric` recopiés), `section()` (pas `st.subheader` brut), `df_styled()` (pas `st.dataframe` direct — auto-détecte les `column_config` Elo / dates / pourcentages). Tous exposés depuis `app/components/widgets.py`.
- **Requêtes SQL partagées** : centraliser dans `app/components/queries.py` (`player_options`, `tournaments_for_circuit`, `latest_match_per_circuit`). Ne jamais redéfinir `_player_options` dans une page.
- **Selectbox circuit unifié** : utiliser `circuit_selectbox()` de `app/components/widgets.py` (constante `CIRCUITS = ("Tous", "ATP", "WTA")`). Toute concaténation SQL passe par `circuit_filter_sql()` qui valide via allowlist.
- **Tests** : toute fonction de calcul métier (Elo, features, pipeline) doit avoir une couverture pytest.

## Git & CI

- Commits : **Conventional Commits en français** (`feat: …`, `fix: …`, `chore: …`).
- CI (`.github/workflows/ci.yml`) lance ruff + black + pytest avec `--cov-fail-under=40` sur Python 3.11. Si la CI fail sur le linter, fixer le code, **pas la config**.
- **Valider avec les versions épinglées**, pas celles résolues localement : la CI installe `ruff==0.7.4` et `black==24.10.0`. Une règle plus récente ajoutée à `pyproject.toml` (ex. un ignore `RUF046`) fait échouer le *parsing* de la config sur 0.7.4 — pas seulement le lint. Contrôle avant push :
  `uv run --isolated --with 'ruff==0.7.4' ruff check src app tests`
- Workflow `daily_ingest.yml` actif (cron 04:00 UTC) : **commit direct sur `main`** des nouveaux parquets (plus de PR à merger). Un contrôle de non-régression refuse toute chute > 10 % du volume de `matches`/`players`.
- Workflow `healthcheck.yml` (toutes les 6 h) : ping l'app (variable de dépôt `APP_URL`) pour empêcher la mise en veille Streamlit Cloud, et ouvre/referme une issue `indisponibilite` automatiquement.
- **L'app déployée est privée** : sa racine renvoie un `303` vers l'authentification Streamlit alors qu'elle fonctionne normalement. Pour juger de sa santé, sonder `/healthz` (répond `200`) — ne jamais conclure à une panne sur la base du code retour de la racine.
- Workflow `keepalive.yml` (lundi 05:00 UTC) : GitHub désactive les crons après ~60 jours sans activité sur le dépôt, silencieusement. Il réarme ce compteur et ouvre une issue `cron-arrete` si l'ingestion est muette depuis > 48 h. `daily_ingest` ouvre de même une issue `ingestion-echec` en cas de panne. Ces deux issues se referment automatiquement au retour à la normale.
- Les parquets de `data/processed/` sont **volontairement versionnés** (~21 Mo total) pour Streamlit Cloud. Surveiller : la CI échoue si un parquet dépasse `MAX_PARQUET_BYTES` (défaut 100 Mo).

## Vérifier un changement de bout en bout

`pytest` ne charge aucune page Streamlit : une page peut être verte en test et
casser au runtime. Pour valider réellement (ce qui suit reproduit Streamlit Cloud,
qui installe via `pip install -r requirements.txt`, pas via `uv`) :

```bash
uv run python -m compileall -q app/          # syntaxe des 10 pages
uv run streamlit run app/Home.py --server.port 8599 --server.headless true &
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8599/Joueurs
```

Chaque page est atteignable par son nom sans le préfixe numérique
(`1_Joueurs.py` → `/Joueurs`, `9_Profils_et_Styles.py` → `/Profils_et_Styles`).

## Notes environnement

Si le projet est sous `~/Desktop` ou autre dossier sync iCloud, les opérations git/mmap peuvent échouer avec `Operation canceled`. Dans ce cas : `brctl download .` pour forcer le téléchargement local, ou déplacer le projet hors iCloud (`~/dev/`, `~/Code/`).

Autres symptômes iCloud observés sur ce dépôt — **toujours vérifier `git status` avant de commiter** :

- **Doublons de conflit** (`CLAUDE 2.md`, `sackmann_loader (1).py`) apparaissant en masse. Un `.github/workflows/daily_ingest 2.yml` non repéré serait exécuté par GitHub comme un second workflow actif. Nettoyage : supprimer ces fichiers, ils n'ont jamais de contenu utile.
- **Suppressions fantômes** : `git status` affiche tout le dépôt en `D` alors que les fichiers sont sur disque. Cause : un `.git/index.lock` orphelin d'un process git tué. Vérifier qu'aucun git ne tourne, supprimer le lock, puis `git reset`.
- **Fichiers évincés** : `data/raw/*.csv` peut afficher une taille alors que `du -sh` renvoie 0 B (placeholders). Le pipeline échoue alors localement — lancer l'ingestion via GitHub Actions plutôt que `brctl download` sur ~50 fichiers.
