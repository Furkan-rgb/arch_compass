.PHONY: sync frontend-sync api-types api-types-check lint typecheck test frontend-check frontend-build test-ollama test-google eval eval-local check build full demo demo-local test-browser web web-google

sync:
	uv sync --locked
	cd frontend && pnpm install --frozen-lockfile

frontend-sync:
	cd frontend && pnpm install --frozen-lockfile

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
	cd frontend && pnpm run check

frontend-build:
	cd frontend && pnpm run build

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
# change and one you run when you remember to. `make demo-local` uses the Ollama config.
# Needs a live model either way, so both sit outside `check`.
demo:
	uv run python scripts/run_boundary_review.py --models-config config/models.google.yaml

demo-local:
	uv run python scripts/run_boundary_review.py --models-config config/models.ollama.yaml

# Every brownfield example, scored where one ships answers. Tens of model calls, so it
# runs on the local model: a metered free tier cannot serve it, and the workspace has no
# queue for work this long by design.
eval-local:
	uv run python scripts/run_boundary_review.py --all --models-config config/models.ollama.yaml

# This repository is also a workspace, and it keeps a configuration per provider rather
# than one unnamed `models.yaml`. Two of them is not a default, so `archcompass web` says
# so instead of guessing; these targets are where the repository makes the choice.
# `--models-config` is a global option on the app callback, so it goes before the
# subcommand. After it, Typer rejects the whole invocation with "No such option".
# Both build the bundle first. The server serves its own frontend, so the two are one
# deployment and are correct only together — and they came apart three times in one week the
# same way: rebuild the bundle, leave the older server running, and the page then sends a
# field that process has never heard of. Restarting fixes it; building here means there is
# nothing to fix, and it costs about two seconds.
web: frontend-build
	uv run archcompass --models-config config/models.ollama.yaml web

web-google: frontend-build
	uv run archcompass --models-config config/models.google.yaml web

# Drives the built bundle in a real browser against a real server, with the model
# substituted. Outside `check` because it needs Playwright's chromium downloaded.
test-browser: frontend-build
	uv run pytest -m browser -v

check: lint typecheck test frontend-check

build: frontend-build
	uv build --no-sources

full: check test-ollama build
