# Operations

Running ArchCompass, configuring it, and verifying it. What it does is
[architecture.md](architecture.md); how a review executes is [workflow.md](workflow.md).

Requires Python 3.12, `uv`, Node.js and `pnpm`.

## Install

```bash
uv sync --locked
cd frontend && pnpm install --frozen-lockfile && cd ..
```

For type-aware edge resolution, add the optional pinned mypy adapter:

```bash
uv sync --locked --extra resolution
```

## Running it

```bash
make run     # build the frontend, serve on loopback, open a browser  (alias: make web)
make dev     # two processes: API on 8765, Vite on 5173 with /api proxied
```

`make dev` is the frontend loop: a saved component reaches the browser without a build.
Open <http://localhost:5173>. Only the frontend reloads — a Python change needs `make dev`
restarted, and 8765 keeps serving whatever bundle was last built.

Provider and model selection is stored per workspace and changed from the Models screen. A
single run can pin one instead:

```bash
uv run archcompass --provider google --model gemini-3.5-flash-lite web
uv run archcompass --provider ollama --model qwen3.8:27b web
```

`uv run archcompass --help` is the authoritative command surface. The flows that matter:

```bash
uv run archcompass repo index /path/to/repository
uv run archcompass review CASE_ID --repo /path/to/repository
uv run archcompass reviews list
uv run archcompass reviews show REVIEW_ID
uv run archcompass ci CASE_ID --repo /path/to/repository
```

The CLI runs the graph in-process. It makes no HTTP calls and does not need the server.

## Providers

| provider | credential | judges | embeds |
|---|---|---|---|
| google | `GOOGLE_API_KEY` | yes, in one batch by default | yes — `gemini-embedding-2`, 3,072 dims |
| ollama | none, a reachable server | yes | yes — whatever installed model advertises the capability |
| groq | `GROQ_API_KEY` | yes, concurrently | no |
| cerebras | `CEREBRAS_API_KEY` | yes, concurrently | no |
| fake | none | deterministically, without a model | deterministically |

`fake` is the offline provider the test suite and the Docker smoke check run on
(`ARCHCOMPASS_PROVIDERS=fake`). It is not a demo mode — it produces fixed output — and it is
listed here because it is in the registry, not because a deployment should offer it.

Credentials are read from the environment. A `.env` in the workspace — or in the working
directory — is loaded into it without overwriting anything already set, so a shell export
and CI always win.

Groq and Cerebras are reached the same way as each other, over OpenAI's chat API, and
neither serves embeddings: a run judging through one retrieves through Google or a local
Ollama.

Only Google is asked for every candidate at once. Every other provider — Ollama, Groq,
Cerebras — takes the graph's per-candidate `Send` fan-out, and how many of those run
together is LangGraph's business, not a setting here.

Embedding selection is independent of reasoning selection, and changing the embedding model
creates a different content-addressed index namespace. Existing review provenance is
unchanged by it.

## Environment variables

Everything ArchCompass itself reads. Nothing else is supported; a variable not on this list
does nothing.

### Credentials

| variable | meaning |
|---|---|
| `GOOGLE_API_KEY` | Google, for judging and for `gemini-embedding-2` |
| `GROQ_API_KEY` | Groq |
| `CEREBRAS_API_KEY` | Cerebras |

Each is named by its provider descriptor's `api_key_env`, never hardcoded at the call site.

### Any deployment

| variable | default | meaning |
|---|---|---|
| `ARCHCOMPASS_PROVIDERS` | all | comma-separated allow-list; narrows what is offered at all |
| `ARCHCOMPASS_OLLAMA_URL` | `http://127.0.0.1:11434` | moves the local Ollama server |
| `ARCHCOMPASS_GROQ_MODELS` | the descriptor's | comma-separated model ids to offer |
| `ARCHCOMPASS_CEREBRAS_MODELS` | the descriptor's | comma-separated model ids to offer |
| `ARCHCOMPASS_MODEL_CONCURRENT_REQUESTS` | the descriptor's (1 for Google) | see below — narrower than it looks |
| `ARCHCOMPASS_GOOGLE_BATCH` | `1` | `0` judges Google one candidate at a time |
| `ARCHCOMPASS_HINGE_INVESTIGATION` | `1` | `0` skips the lookups a hinge gets before a person is asked |
| `ARCHCOMPASS_EMBEDDING_PROVIDER` | selected model's | pins the embedding provider |
| `ARCHCOMPASS_EMBEDDING_MODEL` | selected model's | pins the embedding model |
| `ARCHCOMPASS_EMBEDDING_DIMENSIONS` | selected model's | pins the embedding width |
| `ARCHCOMPASS_EMBEDDING_BASE_URL` | none | a self-hosted embedding endpoint |
| `ARCHCOMPASS_EMBEDDING_API_KEY_ENV` | none | *names* the variable holding the embedding key |

The five `ARCHCOMPASS_EMBEDDING_*` variables are a pin, not five independent knobs: set any
one and the workspace stops choosing an embedding model for itself.

Booleans accept `0`, `false`, `no` and `off` for the off state; anything else is on.

`ARCHCOMPASS_GOOGLE_BATCH=0` is what to reach for when batches are refused often enough to
be the slower route — a batch is metered once rather than per candidate, at the cost of
taking as long as its slowest verdict.

`ARCHCOMPASS_MODEL_CONCURRENT_REQUESTS` reaches exactly one path: the loop
`SelectedLangChainJudge` falls back to when a Google batch is refused. Nothing else reads it.
The graph routes to the batch node only when the selected provider is Google, so every other
provider is already fanned out by LangGraph and never touches this number. Groq's and
Cerebras's own `concurrent_requests = 4` is unreachable for the same reason.

`ARCHCOMPASS_HINGE_INVESTIGATION=0` turns off the read-only lookups a hinged finding gets
before its question is put to a person. Each held finding otherwise costs up to twelve
lookups over up to twelve model calls, plus one further judgement if they found anything —
a rounding error on a hosted tier and minutes on one local GPU. Off, the workspace asks its
questions the way it did before the pass existed. It is not a model switch: the selection
does not change.

### Hosted deployment only

Read once, at startup, by `create_hosted_app`. A local run never reaches that module, so
none of these can affect one.

| variable | default | meaning |
|---|---|---|
| `ARCHCOMPASS_HOSTED` | **required** | must be `1`; the hosted entry point refuses to start without it |
| `ARCHCOMPASS_SESSION_ROOT` | `/tmp/archcompass-sessions` | where per-visitor workspaces are written |
| `ARCHCOMPASS_SESSION_CACHE` | `32` | how many workspaces stay open at once |
| `ARCHCOMPASS_SESSION_DAILY_RUNS` | `10` | reviews one visitor may start per day |
| `ARCHCOMPASS_GLOBAL_DAILY_RUNS` | `50` | reviews the instance will run per day |
| `ARCHCOMPASS_SOURCE_HOSTS` | empty | hosts a visitor may name a repository on; empty means examples only |
| `ARCHCOMPASS_SESSION_DAILY_FETCHES` | `5` | repositories one visitor may fetch per day |
| `ARCHCOMPASS_GLOBAL_DAILY_FETCHES` | `100` | repositories the instance will fetch per day |
| `ARCHCOMPASS_MAX_SOURCE_MB` | `64` | how large one fetched repository may be |
| `ARCHCOMPASS_MAX_TOTAL_SOURCE_MB` | `250` | how much fetched source the instance holds at once |
| `ARCHCOMPASS_SOURCE_TIMEOUT` | `120` | seconds a fetch may take |
| `ARCHCOMPASS_MAX_FILE_KB` | `2048` | largest single file analysed |
| `ARCHCOMPASS_MAX_FILES` | `1200` | most files analysed |
| `ARCHCOMPASS_MAX_PYTHON_MB` | `12` | most Python one repository may bring — the binding limit |
| `ARCHCOMPASS_MAX_NODES` | `8000` | most atlas nodes, at roughly 40 KB each |

`ARCHCOMPASS_SOURCE_HOSTS` can only narrow the hosts the fetcher was built for. A new host
needs a URL shape written into the adapter, so it is a code change and not a variable.

The size limits are sized against a 1 GiB container together: 250 MB of source plus an
analysis peaking near 400 MB at the node cap. Raise them with the container's memory, not on
their own.

`Dockerfile` sets `ARCHCOMPASS_HOSTED=1`, and `.github/workflows/deploy.yml` sets the rest
for the Cloud Run deployment.

## Verification

```bash
make check
```

The frontend build, generated OpenAPI type check, Ruff, Pyright (strict, `src` only), the
offline pytest suite, the frontend suite, and `policy-index-check` — which verifies the
shipped policy index still covers the corpus beside it. That last one is offline and cheap,
and it is in `check` because a stale index announces itself nowhere until somebody times a
review on the deployment that depends on it.

These are **not** in `make check` and will not tell you they are broken:

| target | what it needs |
|---|---|
| `make test-ollama` | a running Ollama with the models installed |
| `make test-google` | `GOOGLE_API_KEY` |
| `make test-browser` | Playwright browsers |
| `make examples` | nothing, but it is slow |
| `make evaluation` | the `evaluation` dependency group; executes the notebook in place |

`make full` is `check`, `test-ollama` and `build`.

The retrieval gate reads a recorded reference run and picks the smallest K that passes:

```bash
uv run archcompass retrieval evaluate --from <recorded-results>.yaml
```

**No such file is in the repository**, and `--from` requires one to exist, so this command
cannot be run from a fresh checkout. It is a maintainer's step over results they produced;
the measurement apparatus that produces them is `make evaluation` and
[evaluation/README.md](../evaluation/README.md). See
[policy-retrieval.md](policy-retrieval.md) for the gate's thresholds.
