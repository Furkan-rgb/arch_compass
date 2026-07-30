"""Render a boundary review as Markdown.

One renderer, used by the CLI, the stored `markdown_report`, and anything the web serves,
so the document a person reads is the same wherever they read it.

Cleared boundaries are rendered as fully as material ones. A report listing only problems
would look identical whether the advisor examined every boundary and cleared them or never
ran at all, and telling those two apart is most of what this tool is for.
"""

from __future__ import annotations

from archcompass.domain.review import (
    BoundaryReview,
    BoundaryReviewReport,
    ReviewedBoundary,
    ReviewOverview,
)


def _boundary(item: ReviewedBoundary) -> list[str]:
    # The verdict spelled out rather than named, in the vocabulary of the shape it is about.
    # "Material" is a term of art that reads, in ordinary English, as "this matters" — the
    # opposite of what it records — and one phrase cannot serve both halves of the catalogue.
    lines = [
        "",
        f"### {item.reference} · {item.verdict_label}",
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
    # Both stated on every boundary rather than once at the end, and both for the same
    # reason: a reader deciding whether to act on this verdict needs to know what it rested
    # on at the point of deciding. The two are different halves — what the method could not
    # see, and what the case did not say — and only the second is one they can fix.
    if item.hinge is not None:
        lines += [
            "",
            f"*This verdict turns on an open question.* {item.hinge.unknown} "
            f"If so: {item.hinge.if_confirmed} If not: {item.hinge.if_denied}",
        ]
    lines += ["", f"*Detection limits.* {item.candidate.limitations}"]
    return lines


def _overview(overview: ReviewOverview) -> list[str]:
    """The synthesis, with every claim followed by the boundaries it rests on.

    The references are printed rather than implied. A reader who disagrees with a theme has
    to be able to go straight to the verdicts it was built from, and one that cited nothing
    would not have been recorded at all.
    """

    lines = ["", "## Conclusion", "", overview.situation]
    if overview.themes:
        lines += ["", "### Across the boundaries", ""]
        lines += [
            f"- {statement.text} *({', '.join(statement.supporting_references)})*"
            for statement in overview.themes
        ]
    if overview.recommended_sequence:
        lines += ["", "### Recommended actions, in order", ""]
        lines += [
            f"{position}. {statement.text} "
            f"*({', '.join(statement.supporting_references)})*"
            for position, statement in enumerate(overview.recommended_sequence, start=1)
        ]
    lines += ["", f"*What this review could not see.* {overview.limits}"]
    return lines


def _question_section(overview: ReviewOverview) -> list[str]:
    """What the advisor is asking for, and where each answer lands.

    Only a first pass ever has these: the summarising stage has no field for a question, so
    the second pass cannot open a fresh round. Named for what the advisor is asking rather
    than for a gap in a document — a review may run with nothing written down at all, and
    "what the case does not say" would describe a hole in something that was never written.
    """

    if not overview.open_questions:
        return []
    lines = ["", "## What it needs to know", ""]
    lines.append(
        "Each of these would settle a verdict this run could not settle on its own. An "
        "answer becomes a revision of the case, and the boundaries are then judged again "
        "against it — which is the mechanism working rather than the advisor changing its "
        "mind."
    )
    for question in overview.open_questions:
        lines += [
            "",
            f"**{question.reference}. {question.question}**",
            "",
            # The observation first and as prose, not as another labelled bullet. It is the
            # part a reader cannot supply for themselves, and burying it in a list beside
            # two shorter items is how it gets skipped for the two shorter items.
            question.what_the_review_saw,
            "",
            f"- *What is unstated:* {question.unknown}",
            f"- *Why it matters:* {question.why_it_matters} "
            f"({', '.join(question.supporting_references)})",
            f"- *An answer belongs in:* `{question.answer_belongs_in.value}`",
        ]
    return lines


def _questions(report: BoundaryReviewReport) -> list[str]:
    """A first pass that is still asking: the questions, and no findings.

    Deliberately not a shorter version of the same document. Every boundary here has been
    judged, and printing those verdicts under "what should change" would present as findings
    a set that four-fifths of moved on the bundled example once its questions were answered
    (ADR 0010). What is honest to print is the count, the questions, and where the verdicts
    are — which is the same thing the page shows.
    """

    reviewed = len(report.reviewed)
    subject = "boundary" if reviewed == 1 else "boundaries"
    hinged = sum(1 for item in report.reviewed if item.hinge is not None)
    lines = [
        f"# Boundary review — {report.case_title}",
        "",
        (
            f"**This review is waiting on answers.** {reviewed} {subject} were judged "
            f"against what the case says so far, and {hinged} of those verdicts rested on "
            "something the case does not state. The verdicts are held rather than reported: "
            "answering below carries the review on, and the second pass is the one that "
            "concludes."
        ),
        "",
        "## Case",
        "",
        report.problem_and_desired_outcome,
    ]
    lines += _question_section(report.overview)
    lines += ["", f"*What this pass could not see.* {report.overview.limits}"]
    lines += [
        "",
        "## Coverage",
        "",
        (
            f"{len(report.policies_presented)} policies were presented in full with every "
            f"boundary, and all {reviewed} {subject} were judged. Nothing was skipped; the "
            "verdicts are withheld because they are provisional, not because they are "
            "missing."
        ),
    ]
    return lines


def render_report(report: BoundaryReviewReport, *, awaiting_answers: bool = False) -> str:
    if awaiting_answers:
        return "\n".join(_questions(report))
    lines = [
        f"# Boundary review — {report.case_title}",
        "",
        report.headline,
    ]
    lines += _overview(report.overview)
    lines += [
        "",
        "## Case",
        "",
        report.problem_and_desired_outcome,
    ]
    if report.material:
        # Grouped by verdict rather than by shape, because a reader wants what to act on
        # first. Each heading below names its own shape, so the two directions of the
        # catalogue do not have to share one sentence here.
        lines += ["", "## What should change", ""]
        lines.append("Each of these was found to be costing more than it earns in this case.")
        for item in report.material:
            lines += _boundary(item)
    if report.cleared:
        lines += ["", "## Examined and left alone", ""]
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
    return render_report(review.report, awaiting_answers=review.awaiting_answers)
