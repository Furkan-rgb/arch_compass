"""Deterministic default capabilities for revision, selection, and recording boundaries."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from archcompass.application.capabilities import CandidateSelection, ReviewDraft
from archcompass.application.policy_retrieval import RejudgeAllCandidates
from archcompass.domain import (
    AddressedCandidate,
    Answer,
    ArchitectureCase,
    Candidate,
    CandidateChange,
    ChangeCause,
    RepositoryRef,
    Review,
    ReviewDelta,
    ReviewStatus,
)
from archcompass.domain._support import stable_id, utc_now
from archcompass.domain.errors import NothingToReviewError


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


class DeterministicRevisionCalculator:
    def __init__(
        self,
        *,
        corpus_fingerprint: Callable[[RepositoryRef], str] | None = None,
        model_identity: Callable[[], str] | None = None,
        prompt_identity: Callable[[], str] | None = None,
    ) -> None:
        self._corpus_fingerprint = corpus_fingerprint
        self._model_identity = model_identity
        self._prompt_identity = prompt_identity

    def calculate(
        self,
        candidates: tuple[Candidate, ...],
        case: ArchitectureCase,
        previous: Review | None,
        repository: RepositoryRef,
        history: tuple[Review, ...] = (),
    ) -> ReviewDelta:
        if previous is None:
            return ReviewDelta(new=candidates)
        prior = {str(item.candidate.id): item for item in previous.findings}
        current = {str(item.id): item for item in candidates}
        historical = {
            str(finding.candidate.id): finding
            for review in history
            if review.id != previous.id
            for finding in review.findings
        }
        unchanged: list[Candidate] = []
        changed: list[CandidateChange] = []
        new: list[Candidate] = []
        global_causes: list[ChangeCause] = []
        if previous.case != case:
            global_causes.append(ChangeCause.CASE)
        if self._corpus_fingerprint is not None:
            previous_corpora = {
                item.corpus_fingerprint for item in previous.retrieval_manifest
            }
            current_corpus = self._corpus_fingerprint(repository)
            if previous_corpora and previous_corpora != {current_corpus}:
                global_causes.append(ChangeCause.POLICIES)
        if (
            self._model_identity is not None
            and previous.model_identity != self._model_identity()
        ):
            global_causes.append(ChangeCause.MODEL)
        if (
            self._prompt_identity is not None
            and previous.prompt_identity != self._prompt_identity()
        ):
            global_causes.append(ChangeCause.PROMPT)
        missing_prior = {
            candidate_id: finding
            for candidate_id, finding in prior.items()
            if candidate_id not in current
        }
        succeeded_predecessors: set[str] = set()
        for candidate in candidates:
            finding = prior.get(str(candidate.id))
            if finding is None:
                if str(candidate.id) in historical:
                    changed.append(
                        CandidateChange(candidate, (ChangeCause.RESURFACED,))
                    )
                    continue
                predecessors = [
                    item
                    for item in missing_prior.values()
                    if _succession_signature(item.candidate)
                    == _succession_signature(candidate)
                ]
                if len(predecessors) == 1:
                    predecessor = predecessors[0].candidate
                    succeeded_predecessors.add(str(predecessor.id))
                    changed.append(
                        CandidateChange(
                            candidate,
                            (ChangeCause.SHAPE,),
                            predecessor_id=predecessor.id,
                        )
                    )
                else:
                    new.append(candidate)
            elif finding.candidate == candidate and not global_causes:
                unchanged.append(candidate)
            else:
                candidate_causes: tuple[ChangeCause, ...] = ()
                if finding.candidate != candidate:
                    candidate_causes = (
                        ChangeCause.CONTENT
                        if _without_evidence(finding.candidate)
                        == _without_evidence(candidate)
                        else ChangeCause.SHAPE,
                    )
                causes = tuple(
                    dict.fromkeys(
                        (
                            *candidate_causes,
                            *global_causes,
                        )
                    )
                )
                changed.append(CandidateChange(candidate, causes))
        addressed = tuple(
            AddressedCandidate(
                finding.candidate.id,
                finding.candidate.summary,
                previous.id,
                finding.verdict,
            )
            for candidate_id, finding in prior.items()
            if candidate_id not in current and candidate_id not in succeeded_predecessors
        )
        return ReviewDelta(tuple(unchanged), tuple(changed), tuple(new), addressed)


def _without_evidence(candidate: Candidate) -> tuple[object, ...]:
    return (
        candidate.id,
        candidate.pattern,
        candidate.summary,
        candidate.participants,
        candidate.measurements,
        candidate.detection_rationale,
        candidate.limitations,
    )


def _succession_signature(candidate: Candidate) -> tuple[object, ...]:
    """Conservatively link a renamed/re-keyed instance of the same detector shape."""

    return (
        candidate.pattern,
        tuple(sorted(participant.role for participant in candidate.participants)),
    )


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
        findings = "\n\n".join(
            f"## {finding.candidate.summary}\n\n"
            f"**{finding.verdict.value}** — {finding.reasoning}"
            for finding in draft.findings
        )
        report = (
            f"# Architecture review\n\n{draft.case.goal or 'No goal stated.'}\n\n"
            f"{findings or 'No architectural candidates were found.'}\n"
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
    "DeterministicRevisionCalculator",
    "PersistentCaseReviser",
    "RejudgeAllCandidates",
]
