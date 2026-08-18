.PHONY: up down test lint format mypy migrate seed types clean

up:
	docker compose up -d

down:
	docker compose down

test:
	PYTHONPATH=api:. pytest tests/ -v

lint:
	ruff check api/ scripts/ tests/
	ruff format --check api/ scripts/ tests/

format:
	ruff format api/ scripts/ tests/
	ruff check --fix api/ scripts/ tests/

mypy:
	PYTHONPATH=api:. mypy api/app scripts/

migrate:
	cd api && alembic upgrade head

seed:
	PYTHONPATH=api:. python3 scripts/seed_users.py

types:
	@echo "Types generator will be configured in M3"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
