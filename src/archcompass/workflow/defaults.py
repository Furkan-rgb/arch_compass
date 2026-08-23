"""Deterministic default capabilities for revision, selection, and recording boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from archcompass.domain import (
    Answer,
    ArchitectureCase,
    Candidate,
    Finding,
    Question,
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
    ReviewStatus,
)
from archcompass.domain._support import stable_id, utc_now
from archcompass.domain.errors import NothingToReviewError
from archcompass.ports.capabilities import (
    CandidateSelection,
    InvestigatedFinding,
    ReviewDraft,
    ReviewSynopsis,
)
from archcompass.workflow.report import compose_markdown_report


class NoReviewSynopsis:
    """The seam filled when nothing is going to write a summary.

    A workspace can compose a review without a reasoning model available — a rerun from the
    CLI against cached findings, a test harness, a deployment that has not selected one — and
    a report that fails to compose because its opening paragraph could not be written would
    be the tail wagging the dog. The report simply opens on its counts, as it did before.
    """

    def write(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        questions: tuple[Question, ...],
        delta: ReviewDelta,
        previous: Review | None,
        waiting: bool,
    ) -> ReviewSynopsis | None:
        return None


class NoHingeInvestigation:
    """The seam filled when nothing is going to look anything up.

    Not every model can call tools and a workspace may have selected one that cannot, so
    the absence answer here is not a failure — it is the finding, unchanged, and a hinge
    that goes to a person the way every hinge did before this existed. `supports_tools`
    answering False is what keeps the node cheap: it returns before it reads a finding.
    """

    def supports_tools(self) -> bool:
        return False

    def investigate(
        self,
        finding: Finding,
        case: ArchitectureCase,
        *,
        repository: RepositoryRef,
        atlas: RepositoryAtlas,
    ) -> InvestigatedFinding:
        del case, repository, atlas
        return InvestigatedFinding(finding)


class CaseSnapshotRecorder(Protocol):
    def record(self, case: ArchitectureCase) -> ArchitectureCase: ...

    def next_revision(self, case_id: str) -> int: ...


class PersistentCaseReviser:
    """The same revision, written once, at the end.

    It used to write on every round, which is what made a review that asked twice leave
    three revisions behind. Now the store is asked for a free number when the revision
    opens — so a review started from an older revision takes the next number rather than
    colliding with one that is already there — and the snapshot is written when the review
    that opened it finishes. A review nobody answered writes nothing.
    """

    def __init__(self, cases: CaseSnapshotRecorder) -> None:
        self._cases = cases

    def open(self, case: ArchitectureCase) -> ArchitectureCase:
        return case.open_revision(self._cases.next_revision(case.id))

    def revise(
        self, case: ArchitectureCase, answers: Sequence[Answer]
    ) -> ArchitectureCase:
        return case.with_answers(tuple(answers))

    def seal(self, case: ArchitectureCase) -> ArchitectureCase:
        return self._cases.record(case)


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
        # The round is part of the identity, and has to be: a review asks under one case
        # revision now and keeps that revision however many rounds it takes, so two waiting
        # snapshots of one review would otherwise be filed under one id and the second
        # would be dropped as a duplicate of the first.
        review_id = stable_id(
            "review",
            draft.repository.branch_id,
            draft.atlas.id,
            draft.case.id,
            str(draft.case.revision),
            str(draft.round),
            status.value,
        )
        current_manifest = tuple(item.provenance for item in draft.retrievals)
        current_candidates = {str(item.candidate_id) for item in current_manifest}
        # The manifest audits *this* review's findings, so it carries provenance only for
        # candidates this review still holds one for. Carrying every entry the previous
        # review had kept the provenance of boundaries that no longer exist — and, because
        # the delta reads the corpus fingerprint out of this manifest, one addressed
        # candidate retrieved under an older corpus made every later review report that the
        # corpus had moved, on a repository nobody had touched, for as long as the branch
        # lived.
        judged_candidates = {str(item.candidate.id) for item in draft.findings}
        carried_manifest = (
            ()
            if draft.previous is None
            else tuple(
                item
                for item in draft.previous.retrieval_manifest
                if str(item.candidate_id) not in current_candidates
                and str(item.candidate_id) in judged_candidates
            )
        )
        retrieval_manifest = (*carried_manifest, *current_manifest)
        # The same rule, for the same reason: an investigation audits a finding this
        # review holds, and one carried from the previous review belongs here only
        # where this review did not check that candidate again.
        investigated_candidates = {str(item.candidate_id) for item in draft.investigations}
        carried_investigations = (
            ()
            if draft.previous is None
            else tuple(
                item
                for item in draft.previous.investigation_manifest
                if str(item.candidate_id) not in investigated_candidates
                and str(item.candidate_id) in judged_candidates
            )
        )
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
            synopsis=draft.synopsis,
            round=draft.round,
        )
        return Review(
            id=review_id,
            sequence=sequence,
            round=draft.round,
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
            synopsis=None if draft.synopsis is None else draft.synopsis.text,
            synopsis_identity="" if draft.synopsis is None else draft.synopsis.model_identity,
            retrieval_manifest=retrieval_manifest,
            investigation_manifest=(*carried_investigations, *draft.investigations),
            model_identity=",".join(model_identities),
            prompt_identity=",".join(prompt_identities),
        )


__all__ = [
    "ChangedAndNewCandidateSelector",
    "DeterministicReviewComposer",
    "NoHingeInvestigation",
    "NoReviewSynopsis",
    "PersistentCaseReviser",
]
