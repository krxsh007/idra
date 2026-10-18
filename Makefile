.PHONY: help up down test lint format mypy migrate seed roads eval smoke clean

PY := PYTHONPATH=api:. .venv/bin/python

help:  ## List available commands
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-8s %s\n", $$1, $$2}'

up:  ## Start db, api and web containers
	docker compose up -d

down:  ## Stop all containers
	docker compose down

migrate:  ## Create/upgrade the database schema
	cd api && ../.venv/bin/alembic upgrade head

seed:  ## Load users, facilities, resources, scenarios, knowledge base, roads, eval datasets
	$(PY) scripts/seed/seed_users.py
	$(PY) scripts/seed/load_facilities.py
	$(PY) scripts/seed/load_resources.py
	$(PY) scripts/seed/seed_scenarios.py
	$(PY) scripts/seed/ingest_kb.py
	$(PY) scripts/seed/load_road_network.py
	$(PY) scripts/eval/seed_eval_set.py

roads:  ## Rebuild the OpenStreetMap road graph and road tables only
	$(PY) scripts/seed/load_road_network.py

test:  ## Run the test suite (offline, fake LLM)
	PYTHONPATH=api:. .venv/bin/pytest tests/ -v

lint:  ## Ruff lint + format check
	.venv/bin/ruff check api/ scripts/ tests/
	.venv/bin/ruff format --check api/ scripts/ tests/

format:  ## Auto-format and fix lint issues
	.venv/bin/ruff format api/ scripts/ tests/
	.venv/bin/ruff check --fix api/ scripts/ tests/

mypy:  ## Static type check
	PYTHONPATH=api:. .venv/bin/mypy api/app scripts/

eval:  ## Run the evaluation harness and regenerate docs/evaluation.md
	$(PY) scripts/eval/run_eval.py

smoke:  ## Smoke-test a running stack
	bash scripts/smoke.sh

clean:  ## Remove Python caches
	find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
