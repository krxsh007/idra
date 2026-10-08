.PHONY: up down test lint format mypy migrate seed eval smoke clean

up:
	docker compose up -d

down:
	docker compose down

test:
	PYTHONPATH=api:. .venv/bin/pytest tests/ -v

lint:
	.venv/bin/ruff check api/ scripts/ tests/
	.venv/bin/ruff format --check api/ scripts/ tests/

format:
	.venv/bin/ruff format api/ scripts/ tests/
	.venv/bin/ruff check --fix api/ scripts/ tests/

mypy:
	PYTHONPATH=api:. .venv/bin/mypy api/app scripts/

migrate:
	cd api && ../.venv/bin/alembic upgrade head

seed:
	PYTHONPATH=api:. .venv/bin/python scripts/seed_users.py
	PYTHONPATH=api:. .venv/bin/python scripts/load_facilities.py
	PYTHONPATH=api:. .venv/bin/python scripts/load_resources.py
	PYTHONPATH=api:. .venv/bin/python scripts/seed_scenarios.py
	PYTHONPATH=api:. .venv/bin/python scripts/ingest_kb.py
	PYTHONPATH=api:. .venv/bin/python scripts/seed_eval_set.py

eval:
	PYTHONPATH=api:. .venv/bin/python scripts/run_eval.py

smoke:
	bash scripts/smoke.sh

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
