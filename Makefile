.PHONY: sync frontend-sync api-types api-types-check lint typecheck test frontend-check frontend-build test-ollama test-google eval check build full demo demo-local demo-all test-browser web web-google docker-build

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

# Offline checks that the example repositories still present the shapes the review path is
# demonstrated on. No model, no answer key — the examples ship neither.
eval:
	uv run pytest -m "evaluation and not ollama"

# The standing example, run the way a visitor gets it: a repository with no case, judged in
# full, followed by the questions it came back with. Nothing is scored.
#
# Runs against Google by default: it finishes in about two and a half minutes where the
# local model takes four or five, which is the difference between a check you run on every
# change and one you run when you remember to. `make demo-local` runs the local model.
# Needs a live model either way, so both sit outside `check`.
demo:
	uv run python scripts/run_boundary_review.py --provider google --model gemini-3.6-flash

demo-local:
	uv run python scripts/run_boundary_review.py --provider ollama --model gemma4:26b

# Every example repository. Tens of model calls, so it runs on the local model: a metered
# free tier cannot serve it, and the workspace has no queue for work this long by design.
demo-all:
	uv run python scripts/run_boundary_review.py --all --provider ollama --model gemma4:26b

# `web` opens the workspace and lets it choose its own model, which is what a reader of
# this repository gets. `web-google` pins one for the length of the process, which is what
# a demonstration wants: it says which model produced what is on screen instead of
# inheriting whichever was last clicked. `--provider` and `--model` are global options on
# the app callback, so they go before the subcommand. After it, Typer rejects the whole
# invocation with "No such option".
# Both build the bundle first. The server serves its own frontend, so the two are one
# deployment and are correct only together — and they came apart three times in one week the
# same way: rebuild the bundle, leave the older server running, and the page then sends a
# field that process has never heard of. Restarting fixes it; building here means there is
# nothing to fix, and it costs about two seconds.
web: frontend-build
	uv run archcompass web

web-google: frontend-build
	uv run archcompass --provider google --model gemini-3.6-flash web

# Drives the built bundle in a real browser against a real server, with the model
# substituted. Outside `check` because it needs Playwright's chromium downloaded.
test-browser: frontend-build
	uv run pytest -m browser -v

# The bundle is built first because the test suite asserts on it: the cache-header test
# loads `/`, which answers `frontend_not_built` until the bundle is on disk. That is
# invisible on a machine that has already built one, and fails every time in CI.
# The hosted image, and one question asked of it: does a fresh visitor get a workspace? A
# container that builds and then cannot answer `/api/workspace` is the failure worth catching
# here, and the session cookie in that answer is what says hosted mode is actually wired up.
# The deterministic provider is used so the smoke test reaches no network and needs no key.
docker-build:
	docker build -t archcompass:local .
	@docker rm -f archcompass-smoke >/dev/null 2>&1 || true
	@docker run -d --rm --name archcompass-smoke -p 8088:8080 -e ARCHCOMPASS_PROVIDERS=fake archcompass:local >/dev/null
	@trap 'docker rm -f archcompass-smoke >/dev/null 2>&1' EXIT; \
	  headers=$$(mktemp); \
	  for attempt in $$(seq 1 30); do \
	    curl -fs -D $$headers -o /dev/null http://127.0.0.1:8088/api/workspace 2>/dev/null && break; \
	    sleep 1; \
	  done; \
	  grep -qi '^set-cookie: archcompass_session=' $$headers \
	    || { echo "The container answered without a session cookie:"; cat $$headers; exit 1; }; \
	  echo "docker smoke: /api/workspace answered 200 with a session cookie"

check: frontend-build lint typecheck test frontend-check

build: frontend-build
	uv build --no-sources

full: check test-ollama build
