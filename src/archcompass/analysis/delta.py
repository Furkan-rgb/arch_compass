"""What changed since the branch's previous review, decided without a model.

A candidate is unchanged, changed, new, or addressed, and which one it is follows from
comparing this run's detected candidates against the previous review's findings — never
from anything a model wrote. The causes that are not about the candidate itself are
folded in here too, because each of them invalidates a verdict that was correct when it
was recorded: the case moved, or the model or the prompt moved, which are facts about a
whole review; or the corpus moved, which is a fact about one verdict, because the
manifest records which corpus each candidate was retrieved against.
"""

from __future__ import annotations

from collections.abc import Callable

from archcompass.domain import (
    AddressedCandidate,
    ArchitectureCase,
    Candidate,
    CandidateChange,
    ChangeCause,
    RepositoryRef,
    Review,
    ReviewDelta,
)


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
        # Which corpus a verdict was retrieved against is a fact about that verdict rather
        # than about the review holding it, and the manifest records it per candidate. Read
        # as a set — did every fingerprint this review recorded equal the current one — one
        # entry left behind by a corpus that has since moved reported that the corpus had
        # moved on every run after it, forever, against a repository nobody had touched. A
        # candidate the manifest says nothing about is left alone: there is no record to
        # decide from, and this calculator states what the records establish.
        current_corpus = (
            None
            if self._corpus_fingerprint is None
            else self._corpus_fingerprint(repository)
        )
        retrieved_against = {
            str(item.candidate_id): item.corpus_fingerprint
            for item in previous.retrieval_manifest
        }

        def corpus_moved(candidate_id: str) -> bool:
            recorded = retrieved_against.get(candidate_id)
            return (
                current_corpus is not None
                and recorded is not None
                and recorded != current_corpus
            )

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
            elif (
                finding.candidate == candidate
                and not global_causes
                and not corpus_moved(str(candidate.id))
            ):
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
                corpus_causes = (
                    (ChangeCause.POLICIES,) if corpus_moved(str(candidate.id)) else ()
                )
                causes = tuple(
                    dict.fromkeys(
                        (
                            *candidate_causes,
                            *corpus_causes,
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
