"""What the source service says about the text it serves, at the edges.

The ordinary path — a detector's small span read whole — is exercised end-to-end in the
integration suites. These are the edge answers: a span the excerpt ceiling cuts short must
say so, because a stage shown half a function with no marker answers from the half it saw,
and a stored review from before these captions existed must still read back.
"""

from __future__ import annotations

from pathlib import Path

from tests import reasoning_support

from archcompass.adapters.analysis.source_reader import SafeSourceReader
from archcompass.application.review_source import (
    MAX_CONTEXT_LINES,
    MAX_EXCERPT_LINES,
    MAX_LEADING_COMMENT_LINES,
    ReviewSourceService,
)
from archcompass.domain.atlas import (
    FindingCandidate,
    FindingParticipant,
    FindingPattern,
    SourceLocation,
)
from archcompass.domain.review import BoundaryExcerpt


def _service() -> ReviewSourceService:
    # Only the reader is exercised by `_read`; the repositories and freshness service are
    # for the review-scoped entry points and may be absent here.
    return ReviewSourceService(
        atlases=None,  # type: ignore[arg-type]
        source_reader=SafeSourceReader(),
        freshness=None,  # type: ignore[arg-type]
    )


def test_a_span_the_ceiling_clips_says_where_the_shown_text_ends(tmp_path: Path) -> None:
    (tmp_path / "long.py").write_text(
        "\n".join(f"line_{number} = {number}" for number in range(1, 201)) + "\n",
        encoding="utf-8",
    )
    ceiling = MAX_EXCERPT_LINES + 2 * MAX_CONTEXT_LINES
    participant = FindingParticipant(
        node_id="long",
        qualified_name="package.long",
        role="States the whole file.",
        location=SourceLocation(path="long.py", start_line=1, end_line=200),
    )

    excerpt = _service()._read(
        "BR-001", participant, participant.location, tmp_path, 0
    )

    assert len(excerpt.text.splitlines()) == ceiling
    assert excerpt.truncated_after_line == ceiling, (
        "a clipped excerpt must say where the shown text ends"
    )


def test_a_span_read_whole_carries_no_truncation_mark(tmp_path: Path) -> None:
    (tmp_path / "short.py").write_text("VALUE = 1\nOTHER = 2\n", encoding="utf-8")
    participant = FindingParticipant(
        node_id="short",
        qualified_name="package.short",
        role="States VALUE.",
        location=SourceLocation(path="short.py", start_line=1, end_line=2),
    )

    excerpt = _service()._read(
        "BR-001", participant, participant.location, tmp_path, 0
    )

    assert excerpt.text
    assert excerpt.truncated_after_line is None


def test_an_excerpt_stored_before_the_captions_existed_reads_back() -> None:
    """The captions are optional with defaults for the reason every added field here is:
    a stored review is validated against the current schema and nothing shims it."""

    stored = BoundaryExcerpt.model_validate(
        {
            "reference": "BR-001",
            "qualified_name": "package.Voices",
            "role": "States the voice list.",
            "text": "BUILT_IN_VOICES = []",
        }
    )

    assert stored.truncated_after_line is None
    assert stored.provenance == ""


def test_a_review_still_shows_the_code_it_judged_when_the_repository_is_gone() -> None:
    """The property the whole conversation flow rests on, now that repositories are swept.

    A hosted visitor's fetched source does not outlive their session, and may not outlive the
    next visitor's fetch: the instance holds a bounded amount of code and deletes the least
    recently used to stay inside it. So a review discussed an hour later is a review whose
    repository may no longer be on disk, and asking about it must still be answerable.

    It is, because the evidence was pinned into the report when the review ran rather than
    read again when it is asked about. Asserted here because nothing else asserted it, and
    because the sweeping that makes it matter is new.
    """

    pinned = BoundaryExcerpt(
        reference="BR-001",
        qualified_name="package.Voices",
        role="States the voice list.",
        text="BUILT_IN_VOICES = []",
    )
    ran = reasoning_support.review(
        [reasoning_support.reviewed_boundary("BR-001", "Voices", material=False)]
    )
    # Frozen models, so the review is rebuilt rather than edited: the excerpts pinned when
    # it ran, and a repository root that is not there any more.
    judged = ran.model_copy(
        update={
            "report": ran.report.model_copy(update={"excerpts": [pinned]}),
            "repository_root": "/a/repository/that/no/longer/exists",
        }
    )

    served = _service().for_review(judged)

    assert [excerpt.text for excerpt in served] == ["BUILT_IN_VOICES = []"]


def _candidate(*participants: FindingParticipant) -> FindingCandidate:
    return FindingCandidate(
        pattern=FindingPattern.DUPLICATED_KNOWLEDGE,
        summary="RETRY_LIMIT is stated in 2 modules with the same value.",
        participants=list(participants),
        limitations="Compared by name in one snapshot.",
    )


def _states(path: str, line: int) -> FindingParticipant:
    return FindingParticipant(
        node_id=path,
        qualified_name=path.removesuffix(".py"),
        role="States RETRY_LIMIT at this location.",
        location=SourceLocation(path=path, start_line=line, end_line=line),
    )


def test_a_candidate_is_served_the_code_at_every_span_it_records(tmp_path: Path) -> None:
    """What the judging stage was missing: its own candidate's lines, before it decides."""

    (tmp_path / "left.py").write_text("RETRY_LIMIT = 5\n", encoding="utf-8")
    (tmp_path / "right.py").write_text("OTHER = 1\nRETRY_LIMIT = 5\n", encoding="utf-8")
    candidate = _candidate(_states("left.py", 1), _states("right.py", 2))

    served = _service().for_candidate(candidate, root=tmp_path)

    assert [excerpt.qualified_name for excerpt in served] == ["left", "right"]
    assert served[0].text == "    1 | RETRY_LIMIT = 5"
    assert served[1].text == "    2 | RETRY_LIMIT = 5"


def test_a_definition_is_served_with_the_comment_block_written_above_it(
    tmp_path: Path,
) -> None:
    """The decisive fact is routinely in the comment and never in the span.

    A constant's span is the line that assigns it, and what a constant *means* is written
    directly above it — "the vendor allows five attempts", "unrelated to the retry limit in
    billing". A judging stage shown the assignment alone was being asked whether two copies
    state one fact while the sentence answering it sat one line out of frame.
    """

    (tmp_path / "left.py").write_text(
        "import os\n\n# AcmeHub's guidance is five attempts.\n# Keep it beside billing's copy.\n"
        "RETRY_LIMIT = 5\n",
        encoding="utf-8",
    )
    candidate = _candidate(_states("left.py", 5))

    served = _service().for_candidate(candidate, root=tmp_path)

    assert served[0].text.splitlines() == [
        "    3 | # AcmeHub's guidance is five attempts.",
        "    4 | # Keep it beside billing's copy.",
        "    5 | RETRY_LIMIT = 5",
    ]
    assert served[0].location is not None
    assert served[0].location.start_line == 3, (
        "the excerpt's own coordinates must say where the text it carries begins"
    )


def test_a_comment_a_blank_line_away_belongs_to_something_else(tmp_path: Path) -> None:
    """The run has to touch the span, or a module docstring becomes every constant's meaning."""

    (tmp_path / "left.py").write_text(
        "# A note about the imports below.\n\nRETRY_LIMIT = 5\n",
        encoding="utf-8",
    )
    candidate = _candidate(_states("left.py", 3))

    served = _service().for_candidate(candidate, root=tmp_path)

    assert served[0].text == "    3 | RETRY_LIMIT = 5"


def test_the_widening_stops_after_a_bounded_run_of_comments(tmp_path: Path) -> None:
    """A file that opens with forty lines of licence is not forty lines of context."""

    preamble = "".join(f"# licence line {number}\n" for number in range(1, 41))
    (tmp_path / "left.py").write_text(f"{preamble}RETRY_LIMIT = 5\n", encoding="utf-8")
    candidate = _candidate(_states("left.py", 41))

    served = _service().for_candidate(candidate, root=tmp_path)

    lines = served[0].text.splitlines()
    assert len(lines) == MAX_LEADING_COMMENT_LINES + 1
    assert lines[0].strip().startswith("29 |")


def test_the_excerpt_ceiling_still_applies_after_the_span_has_been_widened(
    tmp_path: Path,
) -> None:
    """Widening adds context to a span; it does not buy the span a larger budget."""

    (tmp_path / "long.py").write_text(
        "# a leading note\n" + "".join(f"line_{number} = {number}\n" for number in range(1, 201)),
        encoding="utf-8",
    )
    ceiling = MAX_EXCERPT_LINES + 2 * MAX_CONTEXT_LINES
    candidate = _candidate(
        FindingParticipant(
            node_id="long",
            qualified_name="long",
            role="States the whole file.",
            location=SourceLocation(path="long.py", start_line=2, end_line=201),
        )
    )

    served = _service().for_candidate(candidate, root=tmp_path)

    assert len(served[0].text.splitlines()) == ceiling
    assert served[0].truncated_after_line == ceiling


def test_a_participant_with_no_span_says_so_rather_than_being_dropped(tmp_path: Path) -> None:
    """A payload short of one participant reads as a candidate with fewer participants."""

    candidate = _candidate(
        FindingParticipant(node_id="proposed", qualified_name="package.Proposed", role="Proposed.")
    )

    served = _service().for_candidate(candidate, root=tmp_path)

    assert len(served) == 1
    assert served[0].text == ""
    assert "no recorded source span" in served[0].unavailable
