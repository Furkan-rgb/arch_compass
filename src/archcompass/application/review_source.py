"""The code a review's findings were measured from.

Every participant of every candidate already carries an exact span — path, first line, last
line — chosen by a deterministic detector at the moment the verdict was reached. What was
missing was only the text at those coordinates: the finding card printed `path:line` as a
label, and the conversation stages were given qualified names with `location` dropped, so a
reader asking "show me the code" was told the review did not contain it.

Selection is therefore already done, and this is delivery rather than retrieval. That
distinction is §12.0: the application decides what to look at and the model decides what it
means. A tool a model could call to fetch source would invert it and let the stage choose
its own evidence, which is the thing `tests/unit/test_boundaries.py` asserts against.

Nothing is stored. The spans are in the review; the text is read from the repository when
someone asks to see it. Storing snippets would change a stored shape for no gain and would
raise a separate question — whether the *judge* saw those lines — which belongs to a
decision about how boundaries are judged rather than to how they are read.
"""

from __future__ import annotations

from pathlib import Path

from archcompass.application.atlas_freshness import AtlasFreshnessService
from archcompass.domain.atlas import FindingParticipant, SourceLocation
from archcompass.domain.errors import (
    ArchCompassError,
    AtlasNotFoundError,
    PathValidationError,
)
from archcompass.domain.review import BoundaryExcerpt, BoundaryReview, ReviewedBoundary
from archcompass.ports.atlas import SourceReader
from archcompass.ports.repositories import AtlasRepository

#: The most lines one participant's excerpt may carry, before context is added. A detector
#: picks declaration spans — one line for a duplicated constant, a handful for a class — so
#: this is a guard against a pathological span rather than a budget anyone meets.
MAX_EXCERPT_LINES = 60

#: How much surrounding code a reader may unfold. Bounded here rather than taken from the
#: request unchecked: the request says how much context is wanted, and this says how much
#: the workspace will read whatever it asks for.
MAX_CONTEXT_LINES = 20


class ReviewSourceService:
    """Resolve a review's recorded spans to the code at them."""

    def __init__(
        self,
        *,
        atlases: AtlasRepository,
        source_reader: SourceReader,
        freshness: AtlasFreshnessService,
    ) -> None:
        self._atlases = atlases
        self._source_reader = source_reader
        self._freshness = freshness

    def for_review(
        self,
        review: BoundaryReview,
        *,
        reference: str | None = None,
        context_lines: int = 0,
    ) -> list[BoundaryExcerpt]:
        """Every located participant of this review, or of one boundary of it.

        Reference-scoped by default at the caller's choice, so a page asks for what it is
        about to draw rather than for the whole repository's worth of spans.

        A boundary whose code cannot be shown still returns an excerpt, carrying the reason
        instead of the text. Three ways that happens and they are not the same: the
        repository has moved on since the review ran, so the lines judged are not the lines
        there now; the repository is gone; or the boundary was never written, which is what a
        greenfield candidate is (§4.1). A reader is better served by which of those it was
        than by an empty panel.
        """

        report = review.report
        if report is None:
            return []
        wanted = [
            item
            for item in report.reviewed
            if reference is None or item.reference == reference
        ]
        if not wanted:
            return []

        context = max(0, min(context_lines, MAX_CONTEXT_LINES))
        root, refusal = self._readable_root(review)
        return [
            excerpt
            for boundary in wanted
            for excerpt in self._for_boundary(boundary, root, refusal, context)
        ]

    def _for_boundary(
        self,
        boundary: ReviewedBoundary,
        root: Path | None,
        refusal: str,
        context: int,
    ) -> list[BoundaryExcerpt]:
        excerpts: list[BoundaryExcerpt] = []
        for participant in boundary.candidate.participants:
            location = participant.location
            if location is None:
                # A boundary that was never written — what a greenfield candidate is (§4.1)
                # — or a node the parser could not place. Either way there is nothing to
                # read, and that is a statement rather than a failure.
                excerpts.append(
                    self._without_text(
                        boundary.reference,
                        participant,
                        None,
                        "This participant has no recorded source span, so there is no code "
                        "to show for it.",
                    )
                )
                continue
            if root is None:
                excerpts.append(
                    self._without_text(boundary.reference, participant, location, refusal)
                )
                continue
            excerpts.append(
                self._read(boundary.reference, participant, location, root, context)
            )
        return excerpts

    def _read(
        self,
        reference: str,
        participant: FindingParticipant,
        location: SourceLocation,
        root: Path,
        context: int,
    ) -> BoundaryExcerpt:
        try:
            text = self._source_reader.excerpt(
                root=root,
                relative_path=location.path,
                start_line=max(1, location.start_line - context),
                end_line=location.end_line + context,
                max_lines=MAX_EXCERPT_LINES + 2 * MAX_CONTEXT_LINES,
            )
        except (PathValidationError, OSError, UnicodeDecodeError) as error:
            return self._without_text(
                reference,
                participant,
                location,
                f"This file could not be read: {error}",
            )
        if not text.strip():
            # An empty span is refused rather than recorded as text, because an excerpt with
            # nothing in it reads as "there is no code here" when it means "the file no
            # longer has those lines".
            return self._without_text(
                reference,
                participant,
                location,
                "Those lines are no longer present in this file.",
            )
        return BoundaryExcerpt(
            reference=reference,
            qualified_name=participant.qualified_name,
            role=participant.role,
            location=location,
            text=text,
        )

    @staticmethod
    def _without_text(
        reference: str,
        participant: FindingParticipant,
        location: SourceLocation | None,
        reason: str,
    ) -> BoundaryExcerpt:
        return BoundaryExcerpt(
            reference=reference,
            qualified_name=participant.qualified_name,
            role=participant.role,
            location=location,
            unavailable=reason,
        )

    def _readable_root(self, review: BoundaryReview) -> tuple[Path | None, str]:
        """The repository this review judged, if it is still the one that was judged.

        Freshness is checked once for the whole request rather than per participant: it is a
        property of the repository against the pinned atlas, and asking it eight times would
        give eight chances to answer differently mid-page.
        """

        try:
            atlas = self._atlases.get(review.atlas_version_id)
        except (AtlasNotFoundError, ArchCompassError) as error:
            return None, f"The atlas this review pinned is no longer available: {error}"
        try:
            self._freshness.ensure_fresh(atlas)
        except ArchCompassError as error:
            # Captioned rather than blocked. The lines that were judged are not the lines
            # there now, and saying so is a more useful answer than silence — but showing
            # them as though they were reviewed would be a false one.
            return None, (
                "This repository has changed since the review ran, so the code at these "
                f"lines is no longer what was judged. {error}"
            )
        root = Path(atlas.version.root_path)
        if not root.is_dir():
            return None, f"The repository this review judged is no longer at {root}."
        return root, ""
