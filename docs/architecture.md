# Architecture

How ArchCompass is structured, and why. The execution flow has its own document —
[workflow.md](workflow.md) — and runtime configuration is in
[operations.md](operations.md). What the product is *for* is [the charter](charter.md).

## The one idea

> **The application decides what to examine. The model decides what it means. Nothing the
> model writes is ever used as a key.**

Everything below is a consequence of that sentence. Deterministic analysis finds the
candidates; a model judges them; and the join between the two is always application-owned.

The last clause is narrower than it sounds and the narrowness matters. A model may **name**
something the application holds — a policy identifier, a qualified name, a candidate id. It
may never return an **ordinal** into a list the application built: an out-of-range one is
fatal, and an in-range but wrong one resolves to the wrong thing and is recorded for ever as
a correct citation. A name has neither reading. It matches, or it visibly matches nothing,
and what matches nothing is refused or dropped.

`test_no_model_output_schema_asks_for_a_place_in_one_of_our_lists` is the guard: it sweeps
every Pydantic model under `reasoning/` and fails on a field named or suffixed `position`,
`index`, `indices` or `ordinal`. The two halves of "refused or dropped" are both real and
they are different acts — an unresolvable name in an investigation lookup comes back to the
model as a refusal naming the recovery step, while a policy the judge cites but was never
shown is logged and dropped, because a citation is a record of why and losing one weakens
that record where raising would destroy a review already paid for.

## The concepts

```text
ArchitectureCase                          RepositoryRef
  |                                           |
Question -> Answer                            v
  |                                     RepositoryAtlas
  |                                           |
  +---------------------> Candidate <---------+
                              |
Policy -----------------------+
                              v
                           Finding
                              |
                              v
                            Review                  StandingDecision
                              |                            ^
                         ReviewDelta                       |
                                                    (branch + candidate)
```

**`RepositoryAtlas`** is objective structure — modules, classes, functions, and the imports,
calls and implements edges between them — derived deterministically at one revision. It is
never a model's opinion.

**`Candidate`** is a structural pattern a detector found and thinks is worth judging. Three
detectors cover both directions a boundary can be wrong: an indirection hiding nothing,
knowledge with no owner, a concept escaped its package.

**`ArchitectureCase`** carries human intent, and only that: the answers a person gave to
questions a review asked. It once carried a free-text goal, then hand-authored constraints
and decisions; both were removed for the same reason. They were demanded before anyone had
seen a finding, so they were almost always blank, and where they were written they restated
the policies in a form nothing could retrieve against. Intent now enters when something
turns on it.

**`Finding`** is what a judgement made of a candidate: a verdict, its reasoning, the policies
it bears on, and the detector-selected evidence it rests on.

**`StandingDecision`** hangs off to the side on purpose. It is not a stage a finding passes
through — a review has no decisions field at all — and it is filed under branch and candidate
rather than under the review that raised it. That is what lets a decision outlive the finding
it answered, and what stops a team's disposition becoming an input to the next judgement.

`Candidate`, `Finding` and `StandingDecision` are three concepts and must not blur: what was
found, what was concluded, what was decided.

## The package tree

`src/archcompass/` is named for what ArchCompass does, not for technical layers.

| package | what lives there |
|---|---|
| `domain/` | the concepts above: frozen dataclasses, enums, invariants |
| `analysis/` | deterministic repository understanding — atlas, detectors, delta, queries |
| `policies/` | the policy corpus, its authoring, and retrieval over it |
| `reasoning/` | model judgement, questions, conversation, model selection |
| `workflow/` | LangGraph orchestration and the review use cases it produces |
| `persistence/` | durable workspace state, in SQLite |
| `repositories/` | getting a repository onto the machine and indexing it |
| `presentation/` | the HTTP API and the CLI |
| `ports/` | the two seams the review graph itself is sequenced out of |

Each feature keeps its vendor code in its own `adapters/`, and nothing above that subpackage
imports it. What a feature asks the outside world for is its own `ports.py`, beside the code
that asks. Top-level `ports/` holds only `capabilities.py` and `policy_retrieval.py` — what
the graph is built from — typed in domain terms alone.

There is no `application/`, `services/`, `helpers/`, `common/` or `utils/`. A generic bucket
is a second answer to "where does this live", which is the failure the tree exists to remove.
`test_the_layer_named_packages_are_gone` fails the build if a top-level `adapters/`,
`application/` or `boundary/` comes back, and asserts every feature package is still there;
the other bucket names are convention, not a guard.

## Dependency direction

Every package depends on `domain/`, and `domain/` depends on nothing. That is measured, not
asserted: an AST sweep in `test_boundaries.py` fails if any module under `domain/` imports
Pydantic, LangChain, LangGraph, FastAPI, SQLite, a provider SDK, or any other feature.

The heaviest edges are all inward:

```text
reasoning    -> domain  20     reasoning -> ports        9
workflow     -> domain  20     workflow  -> ports        6
persistence  -> domain  17     workflow  -> persistence  4
policies     -> domain  13     policies  -> reasoning    3   (embeddings are a model concern)
analysis     -> domain  11     analysis  -> reasoning    1   (the investigation contract)
presentation -> domain  11     ports     -> domain       3
```

Measured by AST over `src/archcompass`, counting modules rather than import statements.

`presentation/` reaches features through their services and never through their `adapters/`.
`bootstrap.py` is the one module whose job is choosing implementations, and it is exempt from
that rule because that is what a composition root is.

## Boundaries that are there for a reason

A protocol earns its place by owning a boundary, not by existing. Several here have one
implementation and are still right; several one-implementation protocols were deleted because
they owned nothing. Implementation count decides neither case.

**`ArchitectureJudge` is the only verdict authority.** It alone produces `material`,
`cleared` and `held`. There was briefly a second — the hinge investigation returned a verdict
of its own, which overwrote the judge's — and measured on a local model, four investigations
in twelve came back with a verdict their own reasoning argued against. The weaker room, which
sees policy titles rather than their guidance, could overwrite the stronger. The fix was not
a validator; it was taking the responsibility away.

**Investigation establishes facts; the judge decides what they mean.** Its lookups are
recorded with their arguments and exact answers, and they are *never* promoted into
`Finding.evidence`. Evidence is detector-selected. Observations are model-selected. Both may
bear on a verdict; neither may be mistaken for the other.

**The verdict is chosen, not inferred.** `FindingOutput.verdict` is
`Literal["material", "cleared", "held"]`, constrained by the structured-output runtime, and
`Verdict(output.verdict)` takes it as given. It used to be a boolean plus an optional hinge,
from which the application reconstructed the category — so the model never actually chose,
`material` with a hinge was silently downgraded, and `held` was the only outcome that
required volunteering a field. Over thirty-five judgements on fixed inputs the boolean chose
`held` not once; the word chose it fifteen times.

What the schema cannot carry is a cross-field rule, and the three there are — a `held` with
nothing to ask, a hinge on a verdict that has answered, a recommendation on a verdict that
may not make one — are all anchored on `verdict` rather than stated as "these two conflict".
A conflict rule can be satisfied from either side and the model picks which, which is how a
question the review needed got dropped instead of the verdict that was wrong. A schema
violation buys exactly one repair call quoting what broke, never a retry loop.

**Persistence is two protocols, not one.** `ReviewSnapshots` is the stored collection — read
it, remove one from it. `ReviewRecorder` is the graph's recording seam, one method, wrapped
by `CachingReviewRecorder`. They are different acts with different callers, and a decorator
depends on the second staying its own protocol.

**Policy retrieval is strategy-independent.** `PolicyRetriever` returns a `RetrievedPolicySet`
with provenance; nothing above it knows about dense scores, lanes or vector stores. See
[policy-retrieval.md](policy-retrieval.md).

**Provider SDKs live in two adapter packages** — `reasoning/adapters/` and
`policies/adapters/` — and a guard fails the build if one appears anywhere else. LangGraph is
confined to `workflow/`.

**Pydantic validates at the boundary; the domain uses its own types.** Records that cross
into HTTP, SQLite or a model's structured output are Pydantic; `domain/` is frozen stdlib
dataclasses with explicit constructors and invariants in `__post_init__`. A model's output is
validated at the edge and converted, never trusted inward.

## Persistence

Two stores, deliberately not one:

```text
review-checkpoints.db        LangGraph thread and checkpoint state — execution durability
workspace.sqlite3            repositories and atlases, case revisions, immutable reviews,
                             execution-to-review aliases, standing decisions, the finding
                             cache, conversations, model selection, retrieval provenance
```

A checkpoint id is never a review id. Domain lineage is repository and branch identity, a
sequence number, and `previous_review_id`. Checkpoints are released when a review ends;
reviews are immutable and kept.

Two details of that boundary are easy to break silently. **Every dataclass a checkpoint can
hold must be in `CHECKPOINT_RECORD_TYPES`** — anything unlisted comes back from
`JsonPlusSerializer` as a raw dict, and no workflow test would notice because they all use
`InMemorySaver`, which never consults the list; a guard walks `ReviewState`'s type hints and
fails on drift in either direction. And **a review listing never decodes a stored review**:
`ReviewSummary` is read out with `json_extract`, because the document behind it runs to
megabytes. It lives in `persistence/` rather than `domain/` for that reason — it is a shape
the store returns, not a concept the product has.

An immutable record is also a compatibility obligation: a review written months ago must
still open. That is why the frontend still reads tool arguments written under an older
vocabulary, and why a `termination` that was never recorded renders as unknown rather than as
anything else.

## Intentional complexity

Things that look like they could be simpler and should not be.

**`CaseReviser` has three methods** — `open`, `revise`, `seal` — because a revision has three
moments and only the graph knows which one it is in. One review keeps one revision however
many rounds it asks. Collapsing them made a review that asked twice occupy three revisions,
and made the number beside a review change while somebody was reading it.

**`supports_batch()` and `supports_tools()` are asked per dispatch, not at startup.** The
model is chosen while the process is running: the same graph judges through a batch this
afternoon and through Ollama this evening.

**The finding cache keys on identities that must agree.** Model identity, prompt identity,
retrieval identity and — since the second judgement exists — the investigation's identity. If
the two sides of any of those ever disagree, every candidate of every review reports
`ChangeCause.PROMPT` for ever. They are each computed in exactly one place for that reason.

**`InvestigationLookup` is deliberately not the port's `RecordedLookup`.** One is a domain
record on an immutable review; the other is the live transcript a loop is writing.

**Two judgement transports, one prompt.** A batched judgement and an interactive one must be
the same judgement — a review submitted as a batch is not allowed to have been asked a
different question — so the prompt is built in one place and both transports send it.
