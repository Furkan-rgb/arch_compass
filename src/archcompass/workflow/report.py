"""The review, written as a document a person can read away from the workbench.

The report is what a review looks like when it leaves the product. It is attached to a pull
request by `archcompass ci --comment-file`, printed by `archcompass reviews show`, rendered
on the Report surface, and downloaded as Markdown — so it has to stand on its own. Nothing
in it may assume the reader can click anything.

The charter's rules apply the same way they do on screen, and this module is where they turn
into Markdown:

* **Lead with the identifier.** A heading names the code, not the sentence about the code.
  The version this replaced set the candidate's summary as an `##`, which produced headings
  like "`src.audiobook.preparation.providers.base.NarrationPreparationProvider` is
  implemented only by `…OllamaProvider`." — a wall of prose where a name should be, and
  unscannable in the one place scanning matters most.
* **The machine assembles, the model judges, the person decides.** The workbench keeps those
  apart with a gutter down the left of every finding. A document has no gutter, so the same
  distinction is carried by run-in labels: **Measured** is what the analyser counted,
  **Judged** is what the model concluded, and the absence of any third label is deliberate —
  standing decisions are a separate record and the footer says so.
* **Say where it came from.** Every finding carries its policies, its evidence locations and
  its detection rationale; the footer carries the model, the prompt, the retriever and the
  atlas the whole thing was read from.
* **Uncertainty is stated, not smoothed.** A held finding prints its hinge. A review that is
  still waiting says at the top that it is not final.
* **The second visit is the important one.** What moved since the previous review is a
  section, named by identifier, not a number in a summary line.
* **Nothing is inferred.** An empty section says it is empty rather than disappearing.

Deterministic: the same review composes the same bytes, so a report can be diffed between
revisions the way the reviews themselves can be.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from archcompass.domain import (
    AnswerStatus,
    ArchitectureCase,
    Candidate,
    Finding,
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
    Verdict,
)
from archcompass.domain.case import Question
from archcompass.domain.values import Measurement, MetricNature

#: The order a reader should meet verdicts in — what needs a human first. The same order the
#: attention queue uses, for the same reason.
_VERDICT_ORDER: tuple[Verdict, ...] = (Verdict.MATERIAL, Verdict.HELD, Verdict.CLEARED)

_VERDICT_MEANING: dict[Verdict, str] = {
    Verdict.MATERIAL: "The evidence supports an architectural concern worth acting on.",
    Verdict.HELD: "Judgement is waiting on context the repository cannot supply.",
    Verdict.CLEARED: "Assessed and found unproblematic.",
}

_COUNT_WORDS = (
    "no",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
)


def _count(value: int, singular: str, plural: str | None = None) -> str:
    """`3 candidates`, and `1 candidate` rather than `1 candidates`."""

    return f"{value} {singular if value == 1 else (plural or f'{singular}s')}"


def _sentence_count(value: int, singular: str, plural: str | None = None) -> str:
    """The same, spelled out where a sentence opens on it."""

    word = _COUNT_WORDS[value] if value < len(_COUNT_WORDS) else str(value)
    return f"{word} {singular if value == 1 else (plural or f'{singular}s')}"


def _sentence(text: str) -> str:
    """Model-authored prose, made safe to put another sentence after.

    A hinge arrives as a fragment — "the constraints this architecture has to respect" — and
    the report follows it with a sentence of its own. Without this the two run together and
    the document reads as though the model wrote both.
    """

    stripped = text.strip()
    if not stripped:
        return ""
    # Only where the first word is an ordinary word. Half of these sentences open on a
    # qualified name — `ports.Clock is implemented only by …` — and capitalising that
    # rewrites the identifier the whole document is keyed on.
    first = stripped.split(" ", 1)[0]
    if first.isalpha() and first.islower():
        stripped = stripped[:1].upper() + stripped[1:]
    return stripped if stripped[-1] in ".!?:" else f"{stripped}."


def _identity(candidate: Candidate) -> str:
    """What the candidate is called. Its first participant names the shape for a reader."""

    return candidate.participants[0].qualified_name


def _humanise(value: str) -> str:
    spaced = value.replace("_", " ").strip()
    return spaced[:1].upper() + spaced[1:] if spaced else value


def _ordered(findings: Iterable[Finding]) -> list[Finding]:
    """By identifier, so two runs of the same review produce the same document."""

    return sorted(findings, key=lambda finding: _identity(finding.candidate).lower())


def _location(finding: Finding) -> str | None:
    for evidence in finding.evidence:
        if evidence.location is None:
            continue
        span = evidence.location
        where = f"{span.path}:{span.start_line}"
        if span.end_line != span.start_line:
            where = f"{where}-{span.end_line}"
        return f"`{where}`"
    return None


def _reading(measurement: Measurement) -> str:
    """One measured quantity, said the way a sentence can hold it.

    `Measurement.display` is `"1 implementations"` — right on the workbench, where the value
    and its name sit on separate lines, and wrong in a sentence. The unit is singularised
    against the value here rather than in the domain, because the number is what the domain
    owns and the grammar is what a document needs.
    """

    unit = measurement.unit or measurement.name.replace("_", " ")
    if measurement.value == 1 and unit.endswith("s") and not unit.endswith("ss"):
        unit = unit[:-1]
    proxy = (
        " (a structural proxy, not a count)"
        if measurement.nature is MetricNature.STRUCTURAL_PROXY
        else ""
    )
    return f"{measurement.value:g} {unit}{proxy}".strip()


def _rationale(text: str) -> str:
    """The detector's account of itself, minus its bookkeeping.

    A rationale reads "Detected deterministically from the repository atlas; participant
    fingerprint 39cc5c…". The clause is the sentence; the fingerprint is an id, and an id in
    the middle of a paragraph is the workbench's Technical detail leaking into the record's
    readable projection.
    """

    return text.split(";")[0].strip().rstrip(".").lower()


def _measured(finding: Finding) -> str:
    """What the deterministic half of the review established, in one paragraph.

    Measurements keep their own honesty: a `structural_proxy` says so, because a proxy and a
    count lead to opposite verdicts and the number alone cannot tell them apart.
    """

    parts: list[str] = []
    readings = [_reading(item) for item in finding.candidate.measurements]
    if readings:
        parts.append(", ".join(readings))
    involved = [participant.qualified_name for participant in finding.candidate.participants]
    if len(involved) > 1:
        parts.append("across " + ", ".join(f"`{name}`" for name in involved))
    where = _location(finding)
    if where:
        parts.append(f"pinned at {where}")
    rationale = _rationale(finding.candidate.detection_rationale)
    if rationale:
        parts.append(rationale)
    if not parts:
        return ""
    return f"**Measured.** {'; '.join(parts)}."


def _entry(finding: Finding, *, delta_state: str | None, measured: bool = True) -> str:
    """One finding.

    The order is the order the three jobs happen in: what was counted, then what the model
    concluded from it, then the policies it bore on, then the response ArchCompass would
    recommend — which is a recommendation and says so.

    A cleared finding skips the measurements. The reasoning is the point of a cleared
    verdict — "we looked at this and here is why it is fine" — and the readings behind it are
    what would turn forty cleared candidates into a document nobody finishes. It keeps its
    heading and its reasoning, because a report of only problems reads the same whether
    everything was examined and cleared or nothing was examined at all.
    """

    lines = [f"### `{_identity(finding.candidate)}`", ""]

    context = [_humanise(finding.candidate.pattern)]
    if delta_state:
        context.append(delta_state)
    if finding.reused_from_review_id:
        context.append(f"carried from review `{finding.reused_from_review_id}`")
    lines.append(f"{_sentence(finding.candidate.summary)} *{' · '.join(context)}*")
    lines.append("")

    reading = _measured(finding) if measured else ""
    if reading:
        lines.extend([reading, ""])

    lines.extend([f"**Judged {finding.verdict.value}.** {_sentence(finding.reasoning)}", ""])

    if finding.hinge:
        lines.extend(
            [
                f"**Waiting on a person.** {_sentence(finding.hinge)} Answering it produces "
                "the next case revision and re-judges what it touches.",
                "",
            ]
        )

    for bearing in finding.policies:
        lines.extend(
            [
                f"**Bears on {bearing.policy.title}** "
                f"(`{bearing.policy.id}`, {bearing.policy.strength.value}) — {bearing.reasoning}",
                "",
            ]
        )

    if finding.recommended_response:
        lines.extend(
            [
                f"**Recommended response.** {_sentence(finding.recommended_response)} "
                "ArchCompass does not write the fix; acting on this is the team's.",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _delta_states(delta: ReviewDelta) -> dict[str, str]:
    """Where each candidate stands against the previous review, by identifier."""

    states = {str(item.id): "new" for item in delta.new}
    for change in delta.changed:
        causes = ", ".join(cause.value for cause in change.causes)
        states[str(change.candidate.id)] = f"changed ({causes})" if causes else "changed"
    for item in delta.unchanged:
        states[str(item.id)] = "unchanged"
    return states


def _moved(delta: ReviewDelta, previous_sequence: int | None) -> str:
    """What is different from last time — the section a returning reader opens first."""

    if previous_sequence is None:
        return (
            "This is the first review of this case, so every candidate below is new and there "
            "is nothing yet to compare it against.\n"
        )

    lines: list[str] = []
    if delta.new:
        lines.append(
            f"**New** — {_count(len(delta.new), 'candidate')} not in review {previous_sequence}."
        )
        lines.append("")
        # Names only. The finding above already carries the sentence, and this section
        # exists to be scanned for *which* things moved.
        lines.extend(
            f"- `{_identity(item)}`"
            for item in sorted(delta.new, key=lambda item: _identity(item).lower())
        )
        lines.append("")
    if delta.changed:
        lines.append(
            f"**Changed** — {_count(len(delta.changed), 'candidate')} the same as "
            "before but no longer in the same state."
        )
        lines.append("")
        lines.extend(
            f"- `{_identity(change.candidate)}` — "
            f"{', '.join(cause.value for cause in change.causes) or 'changed'}"
            for change in sorted(
                delta.changed, key=lambda change: _identity(change.candidate).lower()
            )
        )
        lines.append("")
    if delta.addressed:
        lines.append(
            f"**Addressed** — {_count(len(delta.addressed), 'candidate')} raised in an "
            "earlier review and no longer detected."
        )
        lines.append("")
        lines.extend(
            f"- {item.title} — last judged {item.last_verdict.value}"
            for item in sorted(delta.addressed, key=lambda item: item.title.lower())
        )
        lines.append("")
    if not lines:
        return (
            f"Nothing moved since review {previous_sequence}: every candidate is the one that "
            "was there before, in the state it was in.\n"
        )
    if delta.unchanged:
        lines.append(
            f"{_sentence_count(len(delta.unchanged), 'candidate').capitalize()} carried forward "
            "unchanged."
        )
    return "\n".join(lines).rstrip() + "\n"


def _questions(questions: Sequence[Question], *, waiting: bool) -> str:
    """What the repository could not answer.

    A waiting review is asking. A concluded review that still carries questions was ended
    deliberately with the uncertainty preserved — the charter's "conclude with remaining
    uncertainty" — and calling those "open questions" would read as an oversight rather than
    as a decision somebody took.
    """

    lines: list[str] = []
    for question in questions:
        lines.append(f"- **{question.text}** ({question.facet.value}, round {question.round})")
        if question.options:
            lines.extend(f"  - {option}" for option in question.options)
    lines.append("")
    lines.append(
        "Answering these records them on the architecture case as a new revision and re-judges "
        "the candidates they touch. Anything left unanswered is recorded as explicitly skipped, "
        "not guessed at."
        if waiting
        else "This review was concluded with these still unanswered. They are recorded as "
        "unresolved rather than guessed at; answering them later produces the next case "
        "revision and re-judges what they touch."
    )
    return "\n".join(lines) + "\n"


def _judged_against(case: ArchitectureCase) -> str:
    """The human context the verdicts were reached inside.

    Printed rather than referenced, so a reader six months later can tell whether a verdict
    turned on something the team has since changed their mind about.
    """

    lines: list[str] = []
    if case.constraints:
        lines.append("**Constraints**")
        lines.append("")
        lines.extend(
            f"- *{_humanise(constraint.facet.value)}* — {constraint.text}"
            for constraint in case.constraints
        )
        lines.append("")
    if case.decisions:
        lines.append("**Decisions already taken**")
        lines.append("")
        lines.extend(f"- {decision.text}" for decision in case.decisions)
        lines.append("")
    if case.answers:
        lines.append("**Clarifications answered**")
        lines.append("")
        for answer in case.answers:
            said = (
                answer.value
                if answer.status is AnswerStatus.ANSWERED and answer.value
                else "*explicitly skipped*"
            )
            lines.append(f"- {answer.question.text} — {said} ({answer.actor})")
        lines.append("")
    if not lines:
        return (
            f"Case revision {case.revision} is empty. A case starts empty and fills in as "
            "reviews ask for what they actually need, so these verdicts were reached from the "
            "code and the policy corpus alone.\n"
        )
    return "\n".join(lines).rstrip() + "\n"


def _provenance(
    *,
    repository: RepositoryRef,
    atlas: RepositoryAtlas,
    case: ArchitectureCase,
    findings: Sequence[Finding],
    retrievers: Sequence[str],
) -> str:
    models = sorted({item.model_identity for item in findings if item.model_identity})
    prompts = sorted({item.prompt_identity for item in findings if item.prompt_identity})
    parser = " ".join(f"{key}={value}" for key, value in atlas.parser_configuration) or "—"
    lines = [
        f"- **Judged by** {', '.join(f'`{item}`' for item in models) or '—'}"
        f" using {', '.join(f'`{item}`' for item in prompts) or 'no recorded prompt'}",
        f"- **Policies retrieved by** {', '.join(f'`{item}`' for item in retrievers) or '—'}",
        f"- **Read from** an atlas of {_count(len(atlas.nodes), 'node')} and "
        f"{_count(len(atlas.edges), 'edge')}, parsed with `{parser}`",
        f"- **Repository** `{repository.path}`"
        + (f", branch `{repository.branch}`" if repository.branch else "")
        + (f", commit `{repository.commit}`" if repository.commit else ""),
        f"- **Case** `{case.id}` at revision {case.revision}",
    ]
    return "\n".join(lines) + "\n"


def _blind_spots(findings: Sequence[Finding]) -> str:
    """What the detectors could not see, once per detector.

    A limitation belongs to the detector, not to the candidate: every sole-implementation
    finding carries the same sixty words about dynamically registered implementations. Six
    of them in one document is a wall that teaches a reader to skip the paragraph, which is
    the opposite of what stating a limit is for — so it is said once, under the pattern it
    belongs to, and it is said at the end because it qualifies everything above it.
    """

    # Keyed on the limitation, not on the detector. Two detectors that state the same limit
    # in the same words state it once here, under both their names — otherwise the section
    # reintroduces the wall it exists to remove.
    seen: dict[str, set[str]] = {}
    for finding in findings:
        limit = finding.candidate.limitations.strip()
        if limit:
            seen.setdefault(limit, set()).add(finding.candidate.pattern)
    if not seen:
        return ""
    lines = [
        "## What this review could not see",
        "",
        "Every verdict above was reached inside these limits. They belong to the detectors, "
        "not to any one finding.",
        "",
    ]
    for limit, patterns in sorted(seen.items(), key=lambda item: sorted(item[1])):
        named = ", ".join(_humanise(pattern) for pattern in sorted(patterns))
        lines.extend([f"**{named}** — {limit}", ""])
    return "\n".join(lines).rstrip() + "\n"


def compose_markdown_report(
    *,
    repository: RepositoryRef,
    atlas: RepositoryAtlas,
    case: ArchitectureCase,
    findings: Sequence[Finding],
    questions: Sequence[Question],
    delta: ReviewDelta,
    previous: Review | None,
    retrievers: Sequence[str],
    sequence: int,
    waiting: bool,
) -> str:
    """The whole document.

    Takes the parts rather than a `ReviewDraft` so that it is a pure function of what it
    prints, and so a caller holding a stored `Review` can render the same document without
    reconstructing a draft.
    """

    name = repository.path.name or str(repository.path)
    by_verdict = {
        verdict: [finding for finding in findings if finding.verdict is verdict]
        for verdict in _VERDICT_ORDER
    }
    states = _delta_states(delta)
    previous_sequence = None if previous is None else previous.sequence

    identity = [f"review {sequence}", f"case revision {case.revision}"]
    if repository.branch:
        identity.insert(0, f"branch `{repository.branch}`")
    if repository.commit:
        # Shortened here and printed in full in the footer: the identity line is scanned, and
        # forty characters of hex in it is the line's whole width.
        identity.insert(1 if repository.branch else 0, f"commit `{repository.commit[:10]}`")

    lines = [f"# Architecture review — {name}", "", " · ".join(identity), ""]

    if waiting:
        lines.extend(
            [
                f"> **Not final.** This review is waiting on {_count(len(questions), 'answer')} "
                "before it can finish judging. The verdicts below are what it has so far.",
                "",
            ]
        )

    material = len(by_verdict[Verdict.MATERIAL])
    held = len(by_verdict[Verdict.HELD])
    cleared = len(by_verdict[Verdict.CLEARED])
    if findings:
        headline = (
            f"{_sentence_count(len(findings), 'candidate').capitalize()} judged: "
            f"**{material} material**, {held} held, {cleared} cleared."
        )
        if previous_sequence is not None:
            moved = len(delta.new) + len(delta.changed)
            headline += f" {moved} new or changed since review {previous_sequence}"
            headline += (
                f", and {_count(len(delta.addressed), 'earlier finding')} no longer detected."
                if delta.addressed
                else "."
            )
        lines.extend([headline, ""])
    else:
        lines.extend(
            [
                "No architectural candidates were detected in this snapshot. That is a statement "
                "about what the deterministic analysis found, not a claim that the architecture "
                "is sound.",
                "",
            ]
        )

    for verdict in _VERDICT_ORDER:
        group = by_verdict[verdict]
        if not group:
            continue
        lines.extend([f"## {verdict.value.capitalize()} — {len(group)}", ""])
        lines.extend([f"*{_VERDICT_MEANING[verdict]}*", ""])
        for finding in _ordered(group):
            lines.extend(
                [
                    _entry(
                        finding,
                        delta_state=states.get(str(finding.candidate.id)),
                        measured=verdict is not Verdict.CLEARED,
                    ),
                    "",
                ]
            )

    blind_spots = _blind_spots(findings)
    if blind_spots:
        lines.extend([blind_spots, ""])

    lines.extend(
        [
            f"## What moved since review {previous_sequence}"
            if previous_sequence is not None
            else "## What moved",
            "",
            _moved(delta, previous_sequence),
            "",
        ]
    )

    if questions:
        heading = (
            f"## Open questions — {len(questions)}"
            if waiting
            else f"## Left unanswered — {len(questions)}"
        )
        lines.extend([heading, "", _questions(questions, waiting=waiting), ""])

    lines.extend(["## Judged against", "", _judged_against(case), ""])

    lines.extend(
        [
            "## Where this came from",
            "",
            _provenance(
                repository=repository,
                atlas=atlas,
                case=case,
                findings=findings,
                retrievers=retrievers,
            ),
            "",
            "This document is what ArchCompass concluded. What the team decided to do about it "
            "— accepted, waived or parked — is recorded separately as standing decisions on the "
            "branch, because a decision never edits a judgement.",
            "",
        ]
    )

    # Sections are assembled from parts that each end cleanly, so the joins leave runs of
    # blank lines. Collapsed here rather than policed at every append: the report is a file
    # people diff between revisions, and whitespace noise is diff noise.
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


__all__ = ["compose_markdown_report"]
