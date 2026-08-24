.PHONY: sync frontend-sync api-types api-types-check policy-index policy-index-check lint typecheck test frontend-check frontend-build test-ollama test-google examples evaluation check build full test-browser run dev web web-google docker-build

sync:
	uv sync --locked
	cd frontend && pnpm install --frozen-lockfile

frontend-sync:
	cd frontend && pnpm install --frozen-lockfile

api-types:
	uv run python scripts/generate_openapi_types.py

api-types-check:
	uv run python scripts/generate_openapi_types.py --check

# The shipped policy index: built where there is a key, checked everywhere. Building embeds
# the whole corpus and is the thing the file exists to avoid doing at run time, so it is not
# part of `check` and not part of CI — it runs when a policy changes, and the result is
# committed. The check is offline and is in `check`, because a stale index is invisible
# until somebody times a review on the deployment that depends on it.
policy-index:
	uv run python scripts/build_policy_index.py

policy-index-check:
	uv run python scripts/build_policy_index.py --check

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

# The end-to-end review with nothing hosted in it: a local Ollama judges and a local Ollama
# embeds, which is the deployment somebody evaluating this on their own source actually
# gets. Needs `qwen3.8:27b` and `embeddinggemma` pulled; anything missing skips with the
# `ollama pull` that would fix it rather than failing.
# It builds a policy index for the local embedder first, because the one this package ships
# was built with Google's embedder at 3,072 dimensions and vectors from two models are not
# comparable. That costs about forty seconds, once, and the whole suite is around four
# minutes on a 24 GB card.
# Outside `check` for the same reason `test-google` is: it depends on a live service.
test-ollama:
	uv run pytest -m "ollama"

# The end-to-end review, run against live services. Needs GOOGLE_API_KEY in `.env` and
# spends free-tier quota, and needs a local Ollama holding `embeddinggemma` — Google does the
# judging, Ollama does the embedding. The split is not arbitrary: the free tier allows 100
# embedded texts a minute and the policy corpus is 486 chunks, so retrieval would exhaust the
# minute before the first verdict. It also makes the sharper test of an invariant this product
# holds, that embedding selection is independent of reasoning selection.
# Outside `check` for the same reason `test-ollama` is: it depends on live services. Anything
# missing skips with a message rather than failing, including an exhausted quota — so a rerun
# a minute later is the fix, not a code change.
test-google:
	uv run pytest -m "google"

# Offline checks that the example repositories under `examples/cases` still present the
# shapes the review path is demonstrated on. No model, no answer key — they ship neither.
examples:
	uv run pytest -m "examples and not ollama"

# The retrieval evaluation, executed end to end and left with its outputs in place, so the
# committed notebook is a record of a run rather than a script somebody has to trust. Needs
# a local Ollama holding `embeddinggemma` and the `evaluation` dependency group, which is
# a Jupyter stack and therefore not installed by `make sync`.
# Outside `check` because it depends on a live service and takes a minute; the HTML is for
# reading the result without a kernel.
evaluation:
	uv sync --group evaluation
	uv run --group evaluation jupyter nbconvert --to notebook --execute --inplace \
	  --ExecutePreprocessor.timeout=1800 evaluation/retrieval-evaluation.ipynb
	uv run --group evaluation jupyter nbconvert --to html \
	  --output-dir evaluation/results evaluation/retrieval-evaluation.ipynb

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
run: frontend-build
	uv run archcompass web

web: run

web-google: frontend-build
	uv run archcompass --provider google --model gemini-3.5-flash-lite web

# The same two halves that `run` welds into one process, kept apart on purpose. `run` builds
# the bundle and lets the API process serve it, which is what a reader or a demonstration
# wants and what a person changing a component cannot work in: every edit costs a full
# `tsc -b && vite build` before it is on screen. `dev` starts the API on 8765 and Vite on
# 5173, where the `/api` proxy in `vite.config.ts` already points, so a save reaches the
# browser without a build.
# Open 5173, not 8765. The API process still serves whatever bundle is on disk, and in a
# working tree that bundle is stale by design — 8765 is the trap this target exists to avoid.
# Only the frontend reloads. `archcompass web` hands uvicorn an app object rather than an
# import string, so uvicorn cannot watch for it; a Python edit needs a restart of `make dev`.
# Ctrl-C stops both, and the trap stops the API if Vite exits first. Vite is ready in about
# a quarter of a second and uvicorn is not, so the first load can log one proxy
# ECONNREFUSED; a reload once the API line appears is the whole of it.
dev:
	@trap 'kill 0' EXIT INT TERM; \
	  uv run archcompass web --no-open --port 8765 & \
	  cd frontend && pnpm exec vite --open

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
# The image, started the way `deploy.yml` starts it. The embedding pin is not decoration:
# `create_hosted_app` refuses to boot without one, because the shipped index has to apply to
# every visitor — so a smoke that omitted it was testing that the container exits. It did,
# for as long as that check has existed, and nothing said so because this target is outside
# `make check`. `fake` for the reasoning provider keeps the smoke offline; the embedding pin
# needs no key to verify, only to use.
docker-build:
	docker build -t archcompass:local .
	@docker rm -f archcompass-smoke >/dev/null 2>&1 || true
	@docker run -d --rm --name archcompass-smoke -p 8088:8080 \
	  -e ARCHCOMPASS_PROVIDERS=fake \
	  -e ARCHCOMPASS_EMBEDDING_PROVIDER=openrouter \
	  -e ARCHCOMPASS_EMBEDDING_MODEL=google/gemini-embedding-2 \
	  -e ARCHCOMPASS_EMBEDDING_DIMENSIONS=3072 \
	  -e ARCHCOMPASS_EMBEDDING_API_KEY_ENV=OPENROUTER_API_KEY \
	  archcompass:local >/dev/null
	@trap 'docker rm -f archcompass-smoke >/dev/null 2>&1' EXIT; \
	  headers=$$(mktemp); \
	  for attempt in $$(seq 1 30); do \
	    curl -fs -D $$headers -o /dev/null http://127.0.0.1:8088/api/workspace 2>/dev/null && break; \
	    sleep 1; \
	  done; \
	  grep -qi '^set-cookie: archcompass_session=' $$headers \
	    || { echo "The container answered without a session cookie:"; cat $$headers; exit 1; }; \
	  echo "docker smoke: /api/workspace answered 200 with a session cookie"

check: frontend-build lint typecheck test frontend-check policy-index-check

build: frontend-build
	uv build --no-sources

full: check test-ollama build
