# ADR 0001 — Compose the recommendation instead of reproducing it

**Status:** Accepted
**Date:** 2026-07-25
**Supersedes:** none
**Related:** `docs/plans/llm-boundary-hardening.md` (decision 1, WS3)

## Previous direction

The synthesis stage returned a complete `RecommendationReport`. That meant the model
restated a great deal it did not own: the design forces discovered earlier, the
alternatives and scenarios already evaluated, the canonical policy evidence from the
focused packets, every claim's identity and section placement, and each finding's Atlas
nodes, source locations, metrics, signals, and policy IDs.

Because a model cannot reliably reproduce that much verbatim, four mechanisms existed to
diff the response against the truth and put it back:

1. `OllamaReasoningProvider._normalize_output` rewrote the raw JSON before validation —
   restoring canonical artifacts, moving misclassified section claims, and reassigning
   duplicate claim IDs.
2. `ConsultationWorkflow._restore_synthesis_artifacts` restored the same canonical
   artifacts a second time, in a different layer, recording the same action kind.
3. `OllamaReasoningProvider._link_report_support` made an additional model call to
   re-link every statement to claims, because the in-band links were not trustworthy.
4. `consume_repair_actions` carried the resulting audit trail out of the adapter.

Mechanism 1 also had to run *before* Pydantic validation, since misclassified claims and
duplicate IDs raise inside `validate_report_contract`. That forced domain-aware repair
into the transport adapter, contradicting `docs/architecture.md`, which states that model
adapters "do not choose evidence, history, citation, or truncation rules".

## New direction

The synthesis stage returns a `ProposedRecommendation` (`domain/proposals.py`) containing
only what it uniquely contributes: the disposition, the recommendation prose, the
findings, and the claim handles that support them. `application/synthesis.py` composes
the persisted report from that proposal plus the workflow's own artifacts.

Everything known in advance is referenced by a short request-local handle whose valid
values are enumerated in the JSON schema, so an invented reference cannot be expressed —
the same pattern already proven for design-force handles at clustering.

Claims are not authored freely. The application builds a pool from the concern analyses
and the pinned case; the model cites handles from it. A provider may author only
`advisor_inference` and `derived_constraint` claims, which carry no evidence references.

## Consequences

Four failure classes stop being possible rather than being repaired:

| Failure | Why it cannot occur |
|---|---|
| Invented evidence | A claim handle resolves to a real claim or fails validation |
| Misclassified section | Claims are placed by their own classification |
| Duplicate claim identity | IDs are content-derived and owned by ArchCompass |
| Altered canonical artifact | Forces, alternatives, scenarios, and policy evidence are not on the wire |

Mechanisms 1–4 above are deleted. The Ollama adapter drops from 1,151 to 817 lines and
contains no domain rule; a structural test enforces that it cannot import the application
or workflow layers.

Two further effects are worth recording:

- **Report-level evidence validation is no longer reachable from provider error.**
  Synthesis can only cite claims the concern analyses already validated against their own
  packets, so `validate_report_evidence` should not fail in practice. It is retained as
  defence in depth against a defect in pool construction or packet handling, and the
  reachable synthesis failure is now an uncomposable proposal.
- **Provenance changes shape.** The persisted report is system-composed rather than
  model-emitted-and-repaired. `execution_metadata` records `synthesis_proposal_hash` (a
  canonical hash of the exact response) and `synthesis_composition`, kept separate from
  `model_output_repairs` so that composition is not mistaken for repair.

`canonicalize_report_findings` now records `restored_canonical_finding_evidence` only when
a finding actually asserted differing evidence. Filling in evidence a finding never stated
is projection, not restoration, and logging it as a repair overstated provider error.

One repair attempt remains for synthesis: `repair_recommendation_proposal`, which corrects
handles against the supplied allowlists. It does not re-run synthesis.
