# Evaluation methodology

ArchCompass separates three kinds of evaluation because they answer different questions. Passing
one category must not be presented as evidence that another category passed.

## Workflow and evidence-integrity tests

The mandatory automated suite uses deterministic embedding and reasoning providers. It exercises
the real SQLite, `sqlite-vec`, policy, atlas, query, evidence-validation, report, and revision
paths without contacting a live model.

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

## Architectural-quality benchmark cases

Two cases live under `eval/cases/<case>/`, each a written case beside the repository it is
about and the answers it should reach. They are the whole set on purpose: a bundled example
is something a person will open and be shown the tool through, and an example nobody has
graded teaches whatever the model happened to say that day.

Both present the detector with the same shape six times — an abstraction with exactly one
implementation — so nothing in the structure separates the boundaries and only the case can.
They differ in what the case has to be read *for*, and a run can pass one while failing the
other.

### Task scheduler boundary review — `boundary-review`

Does this boundary absorb any variation at all? Three of the six sit in front of a change the
case says is coming (a second delivery channel, a hosted database, a substituted clock) and
three sit in front of one the case rules out — a format fixed by a downstream system, an
identifier fixed by contract, a settled configuration decision. A run that clears all six is
an abstraction generator; one that condemns all six is an abstraction destroyer. Neither is an
advisor, and the score tells them apart.

### Adding a second speech vendor — `speech-vendor`

Is this boundary in the right *place*? Here every boundary sits in front of variation that is
genuinely coming — a second speech vendor is under contract — so the reading that scored well
above clears all six. Three of them are drawn at the edge the change arrives at. The other
three are vendor-shaped seams cut into the web layer, the pre-flight checks and the narration
planner, each answering a question the case says belongs to whichever vendor is configured, so
each is a further place the second vendor has to be applied.

The case is written to give none of that away: it states the decision, the contracted change,
the constraints and the qualities that matter, and never names a defect, a fix, or the classes
the verdicts are about. `tests/evaluation/test_speech_vendor_fixture.py` fails if that
vocabulary reappears, because a case that states the finding grades the model on reading
rather than on judgement.

The repository also carries the leak the fixture is named for: one voice list written into
four modules, with a copy that has already drifted out of step. Nothing scores that today —
it is *repetition without ownership* (master plan §8A.3), the half of the detector catalogue
that is not built — and it is there so the fixture is ready the day it is.

### Keeping stock in step with the warehouse — `warehouse-sync`

*Did the advisor notice what the case does not say?* This example grades elicitation
(master plan §6C) rather than verdicts, and it is the only one whose case is deliberately
incomplete. It is detailed about how the service is bound and silent about exactly one
thing — whether a second warehouse is coming. Two of its five boundaries turn on that
silence, and the answer moves them in *opposite* directions: a second warehouse justifies
the feed port and condemns the vendor name that leaked into the operator's digest. The
other three are decidable from what the case already states.

A run that hinges all five has learned to hedge and tells a reader nothing about where to
look. A run that hinges none has spent the silence without noticing it. Both are failures,
and separating them from an advisor is what this example is for.

It grades through `elicitation.yaml`, not `expected.yaml`, and ships no verdict key at all.
Two of its verdicts are contingent by construction, so a scored answer for them would settle
in a key the exact question the case refuses to settle. What can be graded without doing
that is where the silence was noticed, plus one count: the two hinged boundaries rest on one
fact, so a run that consolidates asks once.

`tests/integration/test_elicitation_loop.py` holds the offline half — that the questions
reach the report grounded and numbered, that they render, and that answering one produces a
second review with nothing left open. It also asserts the fixture's own premise, so an
example edited to read better cannot quietly stop measuring anything.

Recorded so a later change has something to beat, on `gemma4:26b`, one run per
configuration:

| judge prompt | hinged | correct | asked (1 is right) |
| --- | --- | --- | --- |
| v8 | 5 of 5 | 2/5 | 5 |
| v9 | 4 of 5 | 3/5 | 3 |

v9 named two ways a stage hedges after it has read the case. One landed: hinging on whether
a *stated* constraint is permanent stopped. The other did not — both duplicated-constant
boundaries still hand back "are these one fact or two", which is the question the stage
exists to answer. Read these as one run each and not as a measurement of the difference:
the direction matches what v9 targeted, but nothing here separates a real gain from
run-to-run variance.

#### The same repository with no case at all

`--no-case` throws the example's case away and reviews its repository alone, which is what
a first-time user gets by pointing at their own code. Neither key applies — both were
written for the case as authored — so this reports rather than scores, and two opposite
failures are what it is watching for.

**Condemning everything.** An unwritten case justifies no boundary, and read as evidence
that means every boundary is unjustified. Measured before it was allowed: a thin
`speech-vendor` run condemned `AudioSink`, `SpeechProvider` and `BookStore`, three
boundaries the written case justifies. That is §3.1's failure shipped as the first thing a
new user sees, and judge prompt v10 exists to prevent it.

**Clearing everything.** The mirror image, and the one v10 introduced. On `warehouse-sync`
with no case, v10 condemned **0 of 5** and hinged **2 of 5** — no condemnation spree, but a
report that clears a constant genuinely stated twice for one reason and a vendor name
genuinely spelled out in a module with no business knowing it. A review that clears
everything on the strength of a case nobody wrote reads as approval nobody earned, which is
the same thing §3.1 says about a report that lists only problems, from the other side.

The tension is real and worth stating rather than tuning away: v9 says a hinge on every
boundary is worthless, and v10 says silence is an unknown. Both are right for the case they
were written against, and an empty case is where they pull hardest — nearly every verdict
genuinely does turn on something unstated, so *hinging widely and condemning little* is the
honest shape there, with the overview consolidating the hinges into few questions. v10
reaches the second half and not the first.

One failure survives every version from v8 to v10: both duplicated-constant boundaries hand
back "are these one fact or two" rather than deciding it, with the evidence in the code in
front of them. Three prompt revisions have not moved it, which points at a capability limit
on `gemma4:26b` for that discrimination rather than at wording.

These are architectural-quality benchmarks only when a real reasoning model's output is
assessed against them. Running the deterministic double over the same fixtures is an integrity
test and nothing more. Automated structural assertions such as valid citations are necessary,
but exact keyword matches are not sufficient evidence of architectural quality. Tests that
perform an optional quality run should use the `ollama` or `google` marker and record the
model, prompt identities, configuration, and case revision used.

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

Tests marked `ollama` use the models in `config/models.yaml`. They verify the live embedding
transport contract—batch shape, dimensions, finite values, and input sensitivity—and exercise a
complete structured consultation against the configured reasoning model.

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

## Scoring every example at once

```bash
make eval-local        # both examples, on the local model
make demo-local        # boundary-review only
make demo              # boundary-review, on Google
```

`make eval-local` runs each bundled case, prints one line per boundary as its verdict lands,
then a table of per-example scores. An example without an `expected.yaml` is reported as
unscored rather than counted as a pass, and an abstraction the key does not cover fails the
run: a fixture that has drifted from its own answers would otherwise produce a score that
looks complete while measuring less than it claims.

Read both scores, never their sum. The two examples ask different questions, and 9/12 across
the pair hides which of the two failure modes is live.

It is a script, not a workspace button. Twelve boundaries plus two summaries is fourteen model
calls, the browser has no queue for work that long by design (master plan §18), and a metered
free tier cannot serve it.
