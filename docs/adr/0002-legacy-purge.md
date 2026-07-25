# ADR 0002 — Remove pre-release schema compatibility

**Status:** Accepted (amended by ADR 0003)
**Date:** 2026-07-25
**Supersedes:** none
**Related:** `docs/plans/llm-boundary-hardening.md` (decision 9, WS1)

## Previous direction

Domain models carried in-validator migration code for three schema generations.
`RecommendationReport.upgrade_schema_v1`, `ADRRecord.upgrade_legacy_strings`,
`FocusedAnalysisPacket.upgrade_legacy_packet`, `ScenarioEvaluation.upgrade_legacy_results`,
`ArchitectureCase.upgrade_schema_v1`, and the `ConsultationRun` legacy branch rewrote
incoming payloads before validation. `SupportedStatement` carried a `legacy` flag,
`ChangeAmplificationMetrics` and `CognitiveScopeMetrics` accepted superseded metric
names through validation aliases, and `ConcernAnalysis.cluster_id` defaulted to
`"cluster_legacy"`.

## Problem

Two of those mechanisms were reachable from live model output, not only from stored rows:

1. `schema_version` is a defaulted field, so the JSON schema sent to the reasoning model
   did not require it. A provider that omitted the field had its response read as a
   schema-v1 report: the disposition was inferred from keywords in the decision summary
   ("keep" plus "local" produced `KEEP_LOCAL`), and `findings` — the report's central
   evidence — was fabricated from claims by `_legacy_findings`. The failure was silent and
   produced a plausible-looking report.
2. `SupportedStatement.legacy` was part of the model-facing schema. A statement marked
   `legacy: true` was exempt from the requirement to cite supporting claims and was skipped
   by evidence validation, so the model could opt out of the evidence contract in band.

Both contradict master-plan invariant 13 (facts, assumptions, policies and inferences remain
distinguishable) and invariant 14 (every repository or policy reference is validated).

The compatibility itself was speculative: ArchCompass 0.1.0 has never been released, so the
earlier schemas existed only inside this repository's history.

## New direction

Wire contracts and storage contracts are separate, and domain models validate the current
schema only.

- All legacy upgrade validators, the `legacy` statement flag, the metric-name aliases, and
  the `cluster_legacy` default are removed. `schema_version` is required on
  `RecommendationReport` and `ConsultationRun`.
- Stored documents are decoded through `decode_stored_json`, which converts a validation
  failure into `UnreadableStoredRecordError`: it names the record and asks for the
  consultation to be re-run.
- Dead surfaces removed alongside: `CaseExtraction`, `ports/services.py`,
  `prompt_identities` on both providers, `DEFAULT_CONFIG_TEXT`, the compat wrapper
  `repair_report_evidence`, the `advise(atlas=...)` shim, and unused `casefold`/
  `assert_fresh` spellings.
- Mandated V1.2 ceilings move to `archcompass.domain.budgets`. Configuration may lower a
  ceiling but never raise it, and the two values that admit exactly one setting are no
  longer presented as configuration.

## Consequences

- A provider response that omits `schema_version`, or marks a statement `legacy`, now fails
  loudly at the boundary instead of producing a silently degraded report.
- Findings are authored evidence. A report without them is rejected rather than having them
  synthesized from claims.
- Reading a row written by an earlier, unreleased schema raises an explicit error. No stored
  data is deleted, and no migration rewrites rows; the fix is to re-run the consultation.
- Invariant 21 (old consultations retain the exact case, atlas and policy versions they used)
  is preserved as data retention. What is removed is schema-tolerance code, not rows.
- The deprecated `report_follow_ups` table and its data are retained, as the V1.2 milestone
  required at the time. *Amended:* ADR 0003 drops the table with the owner's explicit
  authorization; its rows were never read after the feature's removal.
