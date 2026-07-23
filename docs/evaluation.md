# Evaluation methodology

Mandatory evaluations use deterministic embedding and reasoning providers. They exercise the
real SQLite, `sqlite-vec`, policy, atlas, query, evidence-validation, report, and revision paths
without a live model.

## Case A: greenfield audiobook

The case includes ingestion, text preparation, chunking, voice design/cloning, narration, one
local GPU, Qwen first, possible hosted providers, and resumable jobs. Acceptance requires stable
workflow boundaries, provider-owned variation, and no universal plugin platform. No atlas query
may occur.

## Case B: brownfield provider leakage

The synthetic Python fixture spreads Qwen voice knowledge across frontend, preflight, workflow,
provider, and root composition. A provider interface lacks capability discovery. Acceptance
requires repository citations, policy retrieval, explicit duplicated knowledge/change
amplification, and provider-owned discovery.

## Case C: premature abstraction

One local behavior has one implementation and no credible variation. Acceptance requires keeping
the implementation local rather than adding interfaces, factories, and configuration.

## Cross-case assertions

- Every source and policy reference is valid and was available to the model stage.
- Facts, assumptions, and inferences remain distinguishable.
- Final synthesis receives focused packets and never the raw atlas or source tree.
- Greenfield consultation succeeds without repository data.
- “No abstraction” is representable as a first-class recommendation.
- Mandatory tests do not contact Ollama.

## Live-provider tests

Tests marked `ollama` use the models in `config/models.yaml`. They verify the embedding batch,
dimension, finite-value, and input-sensitivity contracts, then run the premature-abstraction
case through the real policy index and complete consultation workflow. Assertions target stable
report and evidence invariants rather than exact model wording.

Run only the live-provider tests with:

```bash
make test-ollama
```

Run every deterministic and live check plus the distribution build with:

```bash
make full
```
