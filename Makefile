.PHONY: help install app ingest elo model rebuild lint format test cov check clean deps

# Cible par défaut : afficher l'aide.
.DEFAULT_GOAL := help

help:  ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Installe les dépendances (runtime + dev)
	uv sync --all-extras

app:  ## Lance l'application Streamlit
	uv run streamlit run app/Home.py

ingest:  ## Ingestion complète Sackmann (téléchargement + matérialisation)
	uv run tennis-ingest

elo:  ## Recalcule les ratings Elo
	uv run python -m tennis_analytics.transformation.build_elo

model:  ## Ré-entraîne le modèle de probabilité de victoire
	uv run python -m tennis_analytics.transformation.build_model

rebuild: ingest elo model  ## Pipeline complet : ingestion + Elo + modèle

lint:  ## Vérifie le style (ruff + black)
	uv run ruff check src app tests
	uv run black --check src app tests

format:  ## Formate le code (ruff --fix + black)
	uv run ruff check --fix src app tests
	uv run black src app tests

test:  ## Lance la suite de tests
	uv run pytest

cov:  ## Tests avec rapport de couverture
	uv run pytest --cov=src --cov-report=term-missing tests/

deps:  ## Régénère requirements.txt depuis pyproject.toml (Streamlit Cloud)
	@uv run python scripts/sync_requirements.py

check: lint test  ## Contrôle complet avant commit (lint + tests)

clean:  ## Supprime les artefacts de build et caches
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov build dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
