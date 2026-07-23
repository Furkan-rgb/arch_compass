# Recommendation report contract

`RecommendationReport` is the canonical output. JSON is persisted directly from the validated
Pydantic model. Markdown is rendered deterministically from the same object, so the formats cannot
disagree structurally.

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
Policy guidance requires a retrieved policy. Unknown references never survive validation.

Confidence is `low`, `medium`, or `high` with prose rationale. It is not a probability or
complexity score.

