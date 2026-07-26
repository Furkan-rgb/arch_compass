.PHONY: sync frontend-sync api-types api-types-check lint typecheck test frontend-check frontend-build bundle-check test-ollama test-google eval check build full demo demo-local test-browser

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
	uv run pytest -m "ollama"

# Calls Google AI Studio, so it needs GOOGLE_API_KEY in .env and spends free-tier quota.
# Outside `check` for the same reason `test-ollama` is: it depends on a live service.
test-google:
	uv run pytest -m "google"

eval:
	uv run pytest -m "evaluation and not ollama"

# The standing example. Six boundaries the detector cannot tell apart and a case that
# makes three of them justified; prints one verdict per boundary against the known answer.
#
# Runs against Google by default: it finishes in about two and a half minutes where the
# local model takes four or five, which is the difference between a check you run on every
# change and one you run when you remember to. `make demo-local` uses config/models.yaml.
# Needs a live model either way, so both sit outside `check`.
demo:
	uv run python scripts/run_boundary_review.py --models-config config/models.google.yaml

demo-local:
	uv run python scripts/run_boundary_review.py --models-config config/models.yaml

# Drives the committed bundle in a real browser against a real server, with the model
# substituted. Outside `check` because it needs Playwright's chromium downloaded.
test-browser: frontend-build
	uv run pytest -m browser -v

check: lint typecheck test frontend-check bundle-check

build: frontend-build
	uv build --no-sources

full: check test-ollama build
