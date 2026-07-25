# Recommendation report contract

`RecommendationReport` is the canonical output. JSON is persisted directly from the validated
Pydantic model. Markdown is rendered deterministically from the same object, so the formats cannot
disagree structurally. Newly produced reports use schema version 3 and carry a first-class
recommendation disposition: `introduce_boundary`, `move_responsibility`, `keep_local`, `delay`,
`preserve`, or `gather_information`.

The report contains, in order:

1. Decision summary.
2. Problem and desired outcome.
3. Confirmed context.
4. Assumptions and unresolved questions.
5. Important design forces.
6. Canonical architectural findings.
7. Repository observations and quantified signals.
8. Relevant policies.
9. Recommended architecture.
10. Responsibility allocation.
11. Proposed conceptual interfaces.
12. Alternatives.
13. Scenario analysis.
14. Change-amplification and blast-radius analysis.
15. Trade-offs.
16. Implementation sequence.
17. Qualitative confidence and rationale.
18. Reversal conditions.
19. Revisit triggers.
20. ADR record.
21. Evidence appendix.

Each new report has one to twelve ordered `ArchitecturalFinding` values. Stable IDs are assigned
by the workflow, never trusted from model output. Findings make importance contextual rather than
numeric and preserve rationale, confidence, consequence, exact claim/node/policy evidence,
locations, recommended response, and uncertainty. Providers author the finding's interpretation
and links to validated claims. The application reconstructs Atlas node IDs, repository locations,
metric values, signals, and policies exactly from the finding's corresponding focused packet after
synthesis and after any repair. It rejects evidence from another concern cluster, revalidates
exact concern-cluster coverage after repair, and assigns `FIND-001…n` only after final
canonicalization.

Claims carry a stable ID, text, classification, atlas source references, and policy IDs. Repository
observations require a surfaced node; locations must match that node's path and source span.
Policy guidance requires a retrieved policy that applies to the consultation context.
`PolicyEvidenceSummary` preserves each reported policy's ID, title, scope, applicability subject,
strength, and up to three distinct matched sections merged stably across concern clusters. A
`PolicyConflict` cites at least two retrieved policies and preserves its explanation and
reconciliation.

The decision, recommended architecture, responsibility allocation, conceptual interfaces,
change-amplification conclusion, trade-offs, implementation sequence, reversal conditions,
revisit triggers, and ADR conclusions are `SupportedStatement` values. Each new statement has a
classification and at least one supporting claim ID. Scenario results are keyed by alternative ID
and must cover all alternatives.

Validation permits one deterministic repair pass. Unsupported references and claims are removed;
a repository observation with an invalid or absent location is removed as a whole. The repaired
report is validated again and the run fails if required substantive content no longer has valid
support. Runs record initial errors, repair actions, and final errors separately.

`SourceLocation` requires positive line numbers and `start_line <= end_line`. Canonical-finding
validation compares complete locations, metric observations, signal records, and policy
identities with the focused packet instead of accepting provider-supplied values that merely
reference a valid node.

Markdown is lossless for statement classifications/support IDs, claim classifications, source
paths and line spans, scenario assumptions and per-alternative results, policy metadata, and
policy conflicts. Unknown references never survive validation.

Confidence is `low`, `medium`, or `high` with prose rationale. It is not a probability or
complexity score.

Reports declare schema version 3 explicitly and are validated against that schema alone. A
report with missing findings, unstructured substantive prose, or positional scenario results is
rejected rather than upgraded, and every substantive statement must cite at least one supporting
claim. There is no in-band flag that exempts a statement from that requirement.
