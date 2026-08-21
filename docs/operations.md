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
make run
```

The command builds the frontend, starts the FastAPI application on loopback, and opens the
browser. `make web` is an equivalent alias. Provider/model selection is stored per
workspace. A run can be pinned explicitly:

```bash
uv run archcompass --provider google --model gemini-3.5-flash-lite web
uv run archcompass --provider ollama --model gemma4:26b web
```

Google requires `GOOGLE_API_KEY`. Its policy retriever uses Google's
`gemini-embedding-2` model at 3,072 dimensions by default and shares that credential, so a
Google run needs no separate embedding variables. Ollama requires a reachable local server
and installed model.

Groq and Cerebras are reached the same way as each other, over OpenAI's chat API, and need
`GROQ_API_KEY` and `CEREBRAS_API_KEY` respectively. Neither serves embeddings, so a run that
judges through one of them retrieves through Google or through a local Ollama — which is the
combination that exercises the whole workflow without a paid tier. Neither meters a batch
separately either, so judging there is the concurrent loop rather than the batch path, sized
by the provider's own `concurrent_requests` and overridable with
`ARCHCOMPASS_MODEL_CONCURRENT_REQUESTS`.

Embedding selection remains independent from reasoning selection:
`ARCHCOMPASS_EMBEDDING_PROVIDER`, `ARCHCOMPASS_EMBEDDING_MODEL`,
`ARCHCOMPASS_EMBEDDING_DIMENSIONS`, `ARCHCOMPASS_EMBEDDING_BASE_URL`, and
`ARCHCOMPASS_EMBEDDING_API_KEY_ENV` can override the defaults. Retriever evaluation is a
release check and does not require per-workspace approval.

The Models screen offers reasoning and embedding choices independently. When Ollama is
running, ArchCompass lists installed models that advertise the embedding capability and
uses the dimension reported in their model metadata. Changing the embedding model creates a
different content-addressed index namespace; existing review provenance remains unchanged.

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
uv run archcompass retrieval evaluate --from evaluation.yaml
```

The command tries K=8, 12, 16, and 20 and reports the smallest passing configuration for a
maintainer to record in the retriever's release version.
