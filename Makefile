.PHONY: setup test lint typecheck check local deploy destroy

setup:
	uv sync --all-groups

test:
	uv run pytest --cov=incident_commander --cov-report=term-missing

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy

check: lint typecheck test

local:
	uv run uvicorn incident_commander.api:app --host 127.0.0.1 --port $${PORT:-8080}

deploy:
	./scripts/deploy_aws.sh

destroy:
	./scripts/destroy_aws.sh
