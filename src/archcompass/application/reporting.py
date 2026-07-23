"""Deterministic, lossless Markdown rendering from validated report JSON."""

from __future__ import annotations

from archcompass.domain.consultation import (
    Claim,
    RecommendationReport,
    SupportedStatement,
)


def render_markdown(report: RecommendationReport) -> str:
    parts = [
        f"# {report.adr.title}",
        (
            f"Report ID: `{report.report_id}`  \n"
            f"Schema: `{report.schema_version}`  \n"
            f"Disposition: `{report.disposition}`"
        ),
        "## 1. Decision summary",
        _statement(report.decision_summary),
        "## 2. Problem and desired outcome",
        report.problem_and_desired_outcome,
        "## 3. Confirmed context",
        _claims(report.confirmed_context),
        "## 4. Assumptions and unresolved questions",
        _claims(report.assumptions_and_unresolved_questions),
        "## 5. Important design forces",
        _bullets(
            [
                (f"`{force.force_id}` — {force.title} ({force.importance}): {force.description}")
                for force in report.important_design_forces
            ]
        ),
        "## 6. Repository observations and quantified signals",
        _claims(report.repository_observations),
        "## 7. Relevant policies",
        _policy_section(report),
        "## 8. Recommended architecture",
        _statement(report.recommended_architecture),
        "## 9. Responsibility allocation",
        _supported_bullets(report.responsibility_allocation),
        "## 10. Proposed conceptual interfaces",
        _supported_bullets(report.conceptual_interfaces),
        "## 11. Alternatives considered",
        _bullets(
            [
                f"`{alternative.id}` — {alternative.title}: {alternative.summary}"
                for alternative in report.alternatives_considered
            ]
        ),
        "## 12. Scenario analysis",
        _scenarios(report),
        "## 13. Change-amplification and blast-radius analysis",
        _statement(report.change_amplification_analysis),
        "## 14. Trade-offs",
        _supported_bullets(report.trade_offs),
        "## 15. Implementation sequence",
        _supported_numbered(report.implementation_sequence),
        "## 16. Confidence",
        f"`{report.confidence.level}` — {report.confidence.rationale}",
        "## 17. Conditions that could reverse the recommendation",
        _supported_bullets(report.reversal_conditions),
        "## 18. Revisit triggers",
        _supported_bullets(report.revisit_triggers),
        "## 19. ADR-style decision record",
        (
            f"Status: `{report.adr.status}`\n\n"
            f"Context: {report.adr.context}\n\n"
            f"Decision: {_statement(report.adr.decision)}\n\n"
            f"Consequences:\n{_supported_bullets(report.adr.consequences)}"
        ),
        "## 20. Evidence appendix",
        _claims(report.evidence_appendix),
    ]
    return "\n\n".join(parts).rstrip() + "\n"


def _statement(statement: SupportedStatement) -> str:
    support = ", ".join(statement.supporting_claim_ids) or "none"
    legacy = "; legacy schema-v1 value" if statement.legacy else ""
    return (
        f"{statement.text}\n\n"
        f"_Classification: `{statement.classification}`; supports: `{support}`{legacy}._"
    )


def _claims(claims: list[Claim]) -> str:
    if not claims:
        return "_None._"
    lines: list[str] = []
    for claim in claims:
        references: list[str] = []
        for item in claim.atlas_references:
            location = item.location
            where = (
                f" {location.path}:{location.start_line}-{location.end_line}"
                if location is not None
                else ""
            )
            references.append(f"atlas:{item.node_id}{where}")
        references.extend(f"policy:{policy_id}" for policy_id in claim.policy_ids)
        suffix = f" [{'; '.join(references)}]" if references else ""
        lines.append(f"- `{claim.claim_id}` **{claim.classification}** — {claim.text}{suffix}")
    return "\n".join(lines)


def _policy_section(report: RecommendationReport) -> str:
    parts = [_claims(report.relevant_policies)]
    if report.policy_evidence:
        parts.append(
            "### Policy metadata\n\n"
            + _bullets(
                [
                    (
                        f"`{item.id}` — {item.title}; scope=`{item.scope}`; "
                        f"strength=`{item.strength}`; matched sections: "
                        f"{', '.join(item.matched_sections)}"
                    )
                    for item in report.policy_evidence
                ]
            )
        )
    if report.policy_conflicts:
        parts.append(
            "### Policy conflicts\n\n"
            + "\n".join(
                (
                    f"- Policies `{', '.join(conflict.policy_ids)}` — "
                    f"{conflict.explanation} Reconciliation: {conflict.reconciliation}"
                )
                for conflict in report.policy_conflicts
            )
        )
    return "\n\n".join(parts)


def _scenarios(report: RecommendationReport) -> str:
    sections: list[str] = []
    for scenario in report.scenario_analysis:
        assumptions = _bullets(scenario.assumptions)
        results = _bullets(
            [
                f"`{alternative_id}` — {result}"
                for alternative_id, result in scenario.alternative_results.items()
            ]
        )
        sections.append(
            f"### {scenario.scenario}\n\n"
            f"Assumptions:\n{assumptions}\n\n"
            f"Alternative results:\n{results}\n\n"
            f"Conclusion: {scenario.conclusion}"
        )
    return "\n\n".join(sections)


def _supported_bullets(items: list[SupportedStatement]) -> str:
    if not items:
        return "_None._"
    return "\n".join(f"- {item.text} {_statement_metadata(item)}" for item in items)


def _supported_numbered(items: list[SupportedStatement]) -> str:
    return "\n".join(
        f"{number}. {item.text} {_statement_metadata(item)}"
        for number, item in enumerate(items, start=1)
    )


def _statement_metadata(statement: SupportedStatement) -> str:
    support = ", ".join(statement.supporting_claim_ids) or "none"
    legacy = "; legacy" if statement.legacy else ""
    return f"_(classification=`{statement.classification}`; supports=`{support}`{legacy})_"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "_None._"
