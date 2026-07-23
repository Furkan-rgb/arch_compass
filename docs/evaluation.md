# Evaluation methodology

Mandatory evaluations use deterministic embedding and reasoning providers. They exercise the
real SQLite, `sqlite-vec`, policy, atlas, query, evidence-validation, report, and revision paths
without a live model.

Canonical cases and any repository fixture live together under `eval/cases/<case>/`. The
provider-leakage repository has no duplicate test fixture elsewhere.

## Case A: greenfield audiobook

The case includes ingestion, text preparation, chunking, voice design/cloning, narration, one
local GPU, Qwen first, possible hosted providers, and resumable jobs. Acceptance requires stable
workflow boundaries, provider-owned variation, and no universal plugin platform. No atlas query
may occur, and the disposition must not invent a repository-backed concern.

## Case B: brownfield provider leakage

The synthetic Python fixture spreads Qwen voice knowledge across frontend, preflight, workflow,
provider, and root composition. A provider interface lacks capability discovery. Acceptance
requires located repository citations, policy retrieval, explicit duplicated knowledge/change
amplification, provider-owned discovery, and the `move_responsibility` disposition.

## Case C: premature abstraction

The fixture contains one directly called local formatter and two behavior tests. There is no
interface, factory, registry, or configuration. The case describes those proposed additions and
records that there is no credible variation. Acceptance requires `keep_local` without adding any
of those mechanisms.

## Cross-case assertions

- Every source and policy reference is valid and was available to the model stage.
- Facts, assumptions, and inferences remain distinguishable.
- Final synthesis receives focused packets and never the raw atlas or source tree.
- Greenfield consultation succeeds without repository data.
- “No abstraction” is representable as a first-class recommendation.
- Brownfield observations contain stable node IDs and valid source spans.
- Query and excerpt budgets remain bounded and truncation is auditable.
- Mandatory tests do not contact Ollama.

## Live-provider tests

Tests marked `ollama` use the models in `config/models.yaml`. They verify the embedding batch,
dimension, finite-value, and input-sensitivity contracts, then run the greenfield audiobook case
through the real policy index and complete consultation workflow. Assertions target stable
report, evidence, and per-stage timing invariants rather than exact model wording. There is no
flaky end-to-end duration assertion; configured per-request provider timeouts still apply.

Run only the live-provider tests with:

```bash
make test-ollama
```

Run every deterministic and live check plus the distribution build with:

```bash
make full
```
