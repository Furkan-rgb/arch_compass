"""What changed since the branch's previous review, decided without a model.

A candidate is unchanged, changed, new, or addressed, and which one it is follows from
comparing this run's detected candidates against the previous review's findings — never
from anything a model wrote. The causes that are not about the candidate itself are
folded in here too, because each of them invalidates a verdict that was correct when it
was recorded. Exactly one of them is a fact about a whole review: the case moved, and a
review holds one case. The other three are facts about one verdict and are read off the
record that verdict left — which model judged it, which prompt asked it, which corpus it
was retrieved against.
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
    Finding,
    RepositoryRef,
    Review,
    ReviewDelta,
)


class JudgeSelection(Protocol):
    """What would judge this review, as the model and prompt causes need to read it.

    Structural, and declared here rather than imported, because `analysis` reaches no
    reasoning adapter: what satisfies it is `SelectedLangChainJudge.selection`, and pyright
    checks the fit at the one call site in `bootstrap`.

    One record rather than two callables so that the model and the prompt this run is
    compared against are the same reading of the selection. Read separately, `MODEL` is
    decided against one reading and `PROMPT` against another, so a workspace that switched
    model between the two can be told that its prompt moved while its model did not — a pair
    that was no one selection, and `changed=N, causes:['prompt']` against a commit nobody
    touched, which is the measurement this whole line of work started from.

    The word is reused, and that was weighed rather than missed. `selection` already meant a
    stored record here: `ReasoningModelStatus.selection` and `EmbeddingModelStatus.selection`
    hold a `ReasoningModelSelection` / `EmbeddingModelSelection`, and
    `ReasoningModelSelectionRepository.set` takes one under that name. Those describe what
    somebody chose and when. The parameter below is a callable returning one of *this*
    protocol's records, asked afresh on every call, and mistaking one for the other is a
    mistake about when the value is decided — which is the axis this whole record exists on.

    It keeps the name anyway, because what a rename would buy is bought already. The
    annotation tells them apart at every declaration and pyright checks
    it — `Callable[[], JudgeSelection]` against `ReasoningModelSelection`, never the bare word
    — and the composition root separates them by number as well: `bootstrap` passes the stored
    side as `selections=` to `ModelCatalogService` and `EmbeddingModelService`, and this side
    as `selection=selected_judge.selection`, where the keyword matching the method it binds is
    what makes that line say where the value comes from. A rename would trade a collision the
    type system resolves for a name that no longer does.

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
        selection: Callable[[], JudgeSelection] | None = None,
    ) -> None:
        self._corpus_fingerprint = corpus_fingerprint
        self._selection = selection

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
        # is produced here. `selection` is `SelectedLangChainJudge.selection` — the thing that
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
        #
        # The other side is read off the finding, and that is the second half of the same
        # lesson. It used to be `previous.model_identity`, which `report.py` composed as
        # `",".join(sorted({every stamp the review's findings carry}))` — a joined set on one
        # side of a comparison whose other side is a single identity. Those two are not the
        # same kind of value. They were equal only because every review this workspace holds
        # was judged under exactly one: measured read-only over
        # `.archcompass/workspace.sqlite3`, 7 reviews and 148 findings carry the single pair
        # `openrouter:google/gemini-3.5-flash-lite:thinking=medium` / `judge:deep-v2`, and
        # none of the 148 is unstamped. The first review whose findings genuinely mixed two
        # would have made the joined string unequal to any single identity — for that
        # revision, and not for ever. Re-measured against this commit's parent wiring, over
        # that 7-finding review with three of its seven findings restamped to a second prompt
        # identity: revision N reads `unchanged=0 changed=7 causes=['prompt']`, so
        # `ChangedAndNewCandidateSelector` re-judges all seven with no cap; every stamp it
        # writes is the single identity in force, so against an otherwise untouched commit
        # revision N+1 reads `unchanged=7 changed=0` and the selector raises
        # `NothingToReviewError`. The defect was one whole re-judgement of the review, and
        # then it healed itself.
        #
        # Healing is what it costs, not a reason it was tolerable. Four of those seven had
        # genuinely changed judge and any correct delta re-judges them; the other three were
        # answers the judge in force had already given. A repeat is served from the cache only
        # where the judgement looked at nothing — `reasoning/cache.py` stores no other kind and
        # records that as about a fifth of judgements — so those three mostly go back to the
        # model, and a judge that does not reproduce itself answers them afresh. That is the
        # oscillation this branch exists to kill, bought for nothing. The window is also not a
        # single event: it opens every time a reviewer switches model mid-run, so the price is
        # per straddle rather than once. Latent rather than fixed, and expensive when it fired.
        #
        # It is reachable. Judgement fans out per candidate through `Send` and `selection()` is
        # asked per call — deliberately, so that `PUT /api/models/selection` takes effect —
        # so a reviewer switching model while a review runs straddles the fan-out and the
        # review that comes out of it holds two stamps.
        #
        # Per candidate that window costs only what it should: only the candidates the moved
        # model judged report `MODEL`, and the rest carry their verdicts forward. The
        # shape is the corpus fingerprint's, immediately below, which was burned this same way
        # — it too compared a review-wide reduction — and stopped for the same reason.
        selection = None if self._selection is None else self._selection()

        def judgement_moved(finding: Finding) -> tuple[ChangeCause, ...]:
            if selection is None:
                return ()
            # An unstamped finding is left alone, exactly as a candidate the retrieval
            # manifest says nothing about is: there is no record to decide from, and this
            # calculator states what the records establish. Raising the cause instead would
            # re-judge a candidate on the strength of a record that says nothing. Whether that
            # ever settles is not this calculator's to promise: a fresh judgement stamps the
            # finding that replaces it, but `CachingArchitectureJudge` keys on the selection
            # rather than on the stored stamps, so a row written under the selection in force
            # hands the same unstamped verdict back every time it is asked. Either way the
            # cost is paid for a cause no record supports. No stored finding takes this branch
            # today (148 of 148 carry both stamps, measured above); it is here because a
            # judgement the delta cannot attribute must not be re-judged on a guess.
            moved = (
                (ChangeCause.MODEL,)
                if finding.model_identity
                and finding.model_identity != selection.model_identity
                else ()
            )
            if finding.prompt_identity and finding.prompt_identity != selection.prompt_identity:
                return (*moved, ChangeCause.PROMPT)
            return moved

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
                and not judgement_moved(finding)
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
                            *judgement_moved(finding),
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
