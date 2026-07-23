.PHONY: sync lint typecheck test test-ollama eval check build full

sync:
	uv sync --locked

lint:
	uv run ruff check .

typecheck:
	uv run pyright

test:
	uv run pytest

test-ollama:
	uv run pytest -m ollama

eval:
	uv run pytest -m evaluation

check: lint typecheck test

build:
	uv build --no-sources

full: check test-ollama build
