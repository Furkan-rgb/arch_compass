"""Deterministic Markdown rendering from validated report JSON."""

from __future__ import annotations

from archcompass.domain.consultation import Claim, RecommendationReport


def render_markdown(report: RecommendationReport) -> str:
    parts = [
        f"# {report.adr.title}",
        "## 1. Decision summary",
        report.decision_summary,
        "## 2. Problem and desired outcome",
        report.problem_and_desired_outcome,
        "## 3. Confirmed context",
        _claims(report.confirmed_context),
        "## 4. Assumptions and unresolved questions",
        _claims(report.assumptions_and_unresolved_questions),
        "## 5. Important design forces",
        _bullets(
            [
                f"{force.title} ({force.importance}): {force.description}"
                for force in report.important_design_forces
            ]
        ),
        "## 6. Repository observations and quantified signals",
        _claims(report.repository_observations),
        "## 7. Relevant policies",
        _claims(report.relevant_policies),
        "## 8. Recommended architecture",
        report.recommended_architecture,
        "## 9. Responsibility allocation",
        _bullets(report.responsibility_allocation),
        "## 10. Proposed conceptual interfaces",
        _bullets(report.conceptual_interfaces),
        "## 11. Alternatives considered",
        _bullets(
            [
                f"{alternative.title}: {alternative.summary}"
                for alternative in report.alternatives_considered
            ]
        ),
        "## 12. Scenario analysis",
        _bullets(
            [f"{scenario.scenario}: {scenario.conclusion}" for scenario in report.scenario_analysis]
        ),
        "## 13. Change-amplification and blast-radius analysis",
        report.change_amplification_analysis,
        "## 14. Trade-offs",
        _bullets(report.trade_offs),
        "## 15. Implementation sequence",
        _numbered(report.implementation_sequence),
        "## 16. Confidence",
        f"{report.confidence.level}: {report.confidence.rationale}",
        "## 17. Conditions that could reverse the recommendation",
        _bullets(report.reversal_conditions),
        "## 18. Revisit triggers",
        _bullets(report.revisit_triggers),
        "## 19. ADR-style decision record",
        (
            f"Status: {report.adr.status}\n\n"
            f"Context: {report.adr.context}\n\n"
            f"Decision: {report.adr.decision}\n\n"
            f"Consequences:\n{_bullets(report.adr.consequences)}"
        ),
        "## 20. Evidence appendix",
        _claims(report.evidence_appendix),
    ]
    return "\n\n".join(parts).rstrip() + "\n"


def _claims(claims: list[Claim]) -> str:
    if not claims:
        return "_None._"
    lines: list[str] = []
    for claim in claims:
        references = [
            *(f"atlas:{item.node_id}" for item in claim.atlas_references),
            *(f"policy:{policy_id}" for policy_id in claim.policy_ids),
        ]
        suffix = f" [{', '.join(references)}]" if references else ""
        lines.append(f"- **{claim.classification}** — {claim.text}{suffix}")
    return "\n".join(lines)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "_None._"


def _numbered(items: list[str]) -> str:
    return "\n".join(f"{number}. {item}" for number, item in enumerate(items, start=1))
