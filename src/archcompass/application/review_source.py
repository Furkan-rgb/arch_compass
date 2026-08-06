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

The text is read once, when the review completes, and pinned on the review with everything
else the run depended on. Reading it live instead was the earlier design and it did not
survive contact with a repository being worked on: one comment appended to a file no finding
cited took a six-boundary review from sixteen excerpts to none, because freshness is a single
repository-wide fingerprint. A review is supposed to be readable for as long as it is kept.

So this module does three things that look alike and are not. `for_boundaries` reads the
repository — the one place text is produced, used when the review completes and when a reader
asks to unfold surrounding lines. `for_review` serves what the review already holds, and
reads only when it holds nothing, which is a review stored before excerpts were pinned.
`content_fingerprints` reads the same spans through the same reader for a different purpose
entirely: nobody sees the text, and what comes back decides whether a boundary's verdict has
to be reached again at all. It lives here because there should be exactly one path that reads
source out of an analysed repository, not because it is about presentation.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from archcompass.application.atlas_freshness import AtlasFreshnessService
from archcompass.domain.atlas import FindingCandidate, FindingParticipant, SourceLocation
from archcompass.domain.atlas_map import AtlasMap, compact_atlas_map
from archcompass.domain.errors import (
    ArchCompassError,
    AtlasNotFoundError,
    PathValidationError,
)
from archcompass.domain.fingerprint import content_fingerprint
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

#: How far into a file a fingerprinted span may reach. Far larger than an excerpt, because
#: nothing is being shown to anybody: this is a ceiling on how much of a generated or vendored
#: file is hashed, not a budget on how much a reader is asked to look at.
MAX_FINGERPRINTED_LINES = 20_000


def _span(text: str, location: SourceLocation) -> str:
    """The recorded lines out of a file already read, as the code says them.

    Sliced here rather than read per participant: several participants routinely sit in one
    module, and a read per span would open the same file once for each of them.
    """

    lines = text.splitlines()
    return "\n".join(lines[location.start_line - 1 : location.end_line])


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
        # One entry, keyed by atlas version. Conversation evidence is reassembled on every
        # turn, and the atlas behind it is a full nodes-edges-metrics blob; a turn about
        # the same review must not reload it to fold it to the same map.
        self._map_cache: tuple[str, AtlasMap] | None = None

    def for_review(
        self,
        review: BoundaryReview,
        *,
        reference: str | None = None,
        context_lines: int = 0,
    ) -> list[BoundaryExcerpt]:
        """Every located participant of this review, or of one boundary of it.

        What the review holds, which is the code as it was when the verdicts were reached.
        That is what a reader of a review wants and what the answering stage must be shown:
        the alternative — re-reading a repository that has since moved on — answers "this has
        changed, so there is nothing to show" about lines the record contains.

        Reference-scoped at the caller's choice, so a page asks for what it is about to draw.

        `context_lines` is the one thing the stored copy cannot serve, because surrounding
        code was never recorded. That is a read against the repository as it is now, and it
        is allowed to fail: unfolding more is browsing, not evidence, so a repository that
        has changed simply keeps the lines that were judged rather than losing them too.

        A review stored before excerpts were pinned holds none, and falls through to a live
        read exactly as it did before — including the reasons a span cannot be shown.
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
        if report.excerpts and not context:
            references = {item.reference for item in wanted}
            return [
                excerpt
                for excerpt in report.excerpts
                if excerpt.reference in references
            ]
        if report.excerpts:
            # Unfolding was asked for. Read it now, and fall back to the pinned copy where
            # the repository can no longer answer — an excerpt that could not grow is a
            # better result than one that disappeared. The substitute carries a provenance
            # caption rather than passing as a live read: the reader is looking at the code
            # as it was judged, and the difference is worth a sentence exactly when the
            # repository has moved on.
            expanded = self._read_boundaries(review, wanted, context)
            return [
                self._grown_or_pinned(live, stored)
                for live, stored in zip(
                    expanded, self._pinned_for(report.excerpts, expanded), strict=True
                )
            ]
        return self._read_boundaries(review, wanted, context)

    def atlas_map_for(self, review: BoundaryReview) -> AtlasMap:
        """The pinned atlas folded to a map a conversation stage can carry.

        No freshness check, deliberately: the map describes the structure the review was
        judged against, which is what a conversation pinned to that review should be shown
        — the pinned copy is the right copy even when the repository has moved on. Only an
        atlas the workspace no longer holds produces a map that says so instead.
        """

        if self._map_cache is not None and self._map_cache[0] == review.atlas_version_id:
            return self._map_cache[1]
        try:
            atlas = self._atlases.get(review.atlas_version_id)
        except (AtlasNotFoundError, ArchCompassError) as error:
            return AtlasMap(
                unavailable=f"The atlas this review pinned is no longer available: {error}"
            )
        folded = compact_atlas_map(atlas)
        self._map_cache = (review.atlas_version_id, folded)
        return folded

    def content_fingerprints(
        self,
        candidates: Sequence[FindingCandidate],
        *,
        root: Path,
    ) -> dict[str, str]:
        """What the code under each candidate says, hashed, keyed by `candidate_id`.

        The other half of a boundary's inputs identity, and the term the verdict cache used to
        be missing. A shape fingerprint is a pattern and some participant names, so rewriting
        a class body without renaming anything left the key identical and carried the previous
        verdict for ever — the advisor confidently reporting a judgement about code that no
        longer existed.

        Read through the same safe reader that produces the excerpts, at the same spans, for
        the same reason: it is the one path that cannot escape the analysed repository, and a
        second way of reading source would be a second thing to get wrong. What is different
        is the moment. Excerpts are read when the review completes, because they are evidence
        for a reader; this is read at detection time, before the first model call, because it
        decides whether there is a model call to make.

        Files are read once, not once per participant. Several participants of several
        candidates routinely sit in one module — that is what a duplicated constant *is* — and
        a per-participant read would open the same file a dozen times to answer one question.

        A span that cannot be read contributes nothing rather than raising. The repository was
        confirmed fresh before this runs, so an unreadable file here is an unusual failure and
        not a stale review; refusing to judge would be a worse answer than judging with one
        participant's text missing, and the absence is stable, so it does not manufacture a
        different fingerprint on every run.
        """

        texts: dict[str, str] = {}
        fingerprints: dict[str, str] = {}
        for candidate in candidates:
            sources: list[tuple[str, str]] = []
            for participant in candidate.participants:
                location = participant.location
                if location is None:
                    # A participant with no span — a proposed boundary, or a node the parser
                    # could not place. There is no code to have changed, and saying so with an
                    # empty text is stable across runs.
                    sources.append((participant.qualified_name, ""))
                    continue
                if location.path not in texts:
                    texts[location.path] = self._whole_file(root, location.path)
                sources.append(
                    (
                        participant.qualified_name,
                        _span(texts[location.path], location),
                    )
                )
            fingerprints[candidate.candidate_id] = content_fingerprint(sources)
        return fingerprints

    def _whole_file(self, root: Path, relative_path: str) -> str:
        """One participant's file, through the reader that cannot leave the repository.

        `MAX_FINGERPRINTED_LINES` rather than the excerpt ceiling, because this is not an
        excerpt: a class near the end of a long module has to be reachable, and a bound that
        stopped short would give every boundary past it the same fingerprint whatever its
        code said. The bound is still there — a generated file of a million lines should not
        be hashed whole — and a span beyond it is treated as unreadable, which re-judges the
        boundary rather than carrying it on a fingerprint that no longer means anything.
        """

        try:
            return self._source_reader.excerpt(
                root=root,
                relative_path=relative_path,
                start_line=1,
                end_line=MAX_FINGERPRINTED_LINES,
                max_lines=MAX_FINGERPRINTED_LINES,
                numbered=False,
            )
        except (PathValidationError, OSError, UnicodeDecodeError):
            return ""

    def for_boundaries(
        self,
        boundaries: list[ReviewedBoundary],
        *,
        root: Path,
        context_lines: int = 0,
    ) -> list[BoundaryExcerpt]:
        """Read the code at these boundaries' spans from a repository already known fresh.

        The completing run's entry point, and the only one that does not start from a stored
        review — there is not one yet. Freshness is the caller's: `ReviewService` checked it
        before the first model call and nothing has been indexed since, so a second check
        here would ask a question already answered.
        """

        context = max(0, min(context_lines, MAX_CONTEXT_LINES))
        return [
            excerpt
            for boundary in boundaries
            for excerpt in self._for_boundary(boundary, root, "", context)
        ]

    @staticmethod
    def _grown_or_pinned(
        live: BoundaryExcerpt, stored: BoundaryExcerpt | None
    ) -> BoundaryExcerpt:
        """The expanded read when it worked, otherwise the pinned copy, captioned.

        The caption belongs on exactly the substitution: a pinned copy served because the
        live read was refused is code the repository no longer says, and a reader — and
        the stage reading it aloud — must not take it for the code as it is now.
        """

        if live.text or stored is None:
            return live
        if not stored.text:
            return stored
        return stored.model_copy(
            update={
                "provenance": (
                    "The repository has changed since this review ran; this is the "
                    "code as it was when it was reviewed."
                )
            }
        )

    @staticmethod
    def _pinned_for(
        stored: list[BoundaryExcerpt],
        live: list[BoundaryExcerpt],
    ) -> list[BoundaryExcerpt | None]:
        """Line the pinned copies up with a live read, by reference and qualified name.

        Both lists come from the same boundaries in the same order, so this is a lookup
        rather than a match: a participant is identified by which boundary it belongs to and
        what it is called, and neither can change after the review is stored.
        """

        by_participant = {(item.reference, item.qualified_name): item for item in stored}
        return [by_participant.get((item.reference, item.qualified_name)) for item in live]

    def _read_boundaries(
        self,
        review: BoundaryReview,
        boundaries: list[ReviewedBoundary],
        context: int,
    ) -> list[BoundaryExcerpt]:
        root, refusal = self._readable_root(review)
        return [
            excerpt
            for boundary in boundaries
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
        first = max(1, location.start_line - context)
        ceiling = MAX_EXCERPT_LINES + 2 * MAX_CONTEXT_LINES
        try:
            text = self._source_reader.excerpt(
                root=root,
                relative_path=location.path,
                start_line=first,
                end_line=location.end_line + context,
                max_lines=ceiling,
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
        # The ceiling is decided here, so whether it clipped is known here — the reader
        # only ever returns what it was allowed to. Marked on the excerpt rather than left
        # silent: a stage shown half a span with no marker answers from the half it saw as
        # though it were all there is. Hitting the ceiling exactly at end-of-file is
        # indistinguishable from clipping and marks too, which errs on the honest side.
        shown = len(text.splitlines())
        last_shown = first + shown - 1
        clipped = shown == ceiling and last_shown < location.end_line + context
        return BoundaryExcerpt(
            reference=reference,
            qualified_name=participant.qualified_name,
            role=participant.role,
            location=location,
            text=text,
            truncated_after_line=last_shown if clipped else None,
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
