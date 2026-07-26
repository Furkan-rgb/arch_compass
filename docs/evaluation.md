# Evaluation methodology

ArchCompass separates three kinds of evaluation because they answer different questions. Passing
one category must not be presented as evidence that another category passed.

## Workflow and evidence-integrity tests

The mandatory automated suite uses deterministic embedding and reasoning providers. It exercises
the real SQLite, `sqlite-vec`, policy, atlas, query, evidence-validation, report, and revision
paths without contacting a live model.

V1.2 deterministic acceptance requires the suite to establish that:

- stage orchestration and bounded query budgets work;
- the provider-leakage integrity case routes ownership and change-locality forces through
  different investigations, packets, policy retrievals, and analyses;
- the provider-context-assembly case surfaces a structural proxy and relevant policy without the
  problem statement naming the duplicated evidence-selection responsibility;
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

The deterministic reasoning provider deliberately contains fixture-oriented behavior for terms
such as providers, Qwen, voices, and premature abstraction. Its evaluation results therefore prove
workflow and evidence integrity, not general architectural judgment.

Its routing behavior is generic rather than fixture-specific: discovered forces are partitioned
into responsibility ownership, lifecycle/operations, change/evolution, and evidence-uncertainty
concerns when those categories are present. The provider-leakage integrity case requires separate
ownership and change/evolution packets with disjoint surfaced nodes and different retrieved-policy
sets. This asserts that the real per-cluster routing path executes; it does not make the fake
provider an architectural-quality benchmark.

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

Canonical benchmark inputs and their repository fixtures live under `eval/cases/<case>/`. They
define architectural questions and expected decision characteristics independently of any one
model:

### Greenfield audiobook

The case includes ingestion, text preparation, chunking, voice design and cloning, narration, one
local GPU, Qwen first, possible hosted providers, and resumable jobs. A strong answer preserves
stable workflow boundaries, puts provider variation under a clear owner, and avoids a universal
plugin platform. It must not invent repository evidence.

### Brownfield provider leakage

The synthetic Python fixture spreads Qwen voice knowledge across frontend, preflight, workflow,
provider, and root composition. A provider interface lacks capability discovery. A strong answer
uses located repository evidence, explains duplicated knowledge and change amplification, moves
discovery under a clear owner, and avoids broad speculative infrastructure.

### Premature abstraction

The fixture contains one directly called local formatter and two behavior tests. There is no
interface, factory, registry, configuration, or credible variation. A strong answer can recommend
keeping the implementation local and state what future evidence would justify revisiting it.

### Provider context assembly

The case asks only for factual, auditable questions about a completed report. It contains no
provider, adapter, replacement, transport, duplication, or context-assembly cue. Its repository
has one model-boundary implementation that reads several nested report fields, combines findings
and policies, and constructs a request mapping. A strong answer follows the located
`broad-input-boundary-preparation` proxy into a source excerpt, applies the semantic-context
ownership policy, and recommends an application-owned dossier because report and evidence rules
currently spill into transport code. It must distinguish the observed projection from the
advisor inference that responsibility should move.

These cases are architectural-quality benchmarks only when a real reasoning model's output is
assessed against their evidence discipline and decision rubric. Running the deterministic
provider over the same fixtures is still an integrity test. Automated structural assertions
such as valid citations are necessary, but exact keyword matches are not sufficient evidence of
architectural quality. Tests that perform an optional quality run should use the
`ollama` or `google` marker and record the model, prompt identities, configuration, and case
revision used.

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
make eval-local        # every brownfield example, on the local model
make demo-local        # the scored fixture only
make demo              # the scored fixture, on Google
```

`make eval-local` runs each bundled case that ships a repository, prints one line per
boundary as its verdict lands, then a table of per-example scores. An example without an
`expected.yaml` is reported as unscored rather than counted as a pass, and an abstraction the
key does not cover fails the run: a fixture that has drifted from its own answers would
otherwise produce a score that looks complete while measuring less than it claims.

It is a script, not a workspace button. Four examples are roughly thirty model calls, the
browser has no queue for work that long by design (master plan §18), and a metered free tier
cannot serve it.
