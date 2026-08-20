"""Deterministic default capabilities for revision, selection, and recording boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from archcompass.domain import (
    Answer,
    ArchitectureCase,
    Candidate,
    Review,
    ReviewDelta,
    ReviewStatus,
)
from archcompass.domain._support import stable_id, utc_now
from archcompass.domain.errors import NothingToReviewError
from archcompass.ports.capabilities import CandidateSelection, ReviewDraft
from archcompass.workflow.report import compose_markdown_report


class AppendAnswersCaseReviser:
    def revise(
        self, case: ArchitectureCase, answers: Sequence[Answer]
    ) -> ArchitectureCase:
        return case.with_answers(tuple(answers))


class CaseSnapshotRecorder(Protocol):
    def record(self, case: ArchitectureCase) -> ArchitectureCase: ...


class PersistentCaseReviser(AppendAnswersCaseReviser):
    def __init__(self, cases: CaseSnapshotRecorder) -> None:
        self._cases = cases

    def revise(
        self, case: ArchitectureCase, answers: Sequence[Answer]
    ) -> ArchitectureCase:
        revised = super().revise(case, answers)
        return self._cases.record(revised)


class ChangedAndNewCandidateSelector:
    def select(
        self,
        candidates: tuple[Candidate, ...],
        delta: ReviewDelta,
        previous: Review | None,
        ci: bool,
    ) -> CandidateSelection:
        if (
            previous is not None
            and not ci
            and not delta.changed
            and not delta.new
            and not delta.addressed
        ):
            raise NothingToReviewError(
                "Nothing has changed since the branch's previous review.",
                current_against=previous.id,
            )
        selected = {str(item.candidate.id) for item in delta.changed} | {
            str(item.id) for item in delta.new
        }
        chosen = tuple(item for item in candidates if str(item.id) in selected)
        unchanged = {str(item.id) for item in delta.unchanged}
        carried = (
            ()
            if previous is None
            else tuple(
                finding
                for finding in previous.findings
                if str(finding.candidate.id) in unchanged
            )
        )
        return CandidateSelection(chosen, carried)


class DeterministicReviewComposer:
    """Compose record identity and provenance; prose generation is a separate capability."""

    def compose(self, draft: ReviewDraft, *, waiting: bool) -> Review:
        status = ReviewStatus.AWAITING_ANSWERS if waiting else ReviewStatus.COMPLETED
        sequence = 1 if draft.previous is None else draft.previous.sequence + 1
        review_id = stable_id(
            "review",
            draft.repository.branch_id,
            draft.atlas.id,
            draft.case.id,
            str(draft.case.revision),
            status.value,
        )
        current_manifest = tuple(item.provenance for item in draft.retrievals)
        current_candidates = {str(item.candidate_id) for item in current_manifest}
        carried_manifest = (
            ()
            if draft.previous is None
            else tuple(
                item
                for item in draft.previous.retrieval_manifest
                if str(item.candidate_id) not in current_candidates
            )
        )
        retrieval_manifest = (*carried_manifest, *current_manifest)
        model_identities = sorted(
            {item.model_identity for item in draft.findings if item.model_identity}
        )
        prompt_identities = sorted(
            {item.prompt_identity for item in draft.findings if item.prompt_identity}
        )
        now = utc_now()
        # The document the review becomes when it leaves the product — attached to a pull
        # request, printed by the CLI, downloaded. `report.py` owns it, because a readable
        # record is a body of formatting decisions and this class composes identity.
        report = compose_markdown_report(
            repository=draft.repository,
            atlas=draft.atlas,
            case=draft.case,
            findings=draft.findings,
            questions=draft.questions,
            delta=draft.delta,
            previous=draft.previous,
            retrievers=sorted(
                {
                    f"{item.retriever}/{item.version}"
                    for item in retrieval_manifest
                    if item.retriever
                }
            ),
            sequence=sequence,
            waiting=waiting,
        )
        return Review(
            id=review_id,
            sequence=sequence,
            repository=draft.repository,
            atlas=draft.atlas,
            case=draft.case,
            findings=draft.findings,
            questions=draft.questions,
            status=status,
            delta=draft.delta,
            started_at=now,
            finished_at=None if waiting else now,
            previous_review_id=None if draft.previous is None else draft.previous.id,
            markdown_report=report,
            retrieval_manifest=retrieval_manifest,
            model_identity=",".join(model_identities),
            prompt_identity=",".join(prompt_identities),
        )


__all__ = [
    "AppendAnswersCaseReviser",
    "ChangedAndNewCandidateSelector",
    "DeterministicReviewComposer",
    "PersistentCaseReviser",
]
