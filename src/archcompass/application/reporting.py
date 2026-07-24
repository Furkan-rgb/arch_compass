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
        "## 6. Findings",
        _findings(report),
        "## 7. Repository observations and quantified signals",
        _claims(report.repository_observations),
        "## 8. Relevant policies",
        _policy_section(report),
        "## 9. Recommended architecture",
        _statement(report.recommended_architecture),
        "## 10. Responsibility allocation",
        _supported_bullets(report.responsibility_allocation),
        "## 11. Proposed conceptual interfaces",
        _supported_bullets(report.conceptual_interfaces),
        "## 12. Alternatives considered",
        _bullets(
            [
                f"`{alternative.id}` — {alternative.title}: {alternative.summary}"
                for alternative in report.alternatives_considered
            ]
        ),
        "## 13. Scenario analysis",
        _scenarios(report),
        "## 14. Change-amplification and blast-radius analysis",
        _statement(report.change_amplification_analysis),
        "## 15. Trade-offs",
        _supported_bullets(report.trade_offs),
        "## 16. Implementation sequence",
        _supported_numbered(report.implementation_sequence),
        "## 17. Confidence",
        f"`{report.confidence.level}` — {report.confidence.rationale}",
        "## 18. Conditions that could reverse the recommendation",
        _supported_bullets(report.reversal_conditions),
        "## 19. Revisit triggers",
        _supported_bullets(report.revisit_triggers),
        "## 20. ADR-style decision record",
        (
            f"Status: `{report.adr.status}`\n\n"
            f"Context: {report.adr.context}\n\n"
            f"Decision: {_statement(report.adr.decision)}\n\n"
            f"Consequences:\n{_supported_bullets(report.adr.consequences)}"
        ),
        "## 21. Evidence appendix",
        _claims(report.evidence_appendix),
    ]
    return "\n\n".join(parts).rstrip() + "\n"


def _findings(report: RecommendationReport) -> str:
    sections: list[str] = []
    for finding in report.findings:
        locations = ", ".join(
            (
                f"{item.path}:{item.location.start_line}-{item.location.end_line}"
                if item.location is not None
                else item.path
            )
            for item in finding.affected_locations
        )
        sections.append(
            f"### {finding.finding_id} — {finding.title}\n\n"
            f"Importance: **{finding.importance.value.title()}**  \n"
            f"Confidence: **{finding.confidence.level.value.title()}**\n\n"
            f"{finding.summary}\n\n"
            f"Importance rationale: {finding.importance_rationale}\n\n"
            f"Consequence: {finding.consequence}\n\n"
            f"Recommended response: {finding.recommended_response}\n\n"
            f"Claims: `{', '.join(finding.claim_ids)}`  \n"
            f"Atlas nodes: `{', '.join(finding.atlas_node_ids) or 'none'}`  \n"
            f"Policies: `{', '.join(finding.policy_ids) or 'none'}`  \n"
            f"Locations: {locations or 'None'}\n\n"
            f"Uncertainty:\n{_bullets(finding.uncertainty)}"
        )
    return "\n\n".join(sections)


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
                        f"applies to=`{item.applies_to or 'all contexts'}`; "
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
