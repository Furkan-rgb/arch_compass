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
from typing import Protocol

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


class JudgementInForce(Protocol):
    """What would judge this review, as the two global causes need to read it.

    Structural, and declared here rather than imported, because `analysis` reaches no
    reasoning adapter: what satisfies it is `SelectedLangChainJudge.in_force`, and pyright
    checks the fit at the one call site in `bootstrap`.

    One record rather than two callables so that the model and the prompt this run is
    compared against are the same reading of the selection. Read separately, `MODEL` is
    decided against one reading and `PROMPT` against another, so a workspace that switched
    model between the two can be told that its prompt moved while its model did not — a pair
    that was no one selection, and `changed=N, causes:['prompt']` against a commit nobody
    touched, which is the measurement this whole line of work started from.

    Both guards are in the test tree rather than here: `test_reasoning_adapters.py` runs this
    calculator against a selection that moves between calls, and
    `test_no_function_reads_the_model_selection_more_than_once` asks it of every function in
    `src/`. The second one is the one that matters, because the lesson of the four previous
    fixes of this defect is that the next reader to arrive is the one nobody writes a
    behavioural test for.
    """

    @property
    def model_identity(self) -> str: ...

    @property
    def prompt_identity(self) -> str: ...


class DeterministicRevisionCalculator:
    def __init__(
        self,
        *,
        corpus_fingerprint: Callable[[RepositoryRef], str] | None = None,
        judgement: Callable[[], JudgementInForce] | None = None,
    ) -> None:
        self._corpus_fingerprint = corpus_fingerprint
        self._judgement = judgement

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
        # Both sides of these two have to be produced by the same decision, and only one side
        # is produced here. `judgement` is `SelectedLangChainJudge.in_force` — the thing that
        # chooses the judge, reporting what that judge stamps — because a value derived
        # separately is a value that can be derived differently: this compared against
        # `judge:v3` while every finding it read was stamped `judge:deep-v2`, so the prompt
        # reported as moved on every candidate of every review, and
        # `ChangedAndNewCandidateSelector` re-judged all of them. Three revisions of one
        # untouched commit, seven candidates each, and not one verdict carried forward.
        #
        # It lasted about a day. The two constants parted on 2026-08-26 and every review the
        # workspace that found it holds was judged in the hours after that. The duration is
        # the point rather than a mitigation: two derivations of one fact do not have to
        # disagree for long to spoil everything recorded while they do, and none of the damage
        # above would have been different had it lasted a year. An earlier version of this
        # comment said "months" — of a repository whose first commit is dated 2026-07-23. A
        # duration is exactly the kind of claim a comment gets to invent, because nothing runs
        # it; prefer a date somebody can check against `git log`.
        in_force = None if self._judgement is None else self._judgement()
        if in_force is not None and previous.model_identity != in_force.model_identity:
            global_causes.append(ChangeCause.MODEL)
        if in_force is not None and previous.prompt_identity != in_force.prompt_identity:
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
