# ArchCompass — Agent Orientation

ArchCompass is a local-first architecture advisor. It reviews the **boundaries** in an
existing Python repository (abstractions with exactly one implementation) and judges,
one model call at a time, whether each is earning its place given an **ArchitectureCase**
(the requirements, constraints, and expected future changes for one decision) and the
**whole policy corpus**. The output is an immutable **BoundaryReview** you can then ask
follow-up questions about.

Read this first, then `.agents/AGENTS.md` (binding invariants for the active milestone)
and `docs/master-plan.md` (authoritative direction) before substantial changes.

## The pipeline

```text
Python repo ──parse AST──▶ RepositoryAtlas (versioned, deterministic)
                                 │
ArchitectureCase (append-only    ▼
revisions)          ──▶  Detect FindingCandidates      [deterministic, complete sweep;
                                 │                      one detector: abstraction with
Policy corpus (markdown,         ▼                      exactly one implementation]
presented whole,    ──▶  Judge each candidate          [one model call per candidate:
never retrieved/ranked)          │                      candidate + case + all policies]
                                 ▼
                         Verdict per boundary          [material? + rationale + policy
                                 │                      bearings, answered by position]
                                 ▼
                         Compose BoundaryReview        [deterministic: BR-nnn assigned,
                                 │                      identity bound by position,
                                 ▼                      JSON + Markdown persisted]
                         ReviewConversation            [whole review per turn; answers
                                                        cite boundaries by position]
```

The one rule shaping everything: **the application decides what to look at, the model
decides what it means, and nothing the model writes is ever used as a key.** Policies and
boundaries are answered by position; identity is attached afterward by ArchCompass.

## History warning

The "consultation" workflow (clustered findings, recommendation reports, `/runs`,
`ConsultationRun`) was **replaced** by the boundary review (commit `b629814`). Anything
named "consultation" or "run" is the superseded era. The master plan, `.agents/AGENTS.md`
and the frontend describe only the current era (ADR-0006, workspace milestone 1).
Remaining era names are backend-only and deliberate: `ArchitectureCase` still carries
`current_recommendation`/`confidence`, `CaseRevision.event_type` still admits
`"consultation"`, `ports.reasoning.ReportConversationReasoner` keeps its old name, and
`domain/diagnostics.py` still codes cluster-era failures. Removing them is a separate
decision, not leftovers to tidy in passing.

## Layout

- `src/archcompass/domain/` — validated concepts, errors, finding detectors (pure
  derivations over an atlas). A numeric limit has one named home here
  (`MAX_QUESTION_CHARACTERS`); the prompt budget is derived from the configured context
  window in `adapters/models/structured.py`, never frozen.
- `src/archcompass/ports/` — interfaces for persistence, analysis, retrieval, reasoning.
- `src/archcompass/application/` — one module per job: `reviews`, `review_conversations`,
  `review_rendering`, `cases`, `bundled_cases`, `repository_index`, `atlas_queries`,
  `atlas_freshness`, `policies`.
- `src/archcompass/adapters/` — `analysis/` (AST, graph metrics), `models/` (provider-
  neutral stages in `structured.py`; Ollama/Google transports; deterministic test
  providers — adapters hold no domain rules), `persistence/` (SQLite), `retrieval/`
  (policy parsing; embeddings exist but are unused on the review path).
- `src/archcompass/presentation/` — `cli/` (Typer) and `web/app.py` (FastAPI, serves the
  built React bundle).
- `src/archcompass/bootstrap.py` — the only composition root.
- `src/archcompass/policies/` — the bundled policy corpus (markdown).
- `frontend/` — React + TS + Vite. Routes in `src/App.tsx`, pages in `src/pages/`,
  API client `src/api.ts`, generated contract `src/openapi.generated.ts`. Direction:
  `docs/workspace-design.md`; current state: `docs/web-workspace.md`.
- `eval/cases/` — bundled examples; `boundary-review` ships expected answers and is
  scored by `make demo`.
- `tests/` — default run excludes `ollama`, `google`, `browser` markers, so
  `make check` needs no live model.

## Commands

```bash
make check              # lint, types, tests, OpenAPI freshness — no model needed
make demo               # scored live run vs known answers (Google, ~2 min)
make demo-local         # same via Ollama
make api-types          # REQUIRED after changing a web route or response model
make test-browser       # Playwright against the built workspace
make frontend-build     # REQUIRED after frontend changes — the bundle is committed
uv run archcompass web  # serve workspace; frontend dev: npm run dev (5173 proxies 8765)
```

## Active milestone

The review-centred workspace (master plan §16), sequenced in
`docs/workspace-design.md` §7: subtraction → spine → case rail → visible run →
iterate loop. Implement one step per task; do not pull later steps forward.

## Traps

- FastAPI owns the browser API contract; a stale `openapi.generated.ts` fails `make check`.
- The built frontend bundle under `presentation/web/static` is committed; `make check`
  fails if it no longer matches `frontend/` — rebuild and commit it with UI changes.
- Frontend deps already include `js-yaml`, `react-hook-form`, `@hookform/resolvers` —
  don't add a second YAML or form library.
- Changing a prompt's text changes its identity (`adapters/models/prompt_contracts.py`),
  so bump the stage version deliberately; a review records the identity that ran.
- Domain models validate the current schema only; no legacy shims or upgrade validators
  (ADR-0002). Unparseable stored rows are reported, and the review is re-run.
- The binding per-milestone rules live in `.agents/AGENTS.md`.
