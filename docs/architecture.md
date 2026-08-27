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
every Pydantic model under `reasoning/` and fails on a field whose name is one of the ordinal
words in that test's `_ORDINAL_NAMES`, or whose last underscore-delimited segment is one —
`policy_index` is refused and `subindex` is not, because the guard reads names as words rather
than as characters, and a field nobody separated is a field nobody meant. The words are not
copied here; they are
listed there, where they move with the sweep that reads them. The two halves of "refused or dropped" are both real and
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
asserted: `test_domain_imports_only_the_standard_library_and_itself` is an AST sweep that
fails if any module under `domain/` imports a vendor library, a port, or another feature
package. What counts as one is that test's `forbidden` tuple, whose feature half is derived
from `FEATURES` rather than typed out a second time. An earlier version of this sentence
listed the libraries by name and had already fallen behind that tuple.

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
with provenance; nothing above it knows about dense scores, lanes, vector stores — or that
retrieval now asks two queries and fuses them by rank, which changed nothing above the port.
See [policy-retrieval.md](policy-retrieval.md).

**Provider SDKs live in two adapter packages** — `reasoning/adapters/` and
`policies/adapters/` — and a guard fails the build if one appears anywhere else. LangGraph is
confined to `workflow/`.

**One hosted boundary, and no upstream vendors behind it.** OpenRouter is a provider like
any other here; which company serves a request is its routing decision, expressed as a
`provider` block on the request. There is deliberately no Google, Anthropic or OpenAI
abstraction beneath it, and no local list of its models — the catalogue is the source of
truth, filtered to what a review needs. Ollama is the local boundary beside it, and there
is no third: the direct Google, Groq and Cerebras integrations are gone, and the models they
served are reachable as OpenRouter catalogue entries.

**What rides on an OpenRouter request is a preference, not a filter.** Every parameter sent
ranks the endpoints that could serve it; none of them refuses one. So the output ceiling
travels as `max_tokens` rather than `max_completion_tokens` because that is the name those
endpoints declare — no endpoint of `google/gemini-3.5-flash-lite` declares the other, and a
parameter nothing declares ranks every route below the ones that do.

`provider.require_parameters` used to sit beside it, turning that preference into a hard
filter on the argument that a model's declared capabilities are a union across its endpoints.
It is gone. No judgement was ever observed to be served by an endpoint that dropped what was
asked, so the guarantee was never seen to be worth anything, while the filter was observed to
leave a request with no eligible route at all and 404 mid-experiment. The residual risk — a
route whose schema support is weaker than its model's catalogue row claims — is stated rather
than defended against, and it is loud when it happens, because the schema call raises.
`Finding.served_by` is what turns it from an argument into a query.

**A path built from anything a person supplied is checked before it is opened.** Nothing on
the live path does that today: every workspace join is a constant, and the one place a
user-supplied name reaches a filename — an authored policy — is protected twice, by
`policy_slug` reducing a title to `[a-z0-9-]` and by catalogue lookup refusing an id the
workspace does not already hold.

It is written here because the next feature that writes a user-named file into a workspace
will have no prior art to copy. Three checks, and the third is the one with no equivalent
anywhere in this repository: reject an absolute path or a `..` component; **reject a symlink
at every component of the path, not only at its end**; then resolve and re-assert
containment. A helper that did this was deleted rather than kept unwired, because dead code
that looks like a defence is worse than no defence — a reader assumes it is guarding
something. Reintroduce it at the boundary that needs it, and not before.

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

**Only a review awaiting human answers owns durable checkpoint state.** At runtime open,
rows left `running` by the departed process become failed, and terminal or orphaned
checkpoint threads are deleted. That reconciliation happens before a legacy database is
rewritten: compacting first once copied 56 GiB of dead execution state into a 16 GiB-and-
growing WAL before the web server could bind. The rewrite is followed by a truncating WAL
checkpoint, and the store has a 4 GiB SQLite page ceiling. Reaching the ceiling fails the
active review through its normal terminal path; it never turns checkpoints into a second
history store.

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
process is running: the same graph judges through OpenRouter this afternoon and through
Ollama this evening, and whether a hinge can be investigated is a fact about the model
selected at the moment the node runs.

**The finding cache keys on identities that must agree.** Model identity, prompt identity,
retrieval identity, the investigation's identity, the candidate and the case. Each of the
first three is also compared against what the previous review recorded, and a disagreement
there costs the verdict: the candidate reports `ChangeCause.MODEL`, `ChangeCause.PROMPT` or
`ChangeCause.POLICIES`, and is judged again. That is the right bill when the judge or the
corpus really moved, and it is paid once, because the re-judgement records the identity now
in force. What is never right is two derivations of the same fact disagreeing with each
other, which re-judges everything on every run for as long as the two are apart and spoils
every verdict recorded meanwhile. They are each computed in exactly one place for that
reason.

**All three of those comparisons are per candidate, and the other side of each is the record
that candidate's own verdict left** — the finding's two stamps, the manifest's fingerprint.
None of them is a fact about a review. `Review` carried `model_identity` and
`prompt_identity`, composed as the comma-joined set of its findings' stamps, and the delta
compared that joined string against the single identity `selection` reports. A set and a value
are not the same kind of thing: they matched only while every stored review held exactly one
stamp, and the first review to mix two made every candidate read changed on the next
revision — a whole review re-judged for nothing. Not for ever, though: re-judging stamps
every finding with the one identity in force, so the revision after that compares a set of
one against a single value and matches again. Measured on the wiring that carried the fields,
over the stored 7-finding review with three of its findings restamped to a second prompt
identity: `unchanged=0 changed=7`, then `unchanged=7 changed=0`. The bill is one review per
straddle, and the straddle is a reviewer switching model mid-review, which is a thing this
product invites them to do.
The fields are gone rather than better composed — there is nowhere left to write a
review-level identity, so there is nothing for a comparison to reach for. What that buys is
that the fan-out window becomes honest: judgement dispatches per candidate and `selection()` is
read per call, so a reviewer switching model mid-review re-judges the candidates the departed
model judged and carries the rest forward. `report.py` derives "judged by" from the findings
at the point of display, which is the only place that answer exists.

It is held from the source, in `test_boundaries.py`, by a pair of sweeps that is complete only
together — one over what may exist to be compared, one over where a comparison may stand.
Neither is described further here, for the reason the paragraph below gives about every other
sweep in that file: each states its own reach and its own limits in its docstring, beside the
code that decides them.

That place is `SelectedLangChainJudge.selection()`, and it answers with one record —
`JudgeSelection`: the selection, the model identity a finding produced under it carries, which
judge runs, what that judge stamps as its prompt, and whether it reaches a provider at all. The revision
calculator, the finding cache, the retriever's mode, the question generator, the synopsist
and the answerer are all handed that one method. There is no way to obtain one of those
answers without the rest, which is the whole design — the composition root used to hold three
callbacks that each re-read the selection at a different moment and each re-derived a fact
from it, and two of them derived it differently.

The last three of those six only need `deterministic`, and they got it from a helper in
`selected.py` whose body was the same expression `selection` tests — under a comment saying the
rule lived in one place. That is the defect written above, one branch away from the branch it
was written about, so the rule is now asked of the source, by the stand-in sweeps in
`test_boundaries.py` — the block of them sharing the `_STAND_IN_*` constants, starting at
`test_the_stand_in_provider_is_written_out_in_exactly_one_place`. It has to be a source test.
A re-spelled copy agrees with the original on every input, which is exactly why nothing caught
the last two.

How far those reach, and what they decline to reach, is not restated here, and that is the
point. This document described it twice and claimed more coverage than the sweeps had both
times. The correction that named the escaping spellings instead went stale the same day,
because a new sweep closed them while the correction was being written — and the number of
sweeps has moved since this paragraph was first typed, which is why no number is given. A
sentence describing a sweep is a copy of the sweep, and it drifts exactly the way the
duplicated identities above drifted: the test moves, the sentence does not.

Each of those tests states its own reach and its own limits in its docstring, beside the code
that decides them. Read them there, and run them for the verdict.

The identity is not a value the record carries. It is read off the judge class the record
names — `identity` on `DeepArchitectureJudge`, `LangChainArchitectureJudge` and
`DeterministicJudge` — because there is one prompt identity per judge, and the deep judge
sends tool descriptions and a tool contract the plain one never does. That distinction is
what the two previous fixes of this defect missed. Both made the two sides read one shared
constant; both held until a third judge arrived with a constant of its own, and every
candidate of every review then reported `ChangeCause.PROMPT` and was re-judged for as long as
that stood. A judge wired in without an identity of its own does not compile now, which a
shared constant could never enforce.

`identity` is deliberately not on the `ArchitectureJudge` protocol. What the graph holds is
`CachingArchitectureJudge`, a wrapper with no identity of its own that could only answer by
constructing a judge; widening the protocol would make every implementation claim an identity
so that one of them could report one.

**An identity nobody remembers to bump is the same defect as an identity that disagrees, and
the build refuses it.** The identity is hand-written, and hand-written means somebody has to
remember. Measured over the 400 commits of `main` at `769759a`, by loading each tree and
rendering its judge prompts rather than by reading its source for named constants: 15 commits
moved judge prompt text, 3 moved an identity with it, and 12 shipped a changed question under
a stamp that says nothing changed. Every finding judged under one of those twelve reads as
unmoved for ever, and the delta never revisits it.

`reasoning/adapters/prompt_inventory.py` assembles what each judge sends by *calling* the
real prompt builders, `scripts/judge_prompt_check.py` digests that, and `records.py` records
the digest on the line under the identity it was minted against. A mismatch fails `make
check`. It is the shape of `SQLiteDatabase._verify_unchanged`, and it is that shape on
purpose: neither replaces the hand-written key with a content hash, because a content hash
*as* the identity re-judges every stored finding at the user's expense the first time a
comma moves. Both keep the key and raise when the checksum beside it stops being true.

What the check watches and what the identity claims are not the same set, and the difference
is written down where the exclusions are made rather than restated here. The properties that
keep it usable are tests rather than prose: it fires on a prompt that moved, it stays quiet on
a source re-flow and on a relocation that render the same text, and every judge that stamps an
identity is found by importing it rather than by matching a spelling.

**A judgement has one identity, and it is a row's primary key rather than a recipe.**
`CachingArchitectureJudge.key` is the only enumeration of what a judgement depends on.
`SQLiteCoreFindingCache` stamps that key onto every finding it hands back, on
`Finding.cache_key`, and `record_sources` attaches a review to the row by putting the same
string back into a `WHERE cache_key = ?`.

There was a second enumeration until this: a `_finding_identity` hashed out of the stamps a
finding carries, so that a review could find a row whose bytes a later pass had changed. It
could not see the case — a finding records the model, prompt and retrieval that judged it,
never the case it was judged under — so a candidate judged under two cases was one identity.
Measured: 231 rows, 137 carrying an identity, 124 distinct; thirteen pairs, three of which
had reached different verdicts. `record_sources` matched `AND source_review_id IS NULL`, so a
review claimed whichever row of a pair was unclaimed.

The rule this establishes is the one the migration checksum established for
`schema_migrations`: where two things must name one value, do not write the name twice —
make one of them *be* the value. A better second hash is the fix that has already failed
twice here, once for the corpus fingerprint and once for the model and prompt identities,
because a second expression is a second place to forget a term. There is no second place now.
A term added to the key is carried into the cache's identity with no other edit, and the join
is on a primary key, so the first-null-wins race has nowhere to happen.

**A scope selection has one key, and nothing computes it.** The folders a repository is
reviewed without are stored under its canonical root path. Three readers used to work that
path out for themselves — the analyzer before a review, the index service before an analysis,
the freshness check after one — each carrying its own
`str(root.expanduser().resolve(strict=False))` beside a comment promising it matched the
others. It did match. A key that disagreed would not fail either: `get` returns `None`, which
reads as "nobody chose a scope", so the review re-reads the folders somebody excluded and its
fingerprint over that wider set of files marks the stored atlas stale on every open, for ever.

`AtlasSource.canonical_root` answers the question now, so the callers ask instead of guessing
and there is no second expression to keep in step. The rest of the rule is a source test.
`test_a_scope_selection_key_is_always_asked_for_and_never_spelled_out` walks every call to the
port in `src/`, follows each key back through the names and helpers that supply it — across
modules, since `RepositoryIndexService.scope` is reached from a web route — and admits two
shapes: the question put to the analyzer, or the answer read whole off a record written from
it. The same test also holds the question to one answerer: every `canonical_root` in `src/`
sits beside an `analyze` in the same class, because the answer's whole content is the string
that analyzer will stamp, and a helper of that name on a service is the hand-spelled key back
under a spelling the first rule cannot tell from the real one.

It has to be a source test, for the reason the stand-in sweep above has to be one. Six
re-spellings were run against it — including the two that survived the previous pass, one at
the call to `get` and one at the call to the private helper that forwards to it. None of them
changes what the code does: with this test deselected every one passes the whole unit suite,
and with it in place every one fails this test and nothing else.

**`Finding.served_by` is provenance, not an identity, and the difference is the point.** A
hosted gateway serves one model from several endpoints — `google/gemini-3.5-flash-lite` has
seven — and which one answered is its routing decision, taken per request. The response says
so and nothing used to keep it, so `model_identity` read the same whichever endpoint ran the
judgement and the record could not tell a sampler apart from a route. It is observed over the
span `SelectedLangChainJudge` holds the transport for, because a judgement is a conversation
of up to twenty-six requests and the gateway routes each of them separately.

It is in no key. Not the finding cache's — which is now the only one — and not anything the
revision delta reads: which endpoint answered is what happened to a judgement, not what the
judgement was asked, and a gateway balancing its load would otherwise re-judge every candidate
in the workspace. Recording is also not pinning — nothing chooses a route on the strength of it, for
the reason `openrouter.request_body` gives. Empty is the ordinary value: every finding stored
before the field existed, and every judgement made by a provider with one endpoint.

It leaves the application in two places and is rendered in one. The API sends it on every
finding, so a client that wants it has it; nothing in `frontend/src` reads it yet, and the
workbench does not show it. The Markdown report is what renders it — a **Served by** line in
the footer, under the same "say where it came from" rule that puts the model and the prompt
there — and it omits the line entirely when nothing named an endpoint rather than printing a
dash, because an empty slot beside a real one reads as a route that failed to be recorded,
which is a stronger claim than the record makes.

**`InvestigationLookup` is deliberately not the port's `RecordedLookup`.** One is a domain
record on an immutable review; the other is the live transcript a loop is writing.

**Every transport sends one prompt.** A judgement must not depend on which transport carried
it — a review judged through OpenRouter is not allowed to have been asked a different
question from one judged through Ollama — so `judgement_prompt` is built in one place and
every adapter sends what it returns.
