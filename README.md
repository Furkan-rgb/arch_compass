# ArchCompass

ArchCompass is an evidence-grounded software architecture advisor. It analyzes a Python
repository deterministically, identifies structural candidates that deserve architectural
judgement, evaluates them against the team's context and policies, and preserves the result
as an immutable review history.

It is not a code generator, linter, or autonomous repository agent. A candidate is not a
violation. ArchCompass assembles the evidence; the model judges what that evidence means;
people decide what to do about the finding.

## Mental model

```text
RepositoryRef -> RepositoryAtlas -> Candidate
                                      |
ArchitectureCase ---------------------+
                                      |
PolicyRetriever -> selected Policies -+
                                      v
                              ArchitectureJudge
                                      |
                                      v
                                   Finding
                                      |
                           clarification needed?
                              /              \
                     Question -> Answer       no
                              |                |
                    ArchitectureCase          v
                       revision             Review
                                               |
                                        StandingDecision
                                               |
                                        next ReviewDelta
```

The architecture follows one rule:

> LangGraph owns workflow orchestration. LangChain supplies model and retrieval
> infrastructure. ArchCompass owns the domain.

Python stdlib dataclasses model ArchCompass concepts. Pydantic validates HTTP, model, and
persistence-boundary data.

## How a review runs

[`workflow/graph.py`](src/archcompass/workflow/graph.py) is the canonical executable account
of a review:

```text
load context
  -> analyze repository
  -> detect candidates
  -> calculate delta
  -> retrieve policies and judge each candidate
  -> check what the repository settles
  -> generate questions
       | settled / CI / limit / early stop
       |   -> compose and persist Review -> END
       |
       ` questions
           -> persist awaiting Review
           -> interrupt
           -> resume with answers/skips
           -> create ArchitectureCase revision
           -> rejudge selected candidates
           -> generate questions again
```

Each graph node invokes one application capability. Sequencing, branching, fan-out,
interruption, and termination remain visible in the graph. Candidate retrieval and
judgement fan out through LangGraph rather than through a hidden application thread pool.

The initial correctness strategy rejudges every extant candidate after a case revision. It
is a replaceable `RejudgementSelector`, not a permanent domain rule.

## Deterministic and model-assisted work

ArchCompass deterministically:

- identifies repository, branch, commit, and content;
- parses source without importing or executing the reviewed repository;
- builds the atlas and its structural relationships, metrics, facts, and signals;
- detects candidates and assigns stable IDs;
- carries the relationships between a candidate's participants, and measurements that state
  their own nature and limits;
- pins bounded source excerpts, widened to include a definition's leading comment and
  captioned when they were truncated;
- calculates review deltas, succession, resurfacing, and addressed candidates;
- selects and resolves application-owned candidates and policies;
- persists provenance and immutable review snapshots.

The configured model:

- judges one application-selected candidate and policy set;
- explains the verdict and policy bearings;
- identifies unresolved uncertainty;
- puts bounded, recorded, read-only questions to the repository about a finding that would
  otherwise stop the review, and about a reader's own question afterwards;
- proposes clarification questions through a validated structured response.

The model never chooses which candidates are reviewed and never owns identifiers,
fingerprints, persistence keys, or standing decisions. The lookups are the one place it
chooses what to look at, and they decide whether a question is worth a person's time rather
than what a verdict rests on: the pass is never shown a policy list, so it cannot move a
bearing, and every call it makes is kept on the review and shown beneath the finding.

## Domain concepts

The primary frozen dataclasses live under [`domain/`](src/archcompass/domain):

- `ArchitectureCase`, `Question`, and `Answer` capture revisioned human context.
- `RepositoryRef` identifies what is reviewed; `RepositoryAtlas` describes its structure.
- `Policy` represents guidance independently of retrieval mechanics.
- `Candidate` represents a structural shape, not a violation.
- `Finding` records ArchCompass's judgement and evidence.
- `StandingDecision` separately records a human accept, waive, or park disposition.
- `Review` is the immutable audit snapshot; `ReviewDelta` records what changed.

The domain imports only the Python standard library and other domain modules. Infrastructure
records such as vectors, checkpoints, raw model replies, HTTP payloads, and database rows do
not enter it.

## Policy retrieval

`PolicyRetriever` is a swappable application capability. Its result contains selected
policies and generic provenance: retriever/version, corpus fingerprint, selected policy IDs,
optional embedding identity, query fingerprint, and opaque metadata.

The initial production strategy combines:

1. applicable scoped policies;
2. applicable required policies;
3. evaluated dense top-K retrieval;
4. deterministic deduplication and ordering.

Dense scores, prior scores, lane names, quotas, and reranker values are not required domain
fields or workflow assumptions. A hybrid, sparse, graph-based, or future retriever can be
swapped through configuration without changing `Candidate`, `Finding`, `Review`,
`ArchitectureJudge`, or the graph.

Before a retriever becomes the default, the evaluation harness checks recall, required and
scoped inclusion, complete bearing-set coverage, material-verdict regression, and
deterministic ordering. Full-corpus runs remain an evaluation oracle, not a production graph
branch.

## Clarification, revisions, and decisions

A review may ask up to three clarification rounds. Question equivalence derives from the
case facet and sorted supporting candidate IDs, not from model wording. Submissions may
answer, explicitly skip, omit questions (recorded as skips), or conclude early.

The waiting snapshot is persisted before LangGraph interrupts. Resumption uses the same
execution thread, creates a new immutable `ArchitectureCase` revision, and continues through
the visible graph.

`Finding` and `StandingDecision` are intentionally independent:

```text
Finding          = what ArchCompass concluded
StandingDecision = what the team decided to do
```

Decisions retain append-only history, require reasoning for waivers, and can carry through
deterministic candidate succession. They never alter model judgement.

## Persistence

ArchCompass uses separate storage roles:

- `.archcompass/workspace.sqlite3` stores repository analysis, case revisions, immutable
  reviews, decisions, conversations, cache entries, model selection, and retrieval provenance.
- `.archcompass/review-checkpoints.db` stores LangGraph execution checkpoints.

Checkpoint IDs are not domain IDs. Review lineage uses repository and branch identity,
sequence, and `previous_review_id`.

The runtime owns only `workspace.sqlite3`; unrelated database files in the state directory
are ignored. Starting ArchCompass creates the application database when it is missing and
applies pending schema migrations, so opening a workspace never requires a migration command.

ArchCompass does not reinterpret records an earlier schema wrote. When a persisted domain
record changes shape, a numbered migration retires what can no longer be read: derived
output — review snapshots, the finding cache, executions, conversations — is produced again
by re-running a review, while authored input such as case revisions and standing decisions is
kept. See [docs/persistence-model.md](docs/persistence-model.md).

## Providers

Reasoning adapters use LangChain structured output:

- Google: `ChatGoogleGenerativeAI`, keyed by `GOOGLE_API_KEY`
- Ollama: `ChatOllama`, against a local server
- Groq: `ChatOpenAI` against `api.groq.com`, keyed by `GROQ_API_KEY`
- Cerebras: `ChatOpenAI` against `api.cerebras.ai`, keyed by `CEREBRAS_API_KEY`

The last two share one transport, because the only things that differ between vendors of
OpenAI's chat API are an endpoint, a credential variable, a model list and how many requests
the tier will answer at once. Adding another is adding an `OpenAICompatibleProvider` to
`reasoning/adapters/openai_compatible.py`.

The models each of those offers are named rather than discovered. Judging is a structured
call against a JSON schema and a vendor's catalogue is full of models that will not honour
one, so the endpoint's listing is intersected with a list that has actually been judged
with. `ARCHCOMPASS_GROQ_MODELS` and `ARCHCOMPASS_CEREBRAS_MODELS` name others when a vendor
renames one between releases.

`ARCHCOMPASS_PROVIDERS` narrows which of them a deployment offers at all.

Embedding adapters are configured independently:

- Google: `GoogleGenerativeAIEmbeddings`, defaulting to `gemini-embedding-2` at 3,072
  dimensions and reusing `GOOGLE_API_KEY`
- Ollama: `OllamaEmbeddings`

Google therefore needs no separate embedding configuration. Advanced or self-hosted setups
can override `ARCHCOMPASS_EMBEDDING_PROVIDER`, `ARCHCOMPASS_EMBEDDING_MODEL`,
`ARCHCOMPASS_EMBEDDING_DIMENSIONS`, `ARCHCOMPASS_EMBEDDING_BASE_URL`, and
`ARCHCOMPASS_EMBEDDING_API_KEY_ENV`.

The Models screen lists embedding models separately from reasoning models. It discovers
installed Ollama models that advertise embedding support, reads their vector dimensions,
and persists the selected embedder for the workspace. Environment configuration pins the
embedding choice and takes precedence over the workspace selection.

The deterministic provider and full-corpus retriever support offline testing and evaluation.
Production retrieval refuses to spend reasoning budget when its required embedding/index
configuration has not passed the retrieval gate.

## Install and run

Requirements: Python 3.12, `uv`, Node.js, and `pnpm`.

```bash
uv sync --locked
cd frontend && pnpm install --frozen-lockfile && cd ..
make run
```

`make run` builds the frontend and starts the backend that serves it, then opens the browser.
`make web` is retained as an equivalent alias.

Run with an explicitly pinned provider/model:

```bash
uv run archcompass --provider google --model gemini-3.5-flash-lite web
uv run archcompass --provider ollama --model gemma4:26b web
```

Useful CLI commands:

```bash
uv run archcompass repo index /path/to/repository
uv run archcompass review CASE_ID --repo /path/to/repository
uv run archcompass reviews list
uv run archcompass reviews show REVIEW_ID
uv run archcompass ci CASE_ID --repo /path/to/repository
```

Use `uv run archcompass --help` for the complete command surface.

## Verify

```bash
make check
```

This checks generated API types, builds and type-checks the frontend, runs Ruff and Pyright,
and executes the offline pytest suite. Live provider and browser checks are separate:

```bash
make test-google
make test-ollama
make test-browser
```

`make test-google` is the end-to-end one: it drives a whole review over the HTTP API against
real services — a repository indexed, every candidate judged, a question answered, the review
resumed on the same graph thread, a decision recorded and a grounded follow-up asked. Google
does the judging and a local Ollama holding `embeddinggemma` does the embedding, which is also
the sharpest demonstration that the two selections are independent. Anything missing skips with
a message rather than failing.

## Documentation

- [Charter](docs/charter.md) — what ArchCompass is for, and the rules that settle a design argument
- [Current review flow](docs/current-flow.md)
- [Architecture](docs/architecture.md)
- [Domain model](docs/domain-model.md)
- [Review workflow](docs/workflow.md)
- [Policy retrieval](docs/policy-retrieval.md)
- [Persistence model](docs/persistence-model.md)
- [Operations](docs/operations.md)
- [Design system](docs/design-system.md) — the three typographic voices, the palette, and what enforces them
- [The experience](docs/experience.md) — what a person does in the workbench, in what order, and what each surface owes them
- [What each region on screen is called](docs/frontend-regions.md)

Licensed under Apache-2.0.
