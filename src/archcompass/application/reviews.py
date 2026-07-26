"""Detect boundaries in a repository and judge each against one case.

The MVP advisory path, end to end and deliberately short: the application decides what to
look at, the model decides what it means, and nothing the model writes is used as a key
(master plan 12.0).

Detection is deterministic and complete over the atlas, so what reaches the model is not a
sample or a ranking. Judgement runs once per candidate against the whole policy corpus,
which fits comfortably in one request, so there is no retrieval step to get wrong and no
threshold quietly deciding which policy the advisor was allowed to consider.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from archcompass.application.policies import PolicyService
from archcompass.application.review_rendering import render_report
from archcompass.domain.atlas import Atlas, FindingCandidate
from archcompass.domain.case import CaseRevision
from archcompass.domain.errors import (
    ArchCompassError,
    AtlasNotFoundError,
    ReviewCancelledError,
)
from archcompass.domain.finding_detectors import detect_finding_candidates
from archcompass.domain.review import (
    BoundaryReview,
    BoundaryReviewReport,
    CandidateVerdict,
    ReviewStatus,
    empty_review_overview,
    reviewed_boundaries,
)
from archcompass.ports.atlas import AtlasFreshnessChecker
from archcompass.ports.reasoning import FocusedReasoningProvider, ReasoningTask
from archcompass.ports.repositories import (
    AtlasRepository,
    BoundaryReviewRepository,
    CaseRepository,
)


@dataclass(frozen=True)
class JudgedCandidate:
    """One detected pattern and what the model made of it."""

    candidate: FindingCandidate
    verdict: CandidateVerdict


class ReviewService:
    def __init__(
        self,
        *,
        cases: CaseRepository,
        atlases: AtlasRepository,
        reviews: BoundaryReviewRepository,
        freshness: AtlasFreshnessChecker,
        policies: PolicyService,
        reasoner: FocusedReasoningProvider,
    ) -> None:
        self._cases = cases
        self._atlases = atlases
        self._reviews = reviews
        self._freshness = freshness
        self._policies = policies
        self._reasoner = reasoner

    def review(
        self,
        case_id: str,
        *,
        repository_root: Path,
        on_started: Callable[[BoundaryReview], None] | None = None,
        on_detected: Callable[[Sequence[FindingCandidate]], None] | None = None,
        on_verdict: Callable[[JudgedCandidate, int, int], None] | None = None,
        on_summarising: Callable[[], None] | None = None,
    ) -> BoundaryReview:
        """Judge every candidate in the repository against this case.

        `on_started` is called once the run has a record, which is the first moment it has
        an identity: everything that could refuse the run has passed, and the review can be
        opened and watched from anywhere from here on. `on_detected` is called once, before
        the first model call, with every candidate the sweep found. `on_verdict` is called
        as each verdict lands, with the position and the total.

        A review is one model call per candidate and takes minutes, so a caller that reports
        nothing until the last one has finished is the difference between a tool that looks
        stuck and one that does not — and detection is where the length of the sequence
        becomes known, which is what makes the wait countable rather than unexplained.
        """

        started = monotonic()
        revision = self._cases.get(case_id)
        atlas = self._load_atlas(repository_root)
        self._freshness.ensure_fresh(atlas)
        # The run becomes a record here, before the first model call and after everything
        # that could refuse it. Earlier would store runs that never began; later is the
        # minutes-long gap this exists to close — a review nobody can find while it is being
        # produced looks the same as one that was never started.
        running = BoundaryReview(
            status=ReviewStatus.RUNNING,
            case_id=revision.case_id,
            case_revision=revision.revision,
            atlas_version_id=atlas.version.version_id,
            reasoning_model=self._reasoner.model_identity,
            prompt_identity=self._reasoner.prompt_identity(
                ReasoningTask.JUDGE_FINDING_CANDIDATE
            ),
        )
        self._reviews.begin(running)
        if on_started is not None:
            on_started(running)
        try:
            return self._judge(
                running,
                revision=revision,
                atlas=atlas,
                repository_root=repository_root,
                started=started,
                on_detected=on_detected,
                on_verdict=on_verdict,
                on_summarising=on_summarising,
            )
        except ReviewCancelledError:
            # Nothing is written back. The record already says cancelled — that write is
            # what stopped the run — and a failure recorded over it would replace a choice
            # with a breakage. It also leaves the row safe to delete straight away.
            raise
        except ArchCompassError as error:
            # The run's own message: it was raised by ArchCompass and is written for a
            # person to read, which is the same rule the web layer applies before putting
            # one in a response.
            self._fail(running, str(error), started)
            raise
        except Exception:
            # Whatever this was, it is not something to quote back. The row still has to
            # stop saying "running", because a caller that crashed cannot come back to
            # correct it.
            self._fail(running, "The review failed unexpectedly, and nothing was judged.", started)
            raise

    def _judge(
        self,
        running: BoundaryReview,
        *,
        revision: CaseRevision,
        atlas: Atlas,
        repository_root: Path,
        started: float,
        on_detected: Callable[[Sequence[FindingCandidate]], None] | None,
        on_verdict: Callable[[JudgedCandidate, int, int], None] | None,
        on_summarising: Callable[[], None] | None,
    ) -> BoundaryReview:
        # Ordered once, here, and passed to every judgement unchanged. The response binds
        # to policies by position, so the order is part of the contract rather than a
        # presentation detail: re-sorting between the request and the result would
        # re-attribute every answer.
        policies = sorted(
            self._policies.catalog(repository_root=repository_root),
            key=lambda policy: policy.id,
        )
        candidates = detect_finding_candidates(atlas)
        # Now the run has a length, which is the one number a reader watching it needs.
        self._reviews.record_progress(running.review_id, detected=len(candidates))
        if on_detected is not None:
            on_detected(candidates)
        judged: list[JudgedCandidate] = []
        material = 0
        for position, candidate in enumerate(candidates, start=1):
            self._stop_if_cancelled(running.review_id)
            item = JudgedCandidate(
                candidate=candidate,
                verdict=self._reasoner.judge_finding_candidate(
                    revision.snapshot,
                    candidate,
                    policies,
                ),
            )
            judged.append(item)
            material += 1 if item.verdict.material else 0
            self._reviews.record_progress(
                running.review_id,
                reviewed=position,
                material=material,
            )
            if on_verdict is not None:
                on_verdict(item, position, len(candidates))
        boundaries = reviewed_boundaries([(item.candidate, item.verdict) for item in judged])
        # Checked once more before the last call, which is the longest single wait in the
        # run: cancelling just as the verdicts land should not still cost a summarisation.
        self._stop_if_cancelled(running.review_id)
        if on_summarising is not None:
            on_summarising()
        # One call over all the verdicts, and only when there are verdicts. A sweep that
        # found nothing has nothing to synthesise, and asking a model to summarise an empty
        # set would be asking it to invent the content of the answer.
        overview = (
            self._reasoner.summarise_review(revision.snapshot, boundaries)
            if boundaries
            else empty_review_overview()
        )
        report = BoundaryReviewReport(
            case_title=revision.snapshot.title,
            problem_and_desired_outcome=(
                f"{revision.snapshot.problem_statement}\n\n{revision.snapshot.desired_outcome}"
            ),
            reviewed=boundaries,
            overview=overview,
            policies_presented=[policy.id for policy in policies],
        )
        review = running.model_copy(
            update={
                "status": ReviewStatus.SUCCEEDED,
                "report": report,
                "markdown_report": render_report(report),
                "duration_seconds": round(monotonic() - started, 3),
            }
        )
        self._reviews.complete(review)
        return review

    def _stop_if_cancelled(self, review_id: str) -> None:
        """Read the run's own record, between model calls, to see whether to go on.

        The record is the channel. A flag shared with whoever started the run would be
        state living outside the request that owns the work — and the row has to say
        cancelled anyway, for the listing to show it. Cancelling therefore takes effect
        within one model call rather than at once, which is the bound worth stating: on a
        local model that is up to a few minutes.
        """

        if not self._reviews.is_running(review_id):
            raise ReviewCancelledError(f"Boundary review {review_id} was cancelled.")

    def _fail(self, running: BoundaryReview, reason: str, started: float) -> None:
        self._reviews.complete(
            running.model_copy(
                update={
                    "status": ReviewStatus.FAILED,
                    "sanitized_errors": [reason],
                    "duration_seconds": round(monotonic() - started, 3),
                }
            )
        )

    def _load_atlas(self, repository_root: Path) -> Atlas:
        atlas = self._atlases.latest_for_path(repository_root.expanduser().resolve())
        if atlas is None:
            raise AtlasNotFoundError(
                f"No indexed atlas for {repository_root}; "
                f"run `archcompass repo index {repository_root}` first."
            )
        return atlas
