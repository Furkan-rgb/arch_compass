"""Render a boundary review as Markdown.

One renderer, used by the CLI, the stored `markdown_report`, and anything the web serves,
so the document a person reads is the same wherever they read it.

Cleared boundaries are rendered as fully as material ones. A report listing only problems
would look identical whether the advisor examined every boundary and cleared them or never
ran at all, and telling those two apart is most of what this tool is for.
"""

from __future__ import annotations

from archcompass.domain.review import BoundaryReview, BoundaryReviewReport, ReviewedBoundary


def _boundary(item: ReviewedBoundary) -> list[str]:
    verdict = "Material" if item.material else "Not material"
    lines = [
        "",
        f"### {item.reference} · {verdict}",
        "",
        f"`{item.candidate.summary}`",
        "",
    ]
    for participant in item.candidate.participants:
        location = participant.location
        where = "" if location is None else f" — `{location.path}:{location.start_line}`"
        lines.append(f"- {participant.role} `{participant.qualified_name}`{where}")
    lines += ["", item.rationale]
    if item.recommended_response:
        lines += ["", f"**Recommended response.** {item.recommended_response}"]
    if item.policy_bearings:
        lines += ["", "Policies that bear on this boundary:", ""]
        lines += [
            f"- **{bearing.policy_title}** — {bearing.how}" for bearing in item.policy_bearings
        ]
    # Stated on every boundary rather than once at the end. A reader deciding whether to
    # act on this specific verdict needs to know what the method could not see, at the
    # point of deciding.
    lines += ["", f"*Detection limits.* {item.candidate.limitations}"]
    return lines


def render_report(report: BoundaryReviewReport) -> str:
    lines = [
        f"# Boundary review — {report.case_title}",
        "",
        report.overview,
        "",
        "## Case",
        "",
        report.problem_and_desired_outcome,
    ]
    if report.material:
        lines += ["", "## Boundaries judged material", ""]
        lines.append(
            "Each of these was found not to be earning its place under this case."
        )
        for item in report.material:
            lines += _boundary(item)
    if report.cleared:
        lines += ["", "## Boundaries examined and cleared", ""]
        lines.append(
            "The advisor looked at each of these and concluded it should stay as it is."
        )
        for item in report.cleared:
            lines += _boundary(item)
    lines += [
        "",
        "## Coverage",
        "",
        (
            f"{len(report.policies_presented)} policies were presented in full with every "
            "boundary, so a policy that does not appear above did not apply rather than "
            "going unconsidered."
        ),
    ]
    return "\n".join(lines)


def render_review(review: BoundaryReview) -> str:
    if review.report is None:
        reasons = "\n".join(f"- {item}" for item in review.sanitized_errors)
        return f"# Boundary review failed\n\n{reasons or '- No reason was recorded.'}"
    return render_report(review.report)
