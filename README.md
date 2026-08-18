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
- pins source evidence and excerpts;
- calculates review deltas, succession, resurfacing, and addressed candidates;
- selects and resolves application-owned candidates and policies;
- persists provenance and immutable review snapshots.

The configured model:

- judges one application-selected candidate and policy set;
- explains the verdict and policy bearings;
- identifies unresolved uncertainty;
- proposes clarification questions through a validated structured response.

The model never chooses which repository elements to inspect and never owns identifiers,
fingerprints, persistence keys, or standing decisions.

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
  reviews, decisions, conversations, cache entries, model selection, and retrieval approval.
- `.archcompass/review-checkpoints.db` stores LangGraph execution checkpoints.

Checkpoint IDs are not domain IDs. Review lineage uses repository and branch identity,
sequence, and `previous_review_id`.

The runtime owns only `workspace.sqlite3`; unrelated database files in the state directory
are ignored. Starting ArchCompass creates the application database when it is missing, so
opening a workspace never requires a migration command.

## Providers

Reasoning adapters use LangChain structured output:

- Google: `ChatGoogleGenerativeAI`
- Ollama: `ChatOllama`

Embedding adapters are configured independently:

- Google: `GoogleGenerativeAIEmbeddings`
- Ollama: `OllamaEmbeddings`

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
uv run archcompass --provider google --model gemini-3.6-flash web
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

## Documentation

- [Current review flow](docs/current-flow.md)
- [Architecture](docs/architecture.md)
- [Domain model](docs/domain-model.md)
- [Review workflow](docs/workflow.md)
- [Policy retrieval](docs/policy-retrieval.md)
- [Persistence model](docs/persistence-model.md)
- [Operations](docs/operations.md)

Licensed under Apache-2.0.
