"""Human dispositions over findings, kept separate from machine judgement."""

from __future__ import annotations

from typing import Protocol

from archcompass.domain import (
    CandidateId,
    DecisionDisposition,
    Review,
    StandingDecision,
)
from archcompass.domain._support import new_id, utc_now
from archcompass.domain.errors import ReviewNotFoundError
from archcompass.ports.persistence import ReviewSnapshots


class StandingDecisionStore(Protocol):
    def record(self, decision: StandingDecision) -> StandingDecision: ...

    def record_many(
        self, decisions: tuple[StandingDecision, ...]
    ) -> tuple[StandingDecision, ...]: ...

    def latest_for_branch(self, branch_id: str) -> tuple[StandingDecision, ...]: ...

    def history(
        self, branch_id: str, candidate_id: CandidateId
    ) -> tuple[StandingDecision, ...]: ...


class StandingDecisionService:
    def __init__(
        self, *, decisions: StandingDecisionStore, reviews: ReviewSnapshots
    ) -> None:
        self._decisions = decisions
        self._reviews = reviews

    def decide(
        self,
        *,
        review_id: str,
        candidate_id: str,
        disposition: DecisionDisposition,
        author: str,
        reasoning: str | None = None,
    ) -> StandingDecision:
        review = self._reviews.get(review_id)
        decision = self._build(
            review, candidate_id, disposition, author, reasoning
        )
        return self._decisions.record(decision)

    def decide_many(
        self,
        *,
        review_id: str,
        candidate_ids: tuple[str, ...],
        disposition: DecisionDisposition,
        author: str,
        reasoning: str | None = None,
    ) -> tuple[StandingDecision, ...]:
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("bulk decisions cannot repeat a candidate")
        review = self._reviews.get(review_id)
        decisions = tuple(
            self._build(review, candidate_id, disposition, author, reasoning)
            for candidate_id in candidate_ids
        )
        return self._decisions.record_many(decisions)

    @staticmethod
    def _build(
        review: Review,
        candidate_id: str,
        disposition: DecisionDisposition,
        author: str,
        reasoning: str | None,
    ) -> StandingDecision:
        finding = next(
            (
                item
                for item in review.findings
                if str(item.candidate.id) == candidate_id
            ),
            None,
        )
        if finding is None:
            raise ReviewNotFoundError(
                f"Review {review.id} has no candidate {candidate_id}"
            )
        return StandingDecision(
            id=new_id("decision"),
            branch_id=review.repository.branch_id,
            candidate_id=finding.candidate.id,
            disposition=disposition,
            author=author,
            reasoning=reasoning,
            decided_at=utc_now(),
            review_id=review.id,
            finding_verdict=finding.verdict,
            finding_model_identity=finding.model_identity,
            finding_prompt_identity=finding.prompt_identity,
            finding_retrieval_identity=finding.retrieval_identity,
        )

    def current(self, branch_id: str) -> tuple[StandingDecision, ...]:
        return self._decisions.latest_for_branch(branch_id)

    def history(
        self, branch_id: str, candidate_id: str
    ) -> tuple[StandingDecision, ...]:
        return self._decisions.history(branch_id, CandidateId(candidate_id))

    def standings(
        self, *branch_ids: str
    ) -> dict[str, StandingDecision]:
        result: dict[str, StandingDecision] = {}
        for branch_id in branch_ids:
            result.update(
                (str(item.candidate_id), item)
                for item in self._decisions.latest_for_branch(branch_id)
            )
        return result
