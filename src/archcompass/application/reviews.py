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
from archcompass.domain.errors import AtlasNotFoundError
from archcompass.domain.finding_detectors import detect_finding_candidates
from archcompass.domain.review import (
    BoundaryReview,
    BoundaryReviewReport,
    CandidateVerdict,
    ReviewStatus,
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
        on_detected: Callable[[Sequence[FindingCandidate]], None] | None = None,
        on_verdict: Callable[[JudgedCandidate, int, int], None] | None = None,
    ) -> BoundaryReview:
        """Judge every candidate in the repository against this case.

        `on_detected` is called once, before the first model call, with every candidate the
        sweep found. `on_verdict` is called as each verdict lands, with the position and the
        total. A review is one model call per candidate and takes minutes, so a caller that
        reports nothing until the last one has finished is the difference between a tool
        that looks stuck and one that does not — and detection is where the length of the
        sequence becomes known, which is what makes the wait countable rather than
        unexplained.
        """

        started = monotonic()
        revision = self._cases.get(case_id)
        atlas = self._load_atlas(repository_root)
        self._freshness.ensure_fresh(atlas)
        # Ordered once, here, and passed to every judgement unchanged. The response binds
        # to policies by position, so the order is part of the contract rather than a
        # presentation detail: re-sorting between the request and the result would
        # re-attribute every answer.
        policies = sorted(
            self._policies.catalog(repository_root=repository_root),
            key=lambda policy: policy.id,
        )
        candidates = detect_finding_candidates(atlas)
        if on_detected is not None:
            on_detected(candidates)
        judged: list[JudgedCandidate] = []
        for position, candidate in enumerate(candidates, start=1):
            item = JudgedCandidate(
                candidate=candidate,
                verdict=self._reasoner.judge_finding_candidate(
                    revision.snapshot,
                    candidate,
                    policies,
                ),
            )
            judged.append(item)
            if on_verdict is not None:
                on_verdict(item, position, len(candidates))
        report = BoundaryReviewReport(
            case_title=revision.snapshot.title,
            problem_and_desired_outcome=(
                f"{revision.snapshot.problem_statement}\n\n{revision.snapshot.desired_outcome}"
            ),
            reviewed=reviewed_boundaries([(item.candidate, item.verdict) for item in judged]),
            policies_presented=[policy.id for policy in policies],
        )
        review = BoundaryReview(
            status=ReviewStatus.SUCCEEDED,
            case_id=revision.case_id,
            case_revision=revision.revision,
            atlas_version_id=atlas.version.version_id,
            reasoning_model=self._reasoner.model_identity,
            prompt_identity=self._reasoner.prompt_identity(
                ReasoningTask.JUDGE_FINDING_CANDIDATE
            ),
            report=report,
            markdown_report=render_report(report),
            duration_seconds=round(monotonic() - started, 3),
        )
        self._reviews.save(review)
        return review

    def _load_atlas(self, repository_root: Path) -> Atlas:
        atlas = self._atlases.latest_for_path(repository_root.expanduser().resolve())
        if atlas is None:
            raise AtlasNotFoundError(
                f"No indexed atlas for {repository_root}; "
                f"run `archcompass repo index {repository_root}` first."
            )
        return atlas
