> **Superseded.** This is the brief for the clean-break refactor, kept as a record of what
> was decided and why. It is not a plan: the work is done, several files it proposes were
> never created, and the `adapters/`, `application/` and `boundary/` packages it names are
> now ones `tests/unit/test_boundaries.py` fails the build over. Read
> [architecture.md](architecture.md) for the tree as it is.

Refactor the ArchCompass package structure to be feature-oriented / package-by-feature while preserving the current clean dependency boundaries and behavior.

Goal:
Make the filesystem reflect the ArchCompass mental model so a developer can navigate by product concept rather than by technical-layer vocabulary.

Do NOT redesign the application architecture.
Do NOT change workflow semantics, domain semantics, persistence behavior, API behavior, retrieval behavior, model behavior, or repository-analysis behavior unless required only to update imports.
This should be a structural refactor.

Target principles:

1. Keep `domain/` as the framework-independent domain model.
2. Keep `workflow/` as the LangGraph orchestration layer.
3. Organize deterministic repository understanding under `analysis/`.
4. Organize policy corpus, policy authoring, RAG/retrieval, ingestion, and retrieval evaluation under `policies/`.
5. Organize LLM judgement, question generation, conversation, model selection/catalog, and LangChain/provider integrations under `reasoning/`.
6. Organize durable application persistence under `persistence/`.
7. Organize repository acquisition/indexing/checkouts/source handling under `repositories/`.
8. Keep `presentation/` for API/CLI boundaries.
9. Keep narrow ports/interfaces where they provide real inversion-of-control value, but do not let `ports/`, `application/`, or `adapters/` become the primary way humans navigate the product.
10. Remove or greatly reduce generic top-level `application/`, `adapters/`, and `boundary/` buckets once their contents have clear feature homes.

Preferred conceptual structure:

src/archcompass/
├── domain/
│ ├── case.py
│ ├── repository.py
│ ├── atlas.py
│ ├── candidate.py
│ ├── policy.py
│ ├── finding.py
│ ├── decision.py
│ ├── review.py
│ └── values.py
│
├── analysis/
│ ├── analyzer.py
│ ├── detectors.py
│ ├── delta.py
│ ├── queries.py
│ └── adapters/
│
├── policies/
│ ├── corpus.py
│ ├── service.py
│ ├── retrieval.py
│ ├── evaluation.py
│ ├── ingestion.py
│ └── adapters/
│ ├── sqlite_index.py
│ ├── markdown.py
│ └── embeddings.py
│
├── reasoning/
│ ├── judge.py
│ ├── questioner.py
│ ├── conversation.py
│ ├── model_catalog.py
│ └── adapters/
│ ├── langchain.py
│ ├── google.py
│ └── ollama.py
│
├── workflow/
│ ├── graph.py
│ ├── nodes.py
│ ├── state.py
│ └── service.py
│
├── persistence/
│ ├── reviews.py
│ ├── cases.py
│ ├── decisions.py
│ ├── executions.py
│ └── sqlite/
│
├── repositories/
│ ├── service.py
│ ├── checkout.py
│ ├── sources.py
│ └── vcs/
│
├── presentation/
│ ├── api/
│ └── cli/
│
├── ports/
├── bootstrap.py
└── configuration.py

Important:
This structure is guidance, not a mandate to force every existing file into exactly one named file above. Preserve cohesion. If a feature needs several small modules, keep them.

Specific cleanup goals:

- Move current `adapters/analysis/*` into the `analysis/` feature.
- Move policy retrieval/index/Markdown policy infrastructure into `policies/`.
- Move LangChain chat-model, judge, question-generation, provider discovery, and model catalog infrastructure into `reasoning/`.
- Move SQLite repositories out of generic `adapters/persistence/` into `persistence/`.
- Move repository checkout/source/VCS behavior into `repositories/`.
- Remove the generic `boundary/` package where possible.
  - HTTP/Pydantic presentation schemas should live under `presentation/api/`.
  - provider/model catalog DTOs should live with the feature that owns them.
  - analyzer-specific DTOs should live with analysis if they are still necessary.
- Reduce the generic `application/` package by moving services into their owning feature.
- Rename vague files like `core_defaults.py`, `core_capabilities.py`, `core_ci.py` where a clearer feature-specific name is possible.
- Keep `bootstrap.py` as the composition root.

Dependency rules to preserve:

- `domain/` imports only stdlib/domain helpers.
- `domain/` must not import LangGraph, LangChain, Pydantic, FastAPI, SQLite, presentation, persistence, or concrete adapters.
- feature/application logic may depend on domain and ports.
- concrete adapters depend inward on ports/domain/application logic.
- presentation depends on application-facing services, not concrete persistence/vector/model implementations.
- LangGraph remains confined to workflow.
- LangChain/provider SDKs remain infrastructure/adapters under reasoning/policies, never domain.
- Policy retrieval remains behind the stable `PolicyRetriever` capability.
- `Candidate`, `ArchitectureCase`, `Finding`, `Review`, and the LangGraph graph must not depend on dense scores, BM25 scores, lane names, vector-store types, or provider-specific retrieval mechanics.
- checkpoints remain execution durability; Review remains domain persistence.

Do not change these existing architectural invariants:

- "The application decides what to look at. The model decides what it means. Nothing the model writes is ever used as a key."
- deterministic candidate detection remains outside the LLM
- StandingDecision remains separate from Finding
- clarification flow and rejudgement behavior remain unchanged
- waiting Review snapshot is persisted before LangGraph interrupt
- resume continues the same LangGraph thread
- retrieval remains strategy-independent
- embedding model selection remains separate from reasoning model selection

Execution approach:

1. Inspect the current package tree and produce a concrete move map before editing.
2. Identify each current module's owning feature.
3. Move modules mechanically.
4. Update imports in one coherent pass.
5. Delete obsolete empty compatibility packages/re-export files.
6. Do not create compatibility re-export layers unless absolutely necessary.
7. Update architecture/import-boundary tests to reflect the new locations.
8. Update docs that mention old paths.
9. Run the complete test/type/lint suite.
10. Do not leave both old and new structures in parallel.

Pay particular attention to preserving:

- LangGraph checkpoint serialization module paths. If moving dataclasses/types that are serialized in checkpoints, update the allowed msgpack module list and relevant tests carefully.
- SQLite persistence codecs/schema behavior.
- policy retrieval provenance.
- model-selection persistence.
- FastAPI response/request schemas.
- CLI imports.
- frontend/OpenAPI generation if backend schema locations affect it.

Expected result:
Opening `src/archcompass/` should immediately communicate this mental model:

domain ArchCompass concepts
analysis deterministic repository understanding
policies policy corpus and RAG
reasoning LLM judgement and questions
workflow LangGraph orchestration
persistence durable state
repositories repository acquisition/indexing
presentation API and CLI

Before finishing, show:

1. old top-level package tree
2. new top-level package tree
3. major module move map
4. any places where you intentionally deviated from the proposed structure and why
5. test/type/lint results

Do not use this task as an excuse to redesign behavior. The primary success criterion is navigational simplicity while preserving the current architecture and semantics.

Also implement end to end tests to verify full behavior (limit this to the backend, frontend will be taken care of as long as the backend does what it needs to do). Please use gemini flash lite as the model to test and their embedding model. I have a free tier account and the value in the .env file is for the free tier.
