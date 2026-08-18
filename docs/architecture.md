# Architecture

ArchCompass separates product concepts, application capabilities, workflow, and
infrastructure.

```text
FastAPI / CLI / React
        |
        v
application capabilities <---- workflow/graph.py
        |
        v
stdlib dataclass domain
        ^
        |
SQLite / LangChain / deterministic analysis / policy retrieval
```

The governing rule is:

> LangGraph owns workflow orchestration. LangChain supplies model and retrieval
> infrastructure. ArchCompass owns the domain.

## Responsibilities

- `domain/` contains frozen dataclasses, enums, typed identities, and invariants. It imports
  only the standard library and other domain modules.
- `application/` defines narrow capabilities and use cases. A capability describes an
  ArchCompass operation without naming a framework.
- `workflow/graph.py` declares review sequencing, fan-out, clarification branching,
  interruption, and termination.
- `workflow/nodes.py` contains thin adapters. Each node invokes one capability and does not
  call downstream stages.
- `adapters/analysis/` performs deterministic repository analysis and converts analyzer
  records at the boundary.
- `adapters/models/` uses LangChain chat models and Pydantic structured responses.
- `adapters/retrieval/` implements policy-selection strategies and the vector index.
- `adapters/persistence/` converts between immutable domain snapshots and SQLite records.
- `presentation/` owns HTTP, CLI, and browser DTOs.

## Non-negotiable boundaries

The model never chooses repository elements to inspect and never owns IDs, fingerprints,
persistence keys, or human decisions. Repository analysis and candidate detection are
deterministic. A `Finding` records ArchCompass's judgement; a `StandingDecision` separately
records what people chose to do.

LangGraph checkpoint data is resumable execution state. It is not the domain history.
Immutable `Review` snapshots are the audit record.

Policy selection is accessed only through `PolicyRetriever`. Dense similarity, lane names,
authored priors, rerankers, and scores are implementation details, not domain concepts or
workflow inputs.

## Composition

`bootstrap.py` is the composition root. It selects concrete analyzers, repositories,
retrievers, models, and capability implementations, then builds the graph. Presentation
code receives the composed runtime and does not instantiate infrastructure.

The architecture is enforced by tests that reject infrastructure imports from `domain/`
and verify that graph nodes do not import one another.
