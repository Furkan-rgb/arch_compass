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
`positions`, `index`, `indexes`, `indices` or `ordinal`. The two halves of "refused or dropped" are both real and
they are different acts — an unresolvable name in an investigation lookup comes back to the
model as a refusal naming the recovery step, while a policy the judge cites but was never
shown is logged and dropped, because a citation is a record of why and losing one weakens
that record where raising would destroy a review already paid for.

There was one join that was *not* made by matching a name — the Google batch path paired
`responses[index]` with `requests[index]` positionally, submitting a correlation key it never
read back. It went when the batch subsystem did, which is the cheapest way a defect ever
gets fixed.

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

**`RepositoryAtlas`** is structure derived deterministically at one revision, never a
model's opinion: ten node kinds from repository down to test function, and eight edge kinds —
`contains`, `imports`, `calls`, `inherits`, `implements`, `references`, `tests`, `configures`
— alongside metrics, module facts and signals. In the domain it is five tuples of
canonical-JSON strings rather than typed records, a migration boundary its own comment names;
anything that wants to *query* it validates them first.

"Objective" has one qualification the code makes itself: a metric declares its own
`MetricNature`, `MEASUREMENT` or `STRUCTURAL_PROXY`, because some of them stand in for
structure rather than measuring it.

**`Candidate`** is a structural pattern a detector found and thinks is worth judging. Three
detectors cover both directions a boundary can be wrong: an indirection hiding nothing,
knowledge with no owner, a concept escaped its package.

Detection runs over the whole repository every review; *judgement* does not. After the first
review only the changed and the new reach a model, and a finding for an unchanged candidate
is carried verbatim out of the previous review. A second review of a repository where
nothing moved is refused outright rather than charged for.

**`ArchitectureCase`** carries the answers a person gave to questions a review asked, and
one other thing: `policy_context`, which scopes *which policies are retrievable* for a user,
an organisation or a repository. That is not intent — it is the one field on the case a
person still sets directly, and it gates the scoped and required retrieval lanes. Intent
itself is answers. It once carried a free-text goal, then hand-authored constraints
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
reasoning    -> domain  15     reasoning -> ports        5
persistence  -> domain  14     workflow  -> ports        5
policies     -> domain  10     persistence -> repositories 4
analysis     -> domain  10     workflow  -> persistence  3
workflow     -> domain   9     analysis  -> persistence  3
presentation -> domain   7     policies  -> reasoning    3   (embeddings are a model concern)
repositories -> domain   7     analysis  -> reasoning    1   (the investigation contract)
```

Measured by AST over `src/archcompass`: how many modules in the left package import from the
right one. `bootstrap.py` is included, and it is the one module allowed to reach anywhere.

Inward is not the same as acyclic, and this graph is not a layer cake. `analysis` and
`persistence` import each other — persistence stores atlases and so is typed in analysis's
records, while analysis reads them back. That is a cycle between two packages and it is
deliberate; what the tree buys is that a *feature* is one place, not that the arrows form a
tree.

Routes reach features through their services and never through their `adapters/` — a guard
sweeps all of `presentation/web/` for it. Three modules are exempt and all three build a
runtime out of adapters, which is the job: `bootstrap.py`, the composition root; and
`presentation/web/{runtimes,hosted}.py`, which are composition roots for a session and for
the hosted app. Everything else under `presentation/` may see a service and nothing lower.

Only four features have an `adapters/` at all — `analysis`, `policies`, `reasoning`,
`repositories`. The rest reach nothing vendored.

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

**One hosted boundary, and no upstream vendors behind it.** OpenRouter is a provider like
any other here; which company serves a request is its routing decision, expressed as a
`provider` block on the request. There is deliberately no Google, Anthropic or OpenAI
abstraction beneath it, and no local list of its models — the catalogue is the source of
truth, filtered to what a review needs. Google, Ollama, Groq and Cerebras remain reachable
directly, beside it rather than under it.

Two guarantees ride on every OpenRouter request and both are load-bearing.
`provider.require_parameters` makes schema support a hard routing filter rather than a
preference, because a model's declared capabilities are a union across its endpoints and
five of twenty on one model do not honour a schema. The output ceiling travels as
`max_tokens` rather than `max_completion_tokens` for the same reason: it is what those
endpoints declare, and the two together route to nothing.

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

The sequence is **per branch**, not per branch and case: it is `previous.sequence + 1` off
the branch's latest review, so a review of a different case continues the branch's number
line rather than starting one. Every snapshot of one review shares that number — each round
it waited in, and the record it finished as — and `round` is what separates them.

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

**`supports_tools()` is asked per dispatch, not at startup.** The model is chosen while the
process is running: the same graph judges through Google this afternoon and through Ollama
this evening, and whether a hinge can be investigated is a fact about the model selected at
the moment the node runs.

**The finding cache keys on identities that must agree.** Model identity, prompt identity,
retrieval identity and — since the second judgement exists — the investigation's identity.
Each is compared against what the previous review recorded, and a disagreement is permanent
rather than transient: model identity makes every candidate report `ChangeCause.MODEL` for
ever, prompt identity `ChangeCause.PROMPT`, retrieval `ChangeCause.POLICIES` per candidate.
They are each computed in exactly one place for that reason.

**`InvestigationLookup` is deliberately not the port's `RecordedLookup`.** One is a domain
record on an immutable review; the other is the live transcript a loop is writing.

**Every transport sends one prompt.** A judgement must not depend on which transport carried
it — a review judged through Google is not allowed to have been asked a different question
from one judged through Ollama — so `judgement_prompt` is built in one place and every
adapter sends what it returns.
