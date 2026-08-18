"""Creation and revision of clean-break ArchitectureCase snapshots."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from archcompass.domain import (
    ArchitectureCase,
    CaseConstraint,
    CaseDecision,
    PolicyContext,
    Review,
)
from archcompass.domain.errors import CaseNotFoundError
from archcompass.ports.repositories import LineageRepository

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


class CaseSnapshots(Protocol):
    def record(self, case: ArchitectureCase) -> ArchitectureCase: ...

    def get(self, case_id: str, revision: int | None = None) -> ArchitectureCase: ...

    def history(self, case_id: str) -> tuple[ArchitectureCase, ...]: ...

    def list(self, *, limit: int = 100) -> tuple[ArchitectureCase, ...]: ...


class ReviewHistory(Protocol):
    def latest_for_branch(self, branch_id: str) -> Review | None: ...


class ArchitectureCaseService:
    def __init__(
        self,
        cases: CaseSnapshots,
        reviews: ReviewHistory,
        lineages: LineageRepository,
    ) -> None:
        self._cases = cases
        self._reviews = reviews
        self._lineages = lineages

    def create(
        self,
        *,
        goal: str = "",
        constraints: tuple[CaseConstraint, ...] = (),
        decisions: tuple[CaseDecision, ...] = (),
        policy_context: PolicyContext | None = None,
    ) -> ArchitectureCase:
        context = PolicyContext() if policy_context is None else policy_context
        case = ArchitectureCase.create(goal)
        if constraints or decisions or context != PolicyContext():
            case = ArchitectureCase(
                case.id,
                case.revision,
                case.goal,
                constraints,
                decisions,
                policy_context=context,
                created_at=case.created_at,
                updated_at=case.updated_at,
            )
        return self._cases.record(case)

    def start_from_repository(self, root: Path) -> ArchitectureCase:
        # Repository identity is already carried separately. Leaving intent blank is
        # deliberate: the first review should ask for context rather than invent it from a
        # directory name and then treat that prose as user-authored architecture intent.
        return self.create()

    def continue_from_repository(
        self, root: Path, *, branch_id: str | None
    ) -> ArchitectureCase:
        for candidate_branch in _branch_chain(self._lineages, branch_id):
            review = self._reviews.latest_for_branch(candidate_branch)
            if review is None:
                continue
            try:
                return self._cases.get(review.case.id)
            except CaseNotFoundError:
                continue
        return self.start_from_repository(root)

    def show(self, case_id: str, revision: int | None = None) -> ArchitectureCase:
        return self._cases.get(case_id, revision)

    def revise(
        self,
        case_id: str,
        *,
        goal: str | None = None,
        constraints: tuple[CaseConstraint, ...] | None = None,
        decisions: tuple[CaseDecision, ...] | None = None,
        policy_context: PolicyContext | None = None,
    ) -> ArchitectureCase:
        return self._cases.record(
            self._cases.get(case_id).revise(
                goal=goal,
                constraints=constraints,
                decisions=decisions,
                policy_context=policy_context,
            )
        )

    def history(self, case_id: str) -> tuple[ArchitectureCase, ...]:
        return self._cases.history(case_id)

    def list(self, *, limit: int = 100) -> tuple[ArchitectureCase, ...]:
        return self._cases.list(limit=limit)
