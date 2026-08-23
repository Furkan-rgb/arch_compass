"""Creation and revision of clean-break ArchitectureCase snapshots."""

from __future__ import annotations

from archcompass.domain import (
    ArchitectureCase,
    PolicyContext,
)
from archcompass.domain.errors import CaseNotFoundError
from archcompass.persistence.ports import (
    CaseSnapshots,
    LineageRepository,
    ReviewSnapshots,
)

MAX_BASE_DEPTH = 8


def _branch_chain(lineages: LineageRepository, branch_id: str | None) -> tuple[str, ...]:
    if branch_id is None:
        return ()
    chain = [branch_id]
    seen = {branch_id}
    current = branch_id
    while len(chain) < MAX_BASE_DEPTH:
        lineage = lineages.get_branch(current)
        base = None if lineage is None else lineage.base_branch_id
        if base is None or base in seen:
            break
        chain.append(base)
        seen.add(base)
        current = base
    return tuple(chain)


class ArchitectureCaseService:
    def __init__(
        self,
        cases: CaseSnapshots,
        reviews: ReviewSnapshots,
        lineages: LineageRepository,
    ) -> None:
        self._cases = cases
        self._reviews = reviews
        self._lineages = lineages

    def create(self, *, policy_context: PolicyContext | None = None) -> ArchitectureCase:
        context = PolicyContext() if policy_context is None else policy_context
        case = ArchitectureCase.create()
        if context != PolicyContext():
            case = ArchitectureCase(
                case.id,
                case.revision,
                policy_context=context,
                created_at=case.created_at,
                updated_at=case.updated_at,
            )
        return self._cases.record(case)

    def continue_from_repository(self, *, branch_id: str | None) -> ArchitectureCase:
        """The case this branch continues, or a new empty one where it continues nothing.

        The chain rather than the branch alone: a feature branch inherits the case of the
        branch it came from, so a review of it is judged against what has already been
        answered rather than starting over.

        An empty case is the honest fallback. Repository identity is carried separately, and
        everything a review needs to know about intent is asked for when a judgement turns
        on it rather than demanded up front — which is why this took a repository root for a
        while and never read it.
        """

        for candidate_branch in _branch_chain(self._lineages, branch_id):
            review = self._reviews.latest_for_branch(candidate_branch)
            if review is None:
                continue
            try:
                return self._cases.get(review.case.id)
            except CaseNotFoundError:
                continue
        return self.create()

    def show(self, case_id: str, revision: int | None = None) -> ArchitectureCase:
        return self._cases.get(case_id, revision)

    def rescope(self, case_id: str, *, policy_context: PolicyContext) -> ArchitectureCase:
        """Change which policies this case can retrieve, as a new revision.

        Named for what it does now. It was `revise`, when a person could also write
        constraints and decisions through it; nothing writes those any more, and a method
        called "revise the case" invites putting them back.
        """

        return self._cases.record(
            self._cases.get(case_id).revise(policy_context=policy_context)
        )

    def history(self, case_id: str) -> tuple[ArchitectureCase, ...]:
        return self._cases.history(case_id)

    def list(self, *, limit: int = 100) -> tuple[ArchitectureCase, ...]:
        return self._cases.list(limit=limit)
