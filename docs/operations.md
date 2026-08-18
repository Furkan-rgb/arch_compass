# Running and verifying ArchCompass

ArchCompass requires Python 3.12, `uv`, Node.js, and `pnpm`.

## Install

```bash
uv sync --locked
cd frontend && pnpm install --frozen-lockfile && cd ..
```

For type-aware edge resolution, install the optional pinned mypy adapter:

```bash
uv sync --locked --extra resolution
```

## Local workspace

```bash
make web
```

The command builds the frontend, starts the FastAPI application on loopback, and opens the
browser. Provider/model selection is stored per workspace. A run can be pinned explicitly:

```bash
uv run archcompass --provider google --model gemini-3.6-flash web
uv run archcompass --provider ollama --model gemma4:26b web
```

Google requires its configured API-key environment variable. Ollama requires a reachable
local server and installed model. Embedding configuration is independent from reasoning
configuration, and production retrieval requires a passing approval for that embedding
identity.

## Useful CLI flows

```bash
uv run archcompass repo index /path/to/repository
uv run archcompass review CASE_ID --repo /path/to/repository
uv run archcompass reviews list
uv run archcompass reviews show REVIEW_ID
uv run archcompass ci CASE_ID --repo /path/to/repository
```

Use `uv run archcompass --help` for the authoritative command surface.

## Verification

```bash
make check
```

This builds the frontend, checks generated OpenAPI types, runs Ruff and Pyright, executes the
offline pytest suite, and checks the frontend. Optional live-provider and browser suites are
available as `make test-google`, `make test-ollama`, and `make test-browser`.

The retrieval gate consumes recorded reference results:

```bash
uv run archcompass retrieval approve --from evaluation.yaml
```

The command tries K=8, 12, 16, and 20 and records only the smallest passing configuration.
