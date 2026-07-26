# Plan: advice-quality harness

> **Partly historical.** Written before the review path (master plan §6A) replaced the
> clustered consultation. The tiering argument still holds and the scored
> `eval/cases/boundary-review` fixture came out of it; the stage names and file paths do
> not describe the current code.

**Status:** Phase 1 implemented; Phases 2–4 planned
**Scope:** Evaluation tooling. No product surface.

## The problem

The deterministic suite proves the pipeline bounds, validates, composes and persists
correctly. Since WS7 it deliberately makes **no claim about advice quality** — the
substitute reasoner relays its inputs rather than judging, so a green suite says nothing
about whether a real model produces good architecture advice, or even whether it can
satisfy the contracts at all.

`pytest -m architectural_quality` collects **zero tests**. Quality is currently asserted
nowhere.

Running a full consultation per assertion is too slow to iterate on: a dozen model calls
plus indexing, embedding and retrieval. The unit worth testing is one reasoning stage
against one known input.

## Three tiers

| Tier | Model? | Cost | Catches | Run with |
|---|---|---|---|---|
| 1 — recorded replay | no | milliseconds | pipeline regressions against real model output | `make test` |
| 2 — live stage probe | one call | seconds | contract achievability, evidence discipline | `make probe` |
| 3 — full consultation | many calls | minutes | cross-stage coherence | `make test-ollama` |

Tier 3 already existed (`tests/integration/test_ollama.py`). Phase 1 delivers tier 1 and
the capture step that feeds every tier; Phase 2 delivers tier 2.

## What makes this possible

Every reasoning stage takes typed, provider-neutral, serializable input — `GlobalContext`,
`FocusedAnalysisPacket`, `ReportConversationContext`, and since WS3 a claim pool of
handles. That seam did not exist cleanly before WS2/WS3, when the adapter received half
the world. A stage input is now a JSON document, and a stage output is a typed proposal
with handle references rather than free prose, which is what makes assertions mechanical
rather than judgemental.

## Phase 1 — capture and replay *(implemented)*

`scripts/capture_recordings.py` runs one real consultation with a provider that keeps
every request and response, then writes a bundle under `tests/replay/recordings/<name>/`:
a manifest (pins, per-call task and prompt identity), `inputs.json` (the case, forces,
clusters, analyses, alternatives, scenarios, packets, and the exact node allowlist the
run validated against), and the raw response text per call.

`tests/replay/test_recorded_synthesis.py` replays the synthesis answer through
`validate_proposal` → `compose_recommendation` → `canonicalize_report_findings` →
`validate_report_evidence`, with no model running.

### Recorded, not reconstructed

A stage input could in principle be rebuilt from a stored run's pins — handles are
positional over stored lists, and `_global_context` is a pure function of case and atlas.
It was still the wrong choice: `atlas_overview()` carries its own caps and limitation
prose, so a reconstructed fixture would silently follow later edits to that code. **A
fixture that tracks your changes cannot detect them.** The recorded bytes are what the
model actually saw.

Persisting `GlobalContext` on `ConsultationRun` was also rejected. An optional field is
the soft contract ADR 0002 removed; a required one is permanent product surface, entering
the OpenAPI schema and the committed frontend types, for a reader that is a test harness.

### Staleness is automatic

Each recorded call stores the prompt identity that produced it, and identities embed a
content fingerprint. Editing a prompt changes its identity and every recording under it
reports stale — so a recorded corpus cannot silently drift away from the prompts it
describes. Absent recordings **skip** (a fresh checkout is not broken); a present but
stale recording **fails** with the re-capture command.

### What tier 1 does and does not prove

It proves the pipeline still accepts what a real model actually produced — something a
hand-authored fixture cannot, because its author already knows what the code expects. The
existing `payloads.py` fixtures prove the complement: that the contracts reject what they
should.

It proves nothing about advice quality. One model, one case, one moment.

### What the first capture found

Three defects, none of which the deterministic suite could reach, because a substitute
reasoner satisfies whatever the code expects of it:

- **A free-text recommendation disposition.** The model returned `"Recommendation"` and
  the run died at composition. Typed on the wire now, so the JSON schema constrains it.
- **Two layers disagreeing on evidence scope.** The repair pass was stripping a
  legitimate citation of a confirmed user requirement from every finding that made one
  (ADR 0005).
- **A committed model configuration that could not complete a consultation.** 32768/16384
  left 16384 tokens for input against a ~29k-token concern packet.
- **A contract only the prompt stated.** Repository observations were required to carry a
  source location by prompt prose, while the schema left it nullable and the validator
  rejected its absence. Two of three captures died there (ADR 0005).

The pattern worth keeping: each one lived in the gap between what a layer *stated* and
what an adjacent layer *enforced*, with a repair pass absorbing the difference. Nothing
that never ran a real model could see them.

This is also why the two questions are asserted separately. *Did the report end valid*
is the contract; *did it get there unaided* is the achievability signal. Collapsing them
would have hidden the second defect behind a green run, since the pipeline did recover.

## Phase 2 — live stage probes *(implemented)*

`tests/quality/test_stage_probes.py` loads a captured stage input, calls one stage
against real Ollama, and asserts properties of the typed output. Deselected by default;
run with `make probe`. Two assertion classes, neither needing a judge:

- **Contract achievability** — does output satisfy the pipeline unaided, or need the
  repair pass? The operational signal nothing else measures, and the one that predicted
  two dead captures before spans were projected.
- **Evidence discipline** — a packet with no repository evidence must yield no
  `repository_observation`; an analysis must cite only nodes and policies its own packet
  surfaced.

The two are kept in separate tests because they mean different things. Discipline is
binary: one fabricated claim is a defect, not a bad day. Achievability is a property of
the contract as much as of the model, and the pipeline recovers from a good deal — so a
failure there is a finding to act on rather than a broken build.

The discipline probes target a known asymmetry. Synthesis constrains claim handles and
cluster references as **schema enums**, so an invalid reference is unrepresentable.
Concern analysis states its node and policy allowlists in a **runtime instruction** —
prose the model may ignore, and the first live capture shows it does: two invented policy
IDs were dropped by repair. Probing both is what turns that asymmetry from an observation
into a measurement.

### Recording the whole stage input

Phase 1 recorded packets but not the `GlobalContext`, which is half of what every stage
receives. A probe reconstructing it would be testing a context the model never saw, so
the bundle now records it and the format version is 2.

`available_recordings()` is deliberately tolerant while `Recording` stays strict: test
modules call it at import to parameterize, so a strict loader turns one unreadable bundle
into a collection error across every module that mentions recordings — a format bump then
presents as "the suite is broken" rather than "re-capture this bundle".
`unloadable_recordings()` fails one test with one instruction instead.

## Phase 3 — adversarial inputs

Hand-authored packets and claim pools that harvested fixtures will not produce: no
evidence at all, one weak proxy signal, conflicting policies, a case that asserts its own
solution. The product thesis is that more abstraction is not better, so the cases that
matter most are the ones that tempt over-engineering. If the advisor cannot say "don't",
it is an abstraction generator.

## Phase 4 — discrimination

Contrastive assertions across those inputs — same stage, two inputs, assert the
*structured* outputs differ. Never absolute assertions on prose: those are brittle to
model variation and recreate the memorisation problem WS7 removed from the substitute
reasoner.

Only then, if wanted, a rubric judge — where the interesting angle is that the **policy
corpus is the rubric**: did the recommendation apply the policies it retrieved, or name
them decoratively?

## Known limits

- Capture needs a live Ollama and takes minutes; CI has neither, so refreshing after a
  prompt change is a local step.
- A bundle is a few hundred KB of committed JSON, dominated by focused packets. One or
  two are fine; one per case would not be.
- Every response is recorded, but Phase 1 replays only synthesis. The rest are the
  faithful transcript and the seed corpus for Phase 2 — if Phase 2 does not follow, they
  are unread files and should be trimmed.
