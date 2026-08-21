# Architecture

ArchCompass separates product concepts, application capabilities, workflow, and
infrastructure.

```text
FastAPI / CLI / React
        |
        v
ports/capabilities.py <---- workflow/graph.py
        |
        v
stdlib dataclass domain
        ^
        |
persistence / reasoning / analysis / policies / repositories
```

The tree is organised by product concept, not by technical layer. Opening
`src/archcompass/` names what ArchCompass does:

| package | what lives there |
| --- | --- |
| `domain/` | the concepts: case, candidate, finding, review, decision, policy |
| `analysis/` | deterministic repository understanding — atlas, detectors, delta, queries |
| `policies/` | the policy corpus, its authoring, and retrieval over it |
| `reasoning/` | model judgement, questions, conversation, model selection |
| `workflow/` | LangGraph orchestration and the review use cases it produces |
| `persistence/` | durable workspace state, in SQLite |
| `repositories/` | getting a repository onto the machine and indexing it |
| `presentation/` | the HTTP API and the CLI |
| `ports/` | the narrow protocols that keep the arrows pointing inward |

Each feature keeps its concrete infrastructure in its own `adapters/` subpackage, and
nothing above that subpackage imports it.

The governing rule is:

> LangGraph owns workflow orchestration. LangChain supplies model and retrieval
> infrastructure. ArchCompass owns the domain.

## Responsibilities

- `domain/` contains frozen dataclasses, enums, typed identities, and invariants. It imports
  only the standard library and other domain modules.
- `ports/capabilities.py` defines the narrow capabilities the review graph is sequenced out
  of. A capability describes an ArchCompass operation without naming a framework.
- `workflow/graph.py` declares review sequencing, fan-out, clarification branching,
  interruption, and termination.
- `workflow/nodes.py` contains thin adapters. Each node invokes one capability and does not
  call downstream stages.
- `analysis/` performs deterministic repository analysis. `analysis/adapters/` holds the
  Python AST parser and the optional type oracle; `analysis/analyzer.py` converts analyzer
  records into domain candidates.
- `reasoning/adapters/` uses LangChain chat models and Pydantic structured responses.
- `policies/` owns the corpus and policy-selection strategies; `policies/adapters/` holds the
  Markdown parser and the vector index.
- `persistence/` converts between immutable domain snapshots and SQLite records.
- `repositories/` clones, fetches, and indexes the code under review.
- `presentation/` owns HTTP, CLI, and browser DTOs.

## Non-negotiable boundaries

The model never chooses what a verdict rests on, and never owns IDs, fingerprints,
persistence keys, or human decisions. Repository analysis and candidate detection are
deterministic. A `Finding` records ArchCompass's judgement; a `StandingDecision` separately
records what people chose to do.

There is one place where a model chooses what to look at, and it is narrow enough to state
in a sentence: **investigation decides whether to interrupt a person, never what a verdict
rests on.** A judgement that would stop the review to ask a question gets read-only atlas
lookups first, because many of those questions are ones the repository answers. Three things
keep it inside the boundary rather than beside it:

- every lookup is recorded on the review, so nothing a model found is unverifiable;
- the pass is never shown the policies at all, so a policy bearing cannot be added, moved
  or invented — there is nothing to cite;
- the revised finding is built with `dataclasses.replace`, so every field not named is
  carried untouched: the verdict may only leave `held`, and evidence and policies may not
  move at all.

The candidate set stays entirely deterministic. The detector chooses the work; the
application chooses which findings get a second look; the model chooses only which questions
to put to the repository about a finding it was handed.

**A model names what the application holds; it never indexes into it.** No list
ArchCompass assembles for a prompt is numbered for a model to point back into, because an
ordinal that is wrong but in range resolves to the wrong thing and reads as correct
afterwards. Two ways to satisfy it, and both are in `reasoning/adapters/langchain.py`. Where
one call handles one thing, do not ask: `LangChainQuestionGenerator` makes one call per held
finding, so the finding a question belongs to is the call it was made in. Where one call
spans many — a conversation citing several findings, a judgement citing several policies —
ask for the identifier and drop what the application does not recognise, which costs one
citation instead of the review. `tests/unit/test_boundaries.py` enforces it over every model
schema under `reasoning/`.

LangGraph checkpoint data is resumable execution state. It is not the domain history.
Immutable `Review` snapshots are the audit record.

Policy selection is accessed only through `PolicyRetriever`. Dense similarity, lane names,
authored priors, rerankers, and scores are implementation details, not domain concepts or
workflow inputs.

## Composition

`bootstrap.py` is the composition root. It selects concrete analyzers, repositories,
retrievers, models, and capability implementations, then builds the graph. Presentation
code receives the composed runtime and does not instantiate infrastructure.

The architecture is enforced by `tests/unit/test_boundaries.py`, which rejects
infrastructure imports from `domain/`, confines LangGraph to `workflow/` and the provider
SDKs to `reasoning/adapters/` and `policies/adapters/`, keeps a feature's logic away from
another feature's `adapters/`, and fails if `adapters/`, `application/`, or `boundary/`
ever reappear as top-level packages.
