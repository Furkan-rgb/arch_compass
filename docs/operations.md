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

The separate `.archcompass/review-checkpoints.db` contains resumable workflow state, not
completed review history. Startup keeps checkpoints only for reviews awaiting answers,
compacts stale space before serving, and enforces a 4 GiB database ceiling. If no unfinished
review needs to resume, the checkpoint database and its `-wal`/`-shm` sidecars may be removed
while ArchCompass is stopped; `.archcompass/workspace.sqlite3` must be kept.

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
knows about. Nothing on the request narrows that decision: every parameter sent is a
preference OpenRouter ranks routes by, and the output ceiling travels as `max_tokens`
because that is the name those routes declare. The hard filter that used to sit beside it,
`provider.require_parameters`, was removed after it left a request with no eligible route at
all and 404'd mid-experiment; what answered is recorded instead, so every finding carries
the endpoint that served it. See `reasoning/adapters/openrouter.py`.

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

Any other embedder — a local Ollama, or another of OpenRouter's five — needs its own index built first:

```bash
ARCHCOMPASS_EMBEDDING_PROVIDER=ollama ARCHCOMPASS_EMBEDDING_MODEL=embeddinggemma \
ARCHCOMPASS_EMBEDDING_DIMENSIONS=768 make policy-index
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

Each is named by its provider descriptor's `api_key_env`, never hardcoded at the call site.
There is one, because there is one hosted boundary. Ollama needs none.

### Any deployment

| variable | default | meaning |
|---|---|---|
| `ARCHCOMPASS_PROVIDERS` | all | comma-separated allow-list; narrows what is offered at all |
| `ARCHCOMPASS_OLLAMA_URL` | `http://127.0.0.1:11434` | moves the local Ollama server |
| `ARCHCOMPASS_EMBEDDING_PROVIDER` | selected model's | pins the embedding provider |
| `ARCHCOMPASS_EMBEDDING_MODEL` | selected model's | pins the embedding model |
| `ARCHCOMPASS_EMBEDDING_DIMENSIONS` | selected model's | pins the embedding width |
| `ARCHCOMPASS_EMBEDDING_BASE_URL` | none | a self-hosted embedding endpoint |
| `ARCHCOMPASS_EMBEDDING_API_KEY_ENV` | none | *names* the variable holding the embedding key |

The five `ARCHCOMPASS_EMBEDDING_*` variables are a pin, not five independent knobs: set any
one and the workspace stops choosing an embedding model for itself.

Booleans accept `0`, `false`, `no` and `off` for the off state; anything else is on.

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

### What bounds a review, and what does not

Worth knowing before reading a run that looks stuck, because the answer is mostly "nothing".

| bound | value | scope |
|---|---|---|
| `ReasoningModelConfig.timeout_seconds` | 360s | one model or embedding call |
| `ReasoningModelConfig.max_parallel_requests` | 1 on Ollama, 8 hosted | calls in flight at once, whole review |
| `retrying` defaults | 6 attempts over ~2 minutes | one call, across its retries |
| Cloud Run `--timeout` | 600s | one HTTP request |
| a whole run | **none** | — |

There is no wall clock on a review. A run that has stopped moving has stopped for a reason
that is not a timeout, and the three that have actually happened are worth naming.

The first is CPU. A review runs on a background thread — the POST that starts one returns 202
and the work continues after it — and Cloud Run's default is to allocate CPU only while a
request is being handled. Without `--no-cpu-throttling` that thread gets whatever the polls
buy it, a few milliseconds every second and a half, and a two-minute review does not finish
in any time worth waiting. Nothing errors; the counter simply does not move. `deploy.yml`
sets the flag, and the cost of setting it is that CPU is billed for an instance's whole
lifetime rather than only while it serves — bounded by `--max-instances 1`, and still zero
when the demo is idle, because nothing pins a minimum instance.

The second is a queue, and it is the reason `max_parallel_requests` is in the table above. A
review dispatches every selected candidate at once — one branch per candidate, forty-six of
them on this repository — and each branch is one request. Against a hosted API that is the
point. Against Ollama it is not: it starts one `llama-server` with one slot for a model this
size, so it answers the first request and queues the other forty-five, each of them spending
the 360 seconds it was given while it waits its turn. Measured here at about thirty-five
seconds a judgement, the tenth request is reached at five minutes and the eleventh past the
deadline — so the review reported nine judged, stopped moving, and had thirty-six timeouts
queued behind it. What it looked like from the outside was a stuck run at candidate 10 of 46;
what it was is most of a review that had already been paid for and could not be delivered.
The bound is what ends that, and one is the right number for the default local runner. Raise
it only alongside `OLLAMA_NUM_PARALLEL`, because the number that matters is how many the
runner serves at once and asking for more than that only rebuilds the queue.

The third is the counter itself, which used to say "Judging candidate 1 of 50" for the whole
of retrieval. Both halves of a candidate's turn are counted now, so a number that is not
moving means work that is not moving. That was written before it was true: the retrieval half
is streamed as a bare stage with its payload filtered away by the per-candidate subgraph's
output schema, and the code read the payload before the stage, so it counted nothing and
every review reported no retrievals at all. It counts the stage now.

One thing `--no-cpu-throttling` does not buy, so that nobody reads more into it than it says:
it keeps the thread running between requests, not the instance running between visitors.
Nothing pins a minimum instance, so an idle service still scales to zero and a review in
flight when that happens is lost. `--min-instances 1` would close that gap and bills an
instance around the clock to do it, which is the wrong trade for a demo idle most of the week.
So closing the tab is safe for a review of ordinary length and a gamble for a long one.

## The deployment's one-time setup

`.github/workflows/deploy.yml` points here for these and they were never written down, which
is how the deploy came to fail on a commit that passed CI: the OpenRouter migration added a
secret reference to the workflow, nothing granted the runtime service account access to it,
and every push to `main` since has built the container and then been refused at
`Creating Revision`.

```
ERROR: (gcloud.run.deploy) spec.template.spec.containers[0].env[11]
  .value_from.secret_key_ref.name: Permission denied on secret:
  projects/NNNNNNNNNNNN/secrets/archcompass-openrouter-api-key/versions/latest
  for Revision service account NNNNNNNNNNNN-compute@developer.gserviceaccount.com.
```

Read that message with suspicion. It says permission, and it is also what a secret that does
not exist looks like — Secret Manager answers a caller who cannot see a secret the same way
whether or not there is one, so the deploy cannot tell the two apart and neither can the
error. Here there was no secret: the migration replaced

    --set-secrets GOOGLE_API_KEY=archcompass-google-api-key:latest

with `OPENROUTER_API_KEY=archcompass-openrouter-api-key:latest` and created nothing. Ask
directly before reaching for a grant, where a 404 is a 404:

```bash
gcloud secrets describe archcompass-openrouter-api-key --project "$PROJECT"
```

`archcompass-google-api-key` is still there and nothing reads it. It can go once a deploy has
gone green without it.

Four repository variables carry the trust, and the workflow reads nothing else about the
project: `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_WORKLOAD_IDENTITY_PROVIDER` and
`GCP_SERVICE_ACCOUNT`. They are variables rather than file contents so that a fork deploys
nowhere and rotating the trust touches no commit.

The secret, and the grant the deploy actually needs:

```bash
PROJECT=arch-compass
NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"

# The secret the workflow mounts as OPENROUTER_API_KEY.
printf %s "$OPENROUTER_API_KEY" \
  | gcloud secrets create archcompass-openrouter-api-key \
      --project "$PROJECT" --data-file=- --replication-policy=automatic

# The account the *revision* runs as, which is not the account the deploy authenticates as.
# Cloud Run reads the secret at revision-creation time, so this grant is what the deploy is
# refused for — and the error names an account nothing in this repository mentions.
gcloud secrets add-iam-policy-binding archcompass-openrouter-api-key \
  --project "$PROJECT" \
  --member "serviceAccount:${NUMBER}-compute@developer.gserviceaccount.com" \
  --role roles/secretmanager.secretAccessor
```

Rotating the key is a new version of the same secret — `:latest` in the workflow means the
next revision picks it up, and running revisions keep the version they started with:

```bash
printf %s "$NEW_KEY" | gcloud secrets versions add archcompass-openrouter-api-key \
  --project "$PROJECT" --data-file=-
```

A deploy that fails this way leaves the previous revision serving, which is the safe outcome
and also the quiet one: the site keeps working, on the old build, and nothing says so except
a red mark in Actions. Whoever changes the secrets the workflow mounts owns checking that
the deploy after it went green.

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
| `make test-openrouter` | `OPENROUTER_API_KEY` with credit, and a local Ollama for the retrieval side |
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
