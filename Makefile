.PHONY: sync lint typecheck test eval check build

sync:
	uv sync --locked

lint:
	uv run ruff check .

typecheck:
	uv run pyright

test:
	uv run pytest

eval:
	uv run pytest -m evaluation

check: lint typecheck test

build:
	uv build --no-sources

