.PHONY: sync frontend-sync api-types api-types-check lint typecheck test frontend-check frontend-build bundle-check test-ollama eval check build full

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

# The built bundle is committed so the workspace serves without a Node toolchain.
# This fails when it no longer matches frontend/, which is otherwise invisible until
# someone loads a stale page.
bundle-check: frontend-build
	git diff --quiet -- src/archcompass/presentation/web/static || \
		(echo "Committed frontend bundle is stale. Run 'make frontend-build' and commit the result." && exit 1)

test-ollama:
	uv run pytest -m ollama

eval:
	uv run pytest -m "evaluation and not architectural_quality and not ollama"

check: lint typecheck test frontend-check bundle-check

build: frontend-build
	uv build --no-sources

full: check test-ollama build
