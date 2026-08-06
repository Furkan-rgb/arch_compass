"""What the source service says about the text it serves, at the edges.

The ordinary path — a detector's small span read whole — is exercised end-to-end in the
integration suites. These are the edge answers: a span the excerpt ceiling cuts short must
say so, because a stage shown half a function with no marker answers from the half it saw,
and a stored review from before these captions existed must still read back.
"""

from __future__ import annotations

from pathlib import Path

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
