# Evaluation methodology

ArchCompass separates three kinds of evaluation because they answer different questions. Passing
one category must not be presented as evidence that another category passed.

## Workflow and evidence-integrity tests

The mandatory automated suite uses a deterministic reasoning provider. It exercises the real
SQLite, policy, atlas, query, evidence-validation, report, and revision paths without contacting
a live model.

V1.2 deterministic acceptance requires the suite to establish that:

- stage orchestration and bounded query budgets work;
- concern, atlas, policy, and claim references remain valid;
- discovery and clustering keep internal IDs application-owned, constrain model-facing force
  handles to a closed set, and map valid partitions back deterministically;
- facts, assumptions, repository observations, policy guidance, and inference remain distinct;
- focused analysis receives bounded packets, while cross-cluster synthesis receives their
  separate validated analyses rather than the raw packets, atlas, or source tree;
- greenfield consultation succeeds without repository evidence;
- “no abstraction” is representable as a first-class result;
- failed validation remains auditable and does not mutate the case;
- schema-v3 findings receive stable IDs and application-projected packet evidence, including exact
  ordered locations, metric values, signals, and policies;
- conversations are gated on successful runs and retain exact case/Atlas/policy pins;
- ID, exact-title, numeric/word ordinal, comparison, and unambiguous recent-message finding
  references resolve deterministically while ambiguity fails explicitly;
- action, finding, unique-node/path, policy, depth, excerpt-line, and serialized-character limits
  are enforced cumulatively across multi-action turns;
- relationships, ordered dependency paths, tests, concern implications, policy exceptions, query
  summaries, source excerpts, and unavailable reasons reach the reasoning provider;
- original-run and additional pinned-Atlas scope is assigned to each exact artifact, including
  mixed-scope results and new artifacts attached to previously known nodes;
- every factual direct-answer/supporting/uncertainty statement has validated support, and invented
  edge, metric, signal, excerpt, cross-run, or cross-cluster evidence is rejected;
- repair-once behavior, complete failed-attempt records, optimistic ordering, lightweight retrieval
  storage, and JSON/rendered-answer consistency are enforced;
- fixed 12-then-8 summary batches retain recent corrections, enforce monotonic coverage, and do not
  fail an already-persisted valid answer when summarization fails;
- counterfactual answers remain labelled/read-only and unsupported runtime questions do not
  invent telemetry.

The deterministic reasoning provider recognises none of the evaluation fixtures. It once
branched on their vocabulary — Qwen, voices, preflight, and the rest — which made part of the
deterministic tier an assertion about what the double remembered rather than about what the
pipeline did, so `tests/unit/test_boundaries.py` now fails if any of that vocabulary reappears
in it. What the double proves is workflow and evidence integrity; it proves nothing about
architectural judgment, because it exercises no judgment.

Tests marked `evaluation` belong to this deterministic category. Run them with:

```bash
make eval
```

They are also included in `make check` and in continuous integration.

The required conversation evaluation matrix covers finding summaries and details, qualitative
priority across all findings, comparisons, evidence/source traces, policy applicability and
exceptions, alternatives, scenarios, assumptions, implementation order, counterfactual
strengthening and weakening, unsupported runtime questions, additional structural retrieval from
the pinned Atlas, and long conversations with summary revisions. The exact
“Additional repository evidence retrieved during conversation” heading is part of the rendered
contract.

## Example repositories

Four repositories live under `eval/cases/<name>/`, each with an `example.yaml` naming it and
nothing else. There is no case beside them and no answer key. That is deliberate: an example
is what a visitor is shown the tool through, and the tool is a review that judges from code,
asks what it could not weigh, and concludes once it has been told. Shipping a written case
would hand over the answers and skip the flow; shipping expected verdicts would settle in a
key the questions the examples exist to raise.

What each one is for is a property of the repository, and the offline checks under
`tests/evaluation/` defend exactly that much: the shapes are still there, and nothing in
them is decidable by counting.

### Task scheduler boundary review — `boundary-review`

Six boundaries, each an abstraction with exactly one implementation, so the detector cannot
separate them at all. Whether any of them absorbs variation depends entirely on
circumstances nobody has written down — a second delivery channel, a hosted database, a
substituted clock, a format fixed by a downstream system — which is what a run has to ask
about.

### Adding a second speech vendor — `speech-vendor`

The same six-of-a-shape, asking about *placement* rather than existence. Three seams are at
the edge a second vendor would arrive at; three are vendor-shaped holes cut into the web
layer, the pre-flight checks and the narration planner, each answering a question that
belongs to whichever vendor is configured. The repository also carries the leak it is named
for: one voice list written into four modules, with a copy that has already drifted out of
step — *repetition without ownership*, master plan §8A.3.

### A second narration voice — `audiobook-studio`

The only example that exercises all three detectors, and the hardest. Under each repetition
detector one instance is a real finding and one is not, so nothing here can be settled by
learning that duplication is bad. Its adapters conform structurally rather than inheriting,
return concrete types where their ports declare abstract ones and widen signatures the ports
leave narrow — every shape that once made a real repository's boundaries vanish from the
sweep.

### Keeping stock in step with the warehouse — `warehouse-sync`

Five boundaries in a two-year-old service, and one fact that moves two of them in opposite
directions: a second warehouse would justify the feed port and condemn the vendor name that
leaked into the operator's digest. It is the example the elicitation loop is tested over,
because consolidation is visible in it — two boundaries resting on one unknown are one
question, not two.

`tests/integration/test_elicitation_loop.py` holds the offline half: that the questions reach
the report grounded and numbered, that they render, and that answering one produces a second
review with nothing left open.

### What a live run is read for

Nothing is scored. Two failures pull in opposite directions, and the output is read for both:

**Condemning everything.** An unwritten case justifies no boundary, and read as evidence
that means every boundary is unjustified. Measured before it was allowed: a thin
`speech-vendor` run condemned `AudioSink`, `SpeechProvider` and `BookStore`. That is §3.1's
failure shipped as the first thing a new user sees, and judge prompt v10 exists to prevent
it.

**Clearing everything.** The mirror image. One `warehouse-sync` run with no case condemned
**0 of 5** and hinged **2 of 5**, and this was written up as v10 having overshot. That claim
was not supported: a second run of the identical repository, model and prompt gave **2
condemned and 4 hinged**. What the pair shows is run-to-run variance large enough to swamp
the effect. It is recorded as a failure mode worth watching for — a review that clears
everything on the strength of a case nobody wrote reads as approval nobody earned — and not
as something measured.

The tension behind it is real and worth stating rather than tuning away: v9 says a hinge on
every boundary is worthless, and v10 says silence is an unknown. Both are right for what they
were written against, and an unwritten case is where they pull hardest — nearly every verdict
genuinely does turn on something unstated, so *hinging widely and condemning little* is the
honest shape there, with the questions consolidating those hinges into a few.

That variance is also the strongest argument for the two-pass flow (ADR 0010): a first pass
is unstable enough that its verdicts are not reported as findings at all. On `warehouse-sync`,
answering the questions moved **four of five** verdicts.

One failure survives every judge-prompt version from v8 to v10: both duplicated-constant
boundaries hand back "are these one fact or two" rather than deciding it, with the evidence
in the code in front of them. Three revisions have not moved it, which points at a capability
limit on `gemma4:26b` for that discrimination rather than at wording. Measurements recorded
here are one run per configuration and are not differences.

These repositories say something about architectural quality only when a real reasoning
model's output is read against them. Running the deterministic double over them is an
integrity check and nothing more. Tests that perform an optional quality run should use the
`ollama` or `google` marker and record the model, prompt identities and configuration used.

## Recorded replay tier

`tests/replay/` holds two complementary kinds of fixture. Hand-authored payloads prove the
contracts reject what they should. Recorded bundles under `tests/replay/recordings/` prove
the complement: that the pipeline still accepts what a real model actually produced.

A bundle is captured from one live consultation with `make capture-recordings
CASE=eval/cases/<name> NAME=<name>`, which needs a running Ollama. It stores each stage's
input, the raw response, and the prompt identity that produced it. Replay runs in the
default suite with no model.

Because prompt identities embed a content fingerprint, editing a prompt makes every
recording under it stale and the replay test fails with the re-capture command. Absent
recordings skip. Recordings are never hand-edited: a hand-written "recording" proves only
what its author expected.

A recording is evidence about the pipeline, never about architectural quality. It is one
model, one case, one moment. See [plans/quality-harness.md](plans/quality-harness.md).

## Optional live-model and transport evaluations

Tests marked `ollama` name the model they run against in the test itself, because that is
what the number they produce is about. They exercise a complete structured review against
that reasoning model, including the arity of a judgement's policy bearings against the
corpus it was presented.

The live clustering contract also uses deliberately opaque canonical force IDs and verifies that
the provider returns an exact partition after the adapter's constrained `F1`–`Fn` reference
mapping. Embeddings are not used for this assertion: vector similarity is appropriate for
open-corpus retrieval, not exact identity within an already supplied bounded set.

The existing live assertions target transport, schema, evidence, and stage-timing invariants. They
do not by themselves score architectural quality. Live quality evaluation should additionally use
the benchmark rubric above and remain opt-in because model availability, hardware, and duration
vary by workstation.

Run the optional live-provider tests with:

```bash
make test-ollama
```

Run deterministic checks, optional live tests, and the distribution build with:

```bash
make full
```

Continuous integration intentionally runs no Ollama tests. It verifies locked installs,
deterministic checks, frontend tests, and the production/package build.

## Running every example at once

```bash
make demo-all          # every example, on the local model
make demo-local        # boundary-review only
make demo              # boundary-review, on Google
```

Each run indexes an example's repository, starts a case with nothing in it, judges every
boundary and prints the verdicts as they land, followed by what the run came back asking.
The table at the end counts boundaries, material verdicts, hinges and questions — never a
score, because no example ships answers to score against. Three lines are printed under it
where they apply: every boundary condemned, hinges that became no question, and nothing
hinging at all. Each is a failure mode rather than a number.

It is a script, not a workspace button. Twenty-odd boundaries plus their summaries is tens of
model calls, the browser has no queue for work that long by design (master plan §18), and a
metered free tier cannot serve it.
