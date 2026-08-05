"""What a headless run says out loud: a log summary, and one comment on a pull request.

Two renderers over one document, for two readers who are in different postures. The log is
read by someone who has already been told the check failed and wants to know what about; the
comment is read by someone who was not looking for it at all and has to be given the finding
in the first two lines or not at all.

Both quote. Every verdict label and every rationale here is the review's own text, copied and
never rewritten — the one edit either renderer makes is cutting a long rationale at a sentence
boundary, which is why `_excerpt` is careful to stop at a full stop rather than mid-clause.
The constraint comes from the plan (§5) and it is not stylistic: a comment that paraphrased
would be a second account of the review, published under the review's name, drifting from it
with every wording change nobody notices.

Carried boundaries are counted and not listed in either. That is the delta working — run two is
quieter than run one because nothing moved under those boundaries, not because anybody declared
them fine — and the count stays visible so the silence is a claim rather than an omission.

Closures are the exception to "lead with the problem". A boundary that no longer exists is the
loop closing, and it is named rather than counted, because it is the one thing here that is
good news and the tool used to deliver it by going quiet.
"""

from __future__ import annotations

from archcompass.application.ci import CiBoundary, CiRun

#: The line an Action looks for to decide whether it is editing its own comment or writing a
#: new one. First line, exact, and never templated with anything run-specific: a marker that
#: varied by branch or by run would produce a comment per push, which is the behaviour the
#: sticky comment exists to avoid.
COMMENT_MARKER = "<!-- archcompass-ci -->"

#: Where a rationale gets cut in the comment. Long enough for the advisor's reasoning to have
#: made its point, short enough that a pull request with six findings is still readable.
_EXCERPT_LIMIT = 320


def _excerpt(text: str, limit: int = _EXCERPT_LIMIT) -> str:
    """The first whole sentences of a rationale that fit, or all of it when it is short.

    Cut at a sentence boundary and never mid-clause. A rationale ending "…so the boundary is
    not" would invert the finding it is quoting, and an excerpt that can misquote is worse
    than a long comment. Where the first sentence alone is over the limit the text is cut on
    a word boundary with an ellipsis, which reads as truncation rather than as an ending.
    """

    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    kept = ""
    # Walk the sentence terminators in order and keep every complete sentence that fits.
    sentences: list[str] = []
    start = 0
    for position, character in enumerate(collapsed):
        if character in ".?!" and (
            position + 1 == len(collapsed) or collapsed[position + 1] == " "
        ):
            sentences.append(collapsed[start : position + 1])
            start = position + 2
    for sentence in sentences:
        candidate = f"{kept} {sentence}".strip()
        if len(candidate) > limit:
            break
        kept = candidate
    if kept:
        return f"{kept} …"
    return f"{collapsed[:limit].rsplit(' ', 1)[0]} …"


def _carried_forward(run: CiRun) -> str:
    """The attribution the plan requires: how much of this run was reused, in plain numbers."""

    counts = run.counts
    return (
        f"{counts.verdicts_reused} of {counts.verdicts_total} verdicts reused from "
        "earlier runs"
    )


def _partition_line(run: CiRun) -> str:
    """The revision in one line: what moved, and how much of it is still asking something."""

    counts = run.counts
    return (
        f"{counts.carried} carried, {counts.judged} judged, {counts.succeeded} succeeded, "
        f"{counts.addressed} addressed — {counts.attention} needing attention, "
        f"{counts.holding} held on an open question."
    )


def _compared_with(run: CiRun) -> str:
    """Which revision this one is a delta against, so the counts above can be read at all."""

    if run.first_revision or run.previous_review_id is None:
        return (
            f"First revision on {run.branch_name or 'this branch'}: nothing to compare with, "
            "so every boundary is judged."
        )
    return f"Compared with revision {run.previous_review_id}."


def render_ci_summary(run: CiRun) -> str:
    """The run as a log reader meets it: the partition, then only what this revision moved.

    Leads with the partition because that is what says whether the check is working. A run
    reporting "41 carried, 2 judged" is one nobody has to read twice; one reporting "43 judged"
    every time is a repository nothing is settled on, and the difference should be visible
    without reading a single finding.
    """

    lines = [
        f"Boundary check — {run.case_title}",
        "",
        _partition_line(run),
        _compared_with(run),
    ]
    for closed in run.addressed:
        lines += [
            "",
            f"Addressed: {closed.title} "
            f"({closed.last_reference}, {closed.pattern.value})",
        ]
    surfaced = run.surfaced
    if not surfaced:
        lines += [
            "",
            "Nothing on this branch moved since the previous revision.",
        ]
    for item in surfaced:
        lines += ["", *_summary_boundary(item)]
    lines += ["", _verdict_line(run)]
    lines += [f"Review {run.review_id} — {_carried_forward(run)}."]
    return "\n".join(lines)


def _summary_boundary(item: CiBoundary) -> list[str]:
    marks = [*_state_marks(item)]
    if item.blocking:
        marks.append("blocking")
    if item.holding:
        marks.append("holding")
    if item.verdict_reused_from is not None:
        marks.append(f"carried forward from {item.verdict_reused_from}")
    lines = [f"{item.reference} [{', '.join(marks)}] {item.verdict_label}", item.rationale]
    if item.decision is not None:
        lines.append(_decision_line(item))
    for question in item.questions:
        lines.append(f"  Open: {question.question}")
    return lines


def _state_marks(item: CiBoundary) -> list[str]:
    """Where a boundary stands, and which input put it there.

    Both, because they answer different questions and only together do they stop a reader
    hearing "changed" as a statement about their code. `judged` says this revision put the
    boundary back on the table; `because model` says which input moved it there.
    """

    state = item.delta_state.value if item.delta_state is not None else "judged"
    if item.judged_because is None:
        return [state]
    return [state, f"because {item.judged_because.value}"]


def _decision_line(item: CiBoundary) -> str:
    """The team's own position, named and attributed, beside the verdict it disposes of.

    Printed even when it silences the finding — especially then. A boundary that vanished
    because somebody waived it is indistinguishable from a boundary nobody found, and the
    whole point of a recorded disagreement is that it is on the record.
    """

    decision = item.decision
    if decision is None:  # pragma: no cover - guarded by the caller
        return ""
    reason = f": {decision.reason}" if decision.reason else ""
    stale = "" if decision.taken_on_this_verdict else " (taken against an earlier verdict)"
    return f"  {decision.state.value} by {decision.author}{stale}{reason}"


def _verdict_line(run: CiRun) -> str:
    if not run.blocking:
        return "No material boundary this revision judged is unaccounted for."
    subject = "boundary" if len(run.blocking) == 1 else "boundaries"
    listed = ", ".join(run.blocking)
    if run.exit_code == 0:
        return (
            f"{len(run.blocking)} material {subject} ({listed}) nobody has decided on — "
            "reported only, because this check was asked to fail for nothing."
        )
    return f"{len(run.blocking)} material {subject} to account for: {listed}."


def render_ci_comment(run: CiRun, *, workspace_url: str | None = None) -> str:
    """One markdown comment, written to be edited in place on every push.

    The marker is the first line so an Action can find its own previous comment with a
    substring match and edit it rather than adding another. Every push editing one comment is
    the difference between a check that lives in the pull request and a thread nobody can
    read by the fourth commit.

    `workspace_url` is absent by default and no link is invented when it is. A dead link into
    a workspace that is not running would be worse than no link: it would promise a place to
    go and triage a finding, which is the one thing this comment cannot do on its own.
    """

    counts = run.counts
    lines = [
        COMMENT_MARKER,
        "",
        f"## ArchCompass — {run.case_title}",
        "",
        (
            f"**{counts.carried} carried · {counts.judged} judged · "
            f"{counts.succeeded} succeeded · {counts.addressed} addressed · "
            f"{counts.attention} needing attention.** {_verdict_line(run)}"
        ),
    ]
    if run.addressed:
        lines += ["", "### Addressed", ""]
        lines += [
            "These boundaries are gone. Nothing was deleted with them — if the same "
            "structure comes back, its standing and its discussion come back with it.",
            "",
        ]
        for closed in run.addressed:
            lines.append(f"- **{closed.title}** — last seen as {closed.last_reference}.")
    surfaced = [item for item in run.surfaced if not item.holding]
    if surfaced:
        lines += ["", "### What this revision judged", ""]
        for item in surfaced:
            lines += _comment_boundary(
                item, workspace_url=workspace_url, review_id=run.review_id
            )
    held = run.held
    if held:
        lines += [
            "",
            "### Held on an open question",
            "",
            (
                "These verdicts rest on something the case does not state. They are reported "
                "and never blocking; answering in the workspace carries the review on."
            ),
            "",
        ]
        for item in held:
            lines += _comment_held(item, workspace_url=workspace_url, review_id=run.review_id)
    if not surfaced and not held and not run.addressed:
        lines += [
            "",
            "Nothing on this branch moved since the previous revision.",
        ]
    lines += [
        "",
        "---",
        "",
        f"Review `{run.review_id}` against `{run.base_branch_name}` — "
        f"{_carried_forward(run)}.",
    ]
    return "\n".join(lines)


def _comment_boundary(
    item: CiBoundary, *, workspace_url: str | None, review_id: str
) -> list[str]:
    reference = _linked(item, workspace_url, review_id)
    lines = [f"- **{reference} · {item.verdict_label}** *({_marks(item)})*"]
    lines.append(f"  {_excerpt(item.rationale)}")
    if item.decision is not None:
        lines.append(f"  *{_decision_line(item).strip()}*")
    return lines


def _comment_held(
    item: CiBoundary, *, workspace_url: str | None, review_id: str
) -> list[str]:
    reference = _linked(item, workspace_url, review_id)
    lines = [f"- **{reference} · {item.verdict_label}** — held"]
    for question in item.questions:
        lines.append(f"  *{question.reference}.* {question.question}")
    if not item.questions:
        # A hinge with no question composed across the set. Rare, and stated rather than
        # dropped: "held" with nothing after it reads as a rendering fault.
        lines.append("  The review recorded no question for this verdict.")
    return lines


def _marks(item: CiBoundary) -> str:
    marks = _state_marks(item)
    if item.blocking:
        marks.append("blocking")
    elif item.needs_attention:
        # Only where it is not already blocking, which says the same thing more loudly. Both
        # would read as two separate problems with one boundary.
        marks.append("needs attention")
    if item.verdict_reused_from is not None:
        marks.append("carried forward")
    return ", ".join(marks)


def _linked(item: CiBoundary, workspace_url: str | None, review_id: str) -> str:
    """The reference, as a link into the workspace where there is a workspace to link to.

    The fragment is the boundary's own reference, which is what the review page listens for:
    a reader arriving from a pull request lands on the row that was quoted at them rather
    than at the top of a report they then have to search.
    """

    if workspace_url is None:
        return item.reference
    base = workspace_url.rstrip("/")
    return f"[{item.reference}]({base}/reviews/{review_id}#{item.reference})"


__all__ = ["COMMENT_MARKER", "render_ci_comment", "render_ci_summary"]
