.PHONY: sync frontend-sync api-types api-types-check lint typecheck test frontend-check frontend-build test-ollama eval check build full

sync:
	uv sync --locked
	cd frontend && npm ci

frontend-sync:
	cd frontend && npm ci

api-types:
	uv run python scripts/generate_openapi_types.py

api-types-check:
	uv run python scripts/generate_openapi_types.py --check

lint:
	uv run ruff check .

typecheck:
	uv run pyright

test:
	uv run pytest

frontend-check: api-types-check
	cd frontend && npm run check

frontend-build:
	cd frontend && npm run build

test-ollama:
	uv run pytest -m ollama

eval:
	uv run pytest -m evaluation

check: lint typecheck test frontend-check

build: frontend-build
	uv build --no-sources

full: check test-ollama build
