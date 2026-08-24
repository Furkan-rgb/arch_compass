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

This is not cosmetic. It resolves `implements` edges by type rather than by name, and the
sole-implementation detector keys on exactly those — so installing it changes which
candidates a repository has, and therefore which findings a review produces. Whether it is
installed is decided by whether the import succeeds; there is no flag.

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
| **openrouter** | `OPENROUTER_API_KEY` | yes — 222 models, discovered live | yes — 5 models, `google/gemini-embedding-2` by default |
| google | `GOOGLE_API_KEY` | yes | yes — `gemini-embedding-2`, 3,072 dims |
| ollama | none, a reachable server | yes | yes — whatever installed model advertises the capability |
| fake | none | deterministically, without a model | deterministically |

`fake` is the offline provider the test suite and the Docker smoke check run on
(`ARCHCOMPASS_PROVIDERS=fake`). It is not a demo mode — it produces fixed output — and it is
listed here because it is in the registry, not because a deployment should offer it.

Credentials are read from the environment. A `.env` in the workspace — or in the working
directory — is loaded into it without overwriting anything already set, so a shell export
and CI always win.

**OpenRouter is the hosted boundary.** One credential reaches every model it lists, and
which upstream serves a request is its routing decision rather than a provider ArchCompass
knows about. Two things make that safe rather than merely convenient, and both are on every
request: `provider.require_parameters` refuses a route that cannot honour the JSON schema
the judgement is asking for, and the output ceiling travels as `max_tokens`, which is what
those routes declare. See `reasoning/adapters/openrouter.py`.

Its models are not listed here and there is no list of them in the code either. The
catalogue is the source of truth, filtered to what a review needs — a model that declares
both `structured_outputs` and `tools` — which was 222 of 422 when this was written. Routers
(`openrouter/…`), moving pointers (`~…-latest`) and batch-only ids (`…:batch`) are refused,
because each would break the promise that one model identity means one model.

Every provider is judged the same way: one candidate per `Send`, fanned out by LangGraph.
How many run together is LangGraph's business, not a setting here — there is no knob for it
and the one that used to exist reached only a path that no longer does.

Embedding selection is independent of reasoning selection: two choices, both required, and
the Models screen offers them separately. Changing the embedding model creates a different
content-addressed index namespace, and existing review provenance is unchanged by it.

**The shipped index and the default embedder are one decision.** Production retrieval never
generates a vector, so the file this package ships is the only source a review has, and
whichever identity it carries is the embedder that works without configuring anything. That
is `openrouter:google/gemini-embedding-2:3072` — the same Gemini model the index has always
been built from, reached through a different front door.

Any other embedder, Google's own included, needs its own index built first:

```bash
ARCHCOMPASS_EMBEDDING_PROVIDER=google ARCHCOMPASS_EMBEDDING_MODEL=gemini-embedding-2 \
ARCHCOMPASS_EMBEDDING_DIMENSIONS=3072 make policy-index
```

A review whose selected embedder has no index that applies is refused before it spends
anything on reasoning, naming the identity it wanted and the command that makes one.

## Environment variables

Everything ArchCompass itself reads. Nothing else is supported; a variable not on this list
does nothing.

### Credentials

| variable | meaning |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter, for judging and for embedding — **the default for both** |
| `GOOGLE_API_KEY` | Google, for judging and for `gemini-embedding-2` |

Each is named by its provider descriptor's `api_key_env`, never hardcoded at the call site.

### Any deployment

| variable | default | meaning |
|---|---|---|
| `ARCHCOMPASS_PROVIDERS` | all | comma-separated allow-list; narrows what is offered at all |
| `ARCHCOMPASS_OLLAMA_URL` | `http://127.0.0.1:11434` | moves the local Ollama server |
| `ARCHCOMPASS_HINGE_INVESTIGATION` | `1` | `0` skips the lookups a hinge gets before a person is asked |
| `ARCHCOMPASS_EMBEDDING_PROVIDER` | selected model's | pins the embedding provider |
| `ARCHCOMPASS_EMBEDDING_MODEL` | selected model's | pins the embedding model |
| `ARCHCOMPASS_EMBEDDING_DIMENSIONS` | selected model's | pins the embedding width |
| `ARCHCOMPASS_EMBEDDING_BASE_URL` | none | a self-hosted embedding endpoint |
| `ARCHCOMPASS_EMBEDDING_API_KEY_ENV` | none | *names* the variable holding the embedding key |

The five `ARCHCOMPASS_EMBEDDING_*` variables are a pin, not five independent knobs: set any
one and the workspace stops choosing an embedding model for itself.

Booleans accept `0`, `false`, `no` and `off` for the off state; anything else is on.

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

`create_hosted_app` refuses to start on three things, not one, and all three are deliberate —
a misconfiguration that waits to be discovered is discovered by visitors, one bad review at a
time:

1. `ARCHCOMPASS_HOSTED` unset or `0`.
2. No embedding pin, or a prebuilt index that does not match the pin. The hosted demo must
   serve every visitor the same index, so `ARCHCOMPASS_EMBEDDING_*` is required there and
   `verify(PREBUILT_INDEX, ...)` is run before the app exists.
3. Any enabled provider whose `api_key_env` is empty — by descriptor, not by naming Google.
   Narrow `ARCHCOMPASS_PROVIDERS` instead of leaving a key unset.

`ARCHCOMPASS_SOURCE_HOSTS` can only narrow the hosts the fetcher was built for; an unknown
name is refused at startup too. A new host needs a URL shape written into the adapter, so it
is a code change and not a variable.

The size limits are sized against a 1 GiB container together: 250 MB of source plus an
analysis peaking near 400 MB at the node cap. Raise them with the container's memory, not on
their own.

`Dockerfile` sets `ARCHCOMPASS_HOSTED=1`. `.github/workflows/deploy.yml` sets ten of these
for the Cloud Run deployment — the two run caps, the two fetch caps, `SOURCE_HOSTS`,
`PROVIDERS=openrouter` and the four embedding pins — and leaves the six size limits on their
code defaults. Its one secret is `OPENROUTER_API_KEY`.

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
| `make evaluation` | the `evaluation` dependency group and a local Ollama; executes the notebook in place |
| `make docker-build` | Docker; builds the image and smokes it the way `deploy.yml` starts it |

`make full` is `check`, `test-ollama` and `build`.

`make examples` is **not** a gated suite despite looking like one. `pytest`'s default marker
filter deselects `ollama`, `google` and `browser` and nothing else, so the `examples` tests
already run inside `make check`; the target is a way of running only those, not a way of
running ones `check` skipped.

`make evaluation` is the exception that is genuinely outside: it needs the `evaluation`
dependency group and a local Ollama with `embeddinggemma`, and it executes the notebook in
place.

The retrieval gate reads a recorded reference run and picks the smallest K that passes:

```bash
make evaluation      # writes evaluation/results/evaluation.yaml, among other things
uv run archcompass retrieval evaluate --from evaluation/results/evaluation.yaml
```

`--from` requires the file to exist and `evaluation/results/` is not committed, so the run
comes first. See [policy-retrieval.md](policy-retrieval.md) for the gate's thresholds and
[evaluation/README.md](../evaluation/README.md) for the harness.
