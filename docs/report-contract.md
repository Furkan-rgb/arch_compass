# Recommendation report contract

`RecommendationReport` is the canonical output. JSON is persisted directly from the validated
Pydantic model. Markdown is rendered deterministically from the same object, so the formats cannot
disagree structurally. Newly produced reports use schema version 2 and carry a first-class
recommendation disposition: `introduce_boundary`, `move_responsibility`, `keep_local`, `delay`,
`preserve`, or `gather_information`.

The report contains, in order:

1. Decision summary.
2. Problem and desired outcome.
3. Confirmed context.
4. Assumptions and unresolved questions.
5. Important design forces.
6. Repository observations and quantified signals.
7. Relevant policies.
8. Recommended architecture.
9. Responsibility allocation.
10. Proposed conceptual interfaces.
11. Alternatives.
12. Scenario analysis.
13. Change-amplification and blast-radius analysis.
14. Trade-offs.
15. Implementation sequence.
16. Qualitative confidence and rationale.
17. Reversal conditions.
18. Revisit triggers.
19. ADR record.
20. Evidence appendix.

Claims carry a stable ID, text, classification, atlas source references, and policy IDs. Repository
observations require a surfaced node; locations must match that node's path and source span.
Policy guidance requires a retrieved policy. `PolicyEvidenceSummary` preserves each reported
policy's ID, title, scope, strength, and matched sections. A `PolicyConflict` cites at least two
retrieved policies and preserves its explanation and reconciliation.

The decision, recommended architecture, responsibility allocation, conceptual interfaces,
change-amplification conclusion, trade-offs, implementation sequence, reversal conditions,
revisit triggers, and ADR conclusions are `SupportedStatement` values. Each new statement has a
classification and at least one supporting claim ID. Scenario results are keyed by alternative ID
and must cover all alternatives.

Validation permits one deterministic repair pass. Unsupported references and claims are removed;
a repository observation with an invalid or absent location is removed as a whole. The repaired
report is validated again and the run fails if required substantive content no longer has valid
support. Runs record initial errors, repair actions, and final errors separately.

Markdown is lossless for statement classifications/support IDs, claim classifications, source
paths and line spans, scenario assumptions and per-alternative results, policy metadata, and
policy conflicts. Unknown references never survive validation.

Confidence is `low`, `medium`, or `high` with prose rationale. It is not a probability or
complexity score.

Schema-v1 standalone and stored reports remain readable. Compatibility validation wraps legacy
substantive strings as explicitly marked legacy statements and maps positional scenario results
to the corresponding alternative IDs. New schema-v2 reports reject unstructured
substantive prose.
