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
    ReviewSourceService,
)
from archcompass.domain.atlas import FindingParticipant, SourceLocation
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
