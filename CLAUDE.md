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

# Ingestion : archive Sackmann figée (data/reference) + tennis-data + ESPN → data/processed
uv run tennis-ingest                              # complet (rafraîchit aussi l'instantané tennis-data)
uv run tennis-ingest --offline                    # archive seule, sans réseau
uv run tennis-ingest --rebuild-archive            # régénère l'archive Sackmann depuis le miroir (ponctuel)

# Recalcul Elo + modèle ML (à lancer après ingestion ou après modif moteur Elo)
uv run python -m tennis_analytics.transformation.build_elo
uv run python -m tennis_analytics.transformation.build_model

# App Streamlit (lit la Release data-latest ; TENNIS_DATA_RELEASE_URL="" = data/processed local)
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
`modeling`, `db`) + `ids.py`, `publish.py` — les imports sont toujours qualifiés
(`from tennis_analytics.ratings.elo import ...`).

`app/` n'est **pas** un package installé : `app/Home.py` est le **routeur**
(`st.navigation(position="top")`) ; il insère `app/` dans `sys.path`, appelle
`st.set_page_config` (une seule fois) puis exécute la page choisie dans
`app/views/`. Les vues importent donc `components.*` directement. `E402` reste
toléré sur `app/**` (imports après le bootstrap du routeur).

Les `url_path` historiques sont conservés dans `PAGES` (`/Joueurs`,
`/Classements_Elo`, `/Insights`, `/Profils_et_Styles`, `/Definition_Elo`…) ;
une page supprimée devient une vue `visibility="hidden"` qui redirige
(`redirect_top20.py`). Ne pas casser ces URL.

`data/raw`, `data/interim` et `data/state` sont gitignorés. **`data/reference`**
(archive Sackmann figée, instantané tennis-data, alias joueurs) est versionné.
`data/processed` est une **copie de secours** versionnée : l'app sert en priorité
la Release GitHub `data-latest`, publiée par l'ingestion.

## Architecture — flux de données

```
data/reference/sackmann_*.parquet ─┐
tennis-data.co.uk (xlsx) ──────────┼→ data/processed/*.parquet → Release data-latest → app (cache /tmp) → vues DuckDB
ESPN (API, provisoire) ────────────┘   (matches, players,          (manifest SHA-256,     (v_*)
                                         rankings, elo*, modèle)     toutes les 3 h)
```

- **Identifiants** : WTA = id Sackmann + 1 000 000, nouveaux joueurs (hash du nom)
  à partir de 2 000 000 (ATP) / 3 000 000 (WTA) — cf. `src/tennis_analytics/ids.py`.
  Chaque `player_id` appartient à un seul circuit.
- **Ordre chronologique** : toujours `transformation/ordering.py::sort_chronologically`
  (date de tournoi, tournoi, tour, n° de match). Sackmann date tous les matchs d'un
  tournoi du lundi de début : trier sur la date seule mélange les tours.
- **Sources récentes** : `ingestion/recent.py`. tennis-data renvoie **403 depuis
  GitHub Actions** (Cloudflare) : en CI on réutilise `data/reference/recent/`,
  rafraîchi par une ingestion locale. Ne pas contourner ce blocage.

Le **runtime app ne lit pas pandas directement** : il passe par des vues DuckDB (`v_matches`, `v_players`, `v_elo_latest`, `v_player_names`) déclarées dans `src/tennis_analytics/db/duckdb_session.py:create_connection`. Modifier le schéma d'un parquet impose de réviser la vue correspondante.

## Pipeline ML — règles non-négociables

- **Split temporel obligatoire** (`temporal_train_test_split` dans `src/tennis_analytics/modeling/win_probability.py`). Un fallback `train_test_split` aléatoire a été retiré volontairement pour éviter le leakage : si le split temporel produit < 10 lignes, on lève `ValueError`. **Ne jamais réintroduire de shuffle**.
- Features assemblées en streaming dans `assemble_training_frame` : `h2h`, `surface_winrate`, `recent_form` sont calculées en ne regardant que les matchs antérieurs. L'ordre chronologique du DataFrame d'entrée est critique.
- Le bundle joblib (`data/processed/models/logreg_calibrated.joblib`) contient `{model, features, diagnostics}` — la page Méthodologie affiche calibration + poids des indicateurs depuis `diagnostics`. Régénérer le bundle après chaque modif du modèle.

## Moteur Elo — points sensibles

- `src/tennis_analytics/ratings/elo.py::EloEngine.prepare_for_match` applique la décroissance d'inactivité **de façon idempotente** via `state.last_decay_date`. Ne pas retirer ce garde-fou : sans lui, deux appels successifs pour la même date décrémenteraient deux fois.
- `match_uid` utilise le séparateur Unicode `§` (absent des données Sackmann) pour éviter les collisions de concaténation. Un `assert is_unique` garde l'invariant après dédup dans `src/tennis_analytics/transformation/pipeline.py`.

## Conventions code (cf. `.cursorrules`)

- **Langue** : UI Streamlit (`app/`), docstrings et commentaires en **français** (style Google). Identifiants Python en **anglais** (PEP 8).
- **Visualisation** : Plotly uniquement dans `app/`, jamais matplotlib/altair. Thème centralisé via `app/components/plotly_theme.py::apply_tennis_theme(fig)`. Utiliser `st.plotly_chart(fig, width="stretch")` (`use_container_width` est déprécié).
- **Logging** : `loguru` (messages français), jamais `print`.
- **Chemins** : `pathlib` + `ROOT_PATH` (cf. `.env.example`), jamais de chemins absolus codés en dur.
- **Cache Streamlit** : `@st.cache_data` pour lectures DuckDB et agrégations, `@st.cache_resource` pour la connexion DuckDB. **Toujours un `ttl=`** — un cache sans TTL fige les données jusqu'au redémarrage.
- **Fraîcheur des données (non négociable)** : toute fonction `@st.cache_data` lisant DuckDB prend `_DATA_KEY` (issu de `data_key(_ROOT)`) comme premier argument, nommé **`cache_key` — jamais préfixé `_`** (Streamlit ne hache pas les arguments `_…` : la clé serait ignorée). Jamais `str(_ROOT)`, constant. Cf. `_bootstrap.py::resolve_data_dir` et `tests/test_ids_and_ordering.py::test_cache_data_first_argument_is_hashed`.
- **Connexion DuckDB** : une seule par page, celle rendue par `init_app()` (`_ROOT, _CONNECTION = init_app(__file__)`). Ne jamais redéclarer un `@st.cache_resource def _connection()` local — il court-circuite l'invalidation.
- **Bootstrap pages** : chaque vue appelle `_ROOT, _CONNECTION = init_app(__file__)` (connexion cachée, invalidée à chaque nouvelle publication). Pas de `sys.path.insert` ni de `st.set_page_config` dans les vues : le routeur s'en charge.
- **Composants UI obligatoires** : utiliser `page_header()` (pas `st.title`), `kpi_row()` (`st.metric` bordés), `section()` (h2, `level=3` pour h3), `df_styled()` (pas `st.dataframe` direct — auto-détecte Elo / rang / % / dates ; hauteur ajustée aux petits tableaux). Tous dans `app/components/widgets.py`.
- **Design** : pas d'emoji dans les titres et libellés (icônes `:material/…:`), pas de couleur codée en dur dans le CSS (thèmes clair/sombre dans `.streamlit/config.toml`), couleurs de graphiques depuis `plotly_theme.py` (palette Okabe-Ito, tirets/hachures en plus de la couleur). Libellés FR via `surface_fr`, `level_fr`, `round_fr`.
- **Requêtes SQL partagées** : centraliser dans `app/components/queries.py` (`player_options`, `tournaments_for_circuit`, `latest_match_per_circuit`). Ne jamais redéfinir `_player_options` dans une page.
- **Circuit commun** : `circuit_selectbox()` (une fois par vue, juste après `page_header` : affiché dans la page, la barre latérale pouvant être repliée) — `segmented_control` partagé par toutes les pages (clé de session `circuit`, reflétée dans l'URL `?circuit=`). `include_all=False` ramène « Tous » à ATP. Toute concaténation SQL passe par `circuit_filter_sql()` (allowlist).
- **Joueurs par défaut** : `player_selectbox(..., default_player_id=top_player_ids(...)[0])` (n°1 Elo actif), jamais le premier nom alphabétique.
- **Tests** : toute fonction de calcul métier (Elo, features, pipeline) doit avoir une couverture pytest.

## Git & CI

- Commits : **Conventional Commits en français** (`feat: …`, `fix: …`, `chore: …`).
- CI (`.github/workflows/ci.yml`) lance ruff + black + pytest avec `--cov-fail-under=40` sur Python 3.11. Si la CI fail sur le linter, fixer le code, **pas la config**.
- Les versions des outils viennent de `[project.optional-dependencies].dev` (`ruff==0.17.5`, `black==26.10.1`), installées par la CI via `pip install -e ".[dev]"` : `uv run ruff`/`uv run black` utilisent donc les mêmes. Après une montée de version, régénérer `requirements.txt` (`make deps`) — Streamlit Cloud l'utilise.
- Workflow `daily_ingest.yml` (« Ingestion des données », cron `17 */3 * * *`) : ingestion → si `input_hash` change (données **ou** versions pandas/pyarrow/sklearn) : Elo + modèle → contrôles (`python -m tennis_analytics.publish check` : volume −10 %, dernier match qui recule) → **upload dans la Release `data-latest`** (manifest en dernier). Pas de commit par exécution ; copie de secours sur `main` au plus une fois par semaine. L'état ESPN cumulé voyage dans la Release (`state-*.parquet`).
- Workflow `healthcheck.yml` (toutes les 6 h) : ping l'app (variable de dépôt `APP_URL`) pour empêcher la mise en veille Streamlit Cloud, et ouvre/referme une issue `indisponibilite` automatiquement.
- **L'app déployée est privée** : sa racine renvoie un `303` vers l'authentification Streamlit alors qu'elle fonctionne normalement. Pour juger de sa santé, sonder `/healthz` (répond `200`) — ne jamais conclure à une panne sur la base du code retour de la racine.
- Workflow `keepalive.yml` (lundi 05:00 UTC) : GitHub désactive les crons après ~60 jours sans activité sur le dépôt, silencieusement. Il réarme ce compteur et ouvre une issue `cron-arrete` si l'ingestion est muette depuis > 48 h. `daily_ingest` ouvre de même une issue `ingestion-echec` en cas de panne. Ces deux issues se referment automatiquement au retour à la normale.
- Les parquets de `data/processed/` sont **volontairement versionnés** (~21 Mo total) pour Streamlit Cloud. Surveiller : la CI échoue si un parquet dépasse `MAX_PARQUET_BYTES` (défaut 100 Mo).

## Vérifier un changement de bout en bout

`tests/test_app_smoke.py` exécute chaque vue via le routeur (`AppTest` +
`switch_page`), pour chaque circuit : il attrape les exceptions, pas les défauts
visuels. Pour valider réellement (Streamlit Cloud installe via
`pip install -r requirements.txt`, pas via `uv`) :

```bash
uv run python -m compileall -q app/          # syntaxe des vues
uv run streamlit run app/Home.py --server.port 8599 --server.headless true &
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8599/Joueurs
```

Chaque page est atteignable par son `url_path` déclaré dans `app/Home.py`
(`/Resultats`, `/Joueurs`, `/Classements_Elo`, `/Profils_et_Styles`…).

## Notes environnement

Si le projet est sous `~/Desktop` ou autre dossier sync iCloud, les opérations git/mmap peuvent échouer avec `Operation canceled`. Dans ce cas : `brctl download .` pour forcer le téléchargement local, ou déplacer le projet hors iCloud (`~/dev/`, `~/Code/`).

Autres symptômes iCloud observés sur ce dépôt — **toujours vérifier `git status` avant de commiter** :

- **Doublons de conflit** (`CLAUDE 2.md`, `sackmann_loader (1).py`) apparaissant en masse. Un `.github/workflows/daily_ingest 2.yml` non repéré serait exécuté par GitHub comme un second workflow actif. Nettoyage : supprimer ces fichiers, ils n'ont jamais de contenu utile.
- **Suppressions fantômes** : `git status` affiche tout le dépôt en `D` alors que les fichiers sont sur disque. Cause : un `.git/index.lock` orphelin d'un process git tué. Vérifier qu'aucun git ne tourne, supprimer le lock, puis `git reset`.
- **Fichiers évincés** : `data/raw/*.csv` peut afficher une taille alors que `du -sh` renvoie 0 B (placeholders). Le pipeline échoue alors localement — lancer l'ingestion via GitHub Actions plutôt que `brctl download` sur ~50 fichiers.
