from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from archcompass.analysis.delta import DeterministicRevisionCalculator
from archcompass.domain import (
    Answer,
    AnswerStatus,
    ArchitectureCase,
    Candidate,
    CandidateChange,
    CandidateId,
    CaseFacet,
    ChangeCause,
    DecisionDisposition,
    Finding,
    Participant,
    Question,
    RepositoryAtlas,
    RepositoryRef,
    RetrievalProvenance,
    Review,
    ReviewDelta,
    ReviewStatus,
    StandingDecision,
    Verdict,
)
from archcompass.domain._support import utc_now


@dataclass(frozen=True)
class _Judging:
    """What `SelectedLangChainJudge.selection` reports, with only the two stamps in it.

    The calculator reads a record rather than two callables so that the model it compares
    against and the prompt it compares against are one reading of the selection.
    """

    model_identity: str
    prompt_identity: str


def test_case_revision_is_immutable_and_records_an_answer() -> None:
    original = ArchitectureCase.create()
    question = Question.create(
        text="Is another provider planned?",
        facet=CaseFacet.EXPECTED_CHANGE,
        candidate_ids=("candidate_b", "candidate_a"),
        round=1,
    )
    answer = Answer(question, AnswerStatus.ANSWERED, "No", "reader", utc_now())

    revised = original.open_revision().with_answer(answer)

    assert original.answers == ()
    assert revised.revision == original.revision + 1
    # Recorded as given, and stamped with the revision it was recorded on. The caller cannot
    # supply that number — `_resume_command` builds an answer from a question and a
    # submission, and neither knows which revision is open — so the case stamps it, and this
    # is the assertion that says the stamp is the case's and not the caller's.
    assert revised.answers == (replace(answer, case_revision=revised.revision),)
    assert revised.answers[0].case_revision == 2
    assert answer.case_revision == 0
    assert question.candidate_ids == ("candidate_a", "candidate_b")


def test_answering_twice_stays_on_the_revision_the_review_opened() -> None:
    original = ArchitectureCase.create()
    opened = original.open_revision()
    first = Question.create(
        text="Who owns the boundary?",
        facet=CaseFacet.DECISION,
        candidate_ids=("candidate-1",),
        round=1,
    )
    second = Question.create(
        text="Is latency constrained?",
        facet=CaseFacet.CONSTRAINT,
        candidate_ids=("candidate-2",),
        round=2,
    )

    after_first = opened.with_answer(
        Answer(first, AnswerStatus.ANSWERED, "Platform", "user", utc_now())
    )
    after_second = after_first.with_answer(
        Answer(second, AnswerStatus.ANSWERED, "No", "user", utc_now())
    )

    assert after_first.revision == opened.revision
    assert after_second.revision == opened.revision
    assert len(after_second.answers) == 2


def test_a_revision_cannot_be_opened_backwards() -> None:
    case = ArchitectureCase.create().open_revision(7)

    assert case.revision == 7
    with pytest.raises(ValueError, match="later than the one it opens from"):
        case.open_revision(7)


def test_one_clarification_submission_records_every_answer() -> None:
    original = ArchitectureCase.create()
    first = Question.create(
        text="Who owns the boundary?",
        facet=CaseFacet.DECISION,
        candidate_ids=("candidate-1",),
        round=1,
    )
    second = Question.create(
        text="Is latency constrained?",
        facet=CaseFacet.CONSTRAINT,
        candidate_ids=("candidate-2",),
        round=1,
    )

    revised = original.with_answers(
        (
            Answer(first, AnswerStatus.ANSWERED, "Platform", "user", utc_now()),
            Answer(second, AnswerStatus.SKIPPED, None, "user", utc_now()),
        )
    )

    assert revised.revision == original.revision
    assert len(revised.answers) == 2


def test_skipped_answer_carries_no_invented_value() -> None:
    question = Question.create(
        text="Who owns this?",
        facet=CaseFacet.DECISION,
        candidate_ids=("candidate_a",),
        round=1,
    )
    skipped = Answer(question, AnswerStatus.SKIPPED, None, "reader", utc_now())
    assert skipped.value is None
    with pytest.raises(ValueError, match="cannot have a value"):
        Answer(question, AnswerStatus.SKIPPED, "unknown", "reader", utc_now())


def test_finding_with_hinge_cannot_recommend_a_response() -> None:
    candidate = Candidate.identified(
        pattern="dependency_direction",
        summary="Ownership is unclear",
        participants=(Participant("domain.order", "source"),),
    )

    with pytest.raises(ValueError, match="uncertainty hinge"):
        Finding(
            candidate,
            Verdict.MATERIAL,
            "The answer could change the verdict.",
            (),
            (),
            hinge="the owning team",
            recommended_response="Move the module.",
        )


def test_revision_calculator_rejudges_for_policy_model_and_prompt_changes(
    tmp_path: Path,
) -> None:
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = RepositoryAtlas("atlas", repository)
    case = ArchitectureCase.create()
    candidate = Candidate.identified(
        pattern="dependency_direction",
        summary="Domain imports an adapter",
        participants=(Participant("domain.order", "source"),),
    )
    # The stamps are on the finding, which is the only place they are. A review holds no
    # model or prompt identity of its own: it held the comma-joined set of its findings'
    # stamps, and the calculator compared that set against a single identity.
    finding = Finding(
        candidate,
        Verdict.CLEARED,
        "No conflict was found.",
        (),
        (),
        model_identity="old-model",
        prompt_identity="old-prompt",
    )
    now = utc_now()
    previous = Review(
        "review-1",
        1,
        repository,
        atlas,
        case,
        (finding,),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(candidate,)),
        now,
        now,
        retrieval_manifest=(
            RetrievalProvenance(
                candidate.id,
                "any-strategy",
                "1",
                "old-corpus",
                ("policy-a",),
            ),
        ),
    )
    calculator = DeterministicRevisionCalculator(
        corpus_fingerprint=lambda _: "new-corpus",
        selection=lambda: _Judging("new-model", "new-prompt"),
    )

    delta = calculator.calculate((candidate,), case, previous, repository)

    assert delta.changed[0].causes == (
        ChangeCause.POLICIES,
        ChangeCause.MODEL,
        ChangeCause.PROMPT,
    )


def test_a_review_that_mixed_two_models_re_judges_only_what_the_moved_model_judged(
    tmp_path: Path,
) -> None:
    """The fan-out window, and the reason the comparison had to become per candidate.

    Judgement fans out per candidate through `Send`, and `SelectedLangChainJudge.selection()`
    is read per call so that `PUT /api/models/selection` takes effect while a review runs.
    A reviewer who switches model mid-review therefore straddles the fan-out, and the review
    that comes out of it holds two model stamps and two prompt stamps.

    Against the review-level fields this cost a whole review rather than a candidate.
    `report.py` stored `",".join(sorted({every stamp}))` — `"model-a,model-b"` for the review
    below — and the calculator compared that joined string against a single identity. No
    single identity equals a joined pair, so `MODEL` and `PROMPT` were reported for every
    candidate and `ChangedAndNewCandidateSelector` re-judged every one of them.

    It did not last for ever, and the reason it did not is the reason it was expensive: the
    re-judgement stamped every finding with the identity in force, leaving a review that holds
    one stamp again, so the revision after it matched. Re-measured against the wiring that
    carried the fields, over the stored 7-finding review with three findings restamped:
    revision N reads `unchanged=0 changed=7 causes=['prompt']`, revision N+1 reads
    `unchanged=7 changed=0` and the selector then refuses the run as `NothingToReviewError`.
    One review re-judged for nothing, every time somebody straddles the fan-out. That is the
    original defect: a fact computed in two places that cannot agree.

    Per candidate the window costs only what it should. Only the candidate the departed model
    judged is re-judged; the one the selected model judged carries its verdict forward.
    """

    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = RepositoryAtlas("atlas", repository)
    case = ArchitectureCase.create()
    before = Candidate.identified(
        pattern="dependency_direction",
        summary="Domain imports an adapter",
        participants=(Participant("domain.order", "source"),),
    )
    after = Candidate.identified(
        pattern="duplicated_knowledge",
        summary="A retry limit is stated twice",
        participants=(Participant("app.limits.RETRY", "copy"),),
    )
    judged_before = Finding(
        before,
        Verdict.CLEARED,
        "No conflict was found.",
        (),
        (),
        model_identity="model-a",
        prompt_identity="judge:a",
    )
    judged_after = Finding(
        after,
        Verdict.CLEARED,
        "No conflict was found.",
        (),
        (),
        model_identity="model-b",
        prompt_identity="judge:b",
    )
    now = utc_now()
    previous = Review(
        "review-1",
        1,
        repository,
        atlas,
        case,
        (judged_before, judged_after),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(before, after)),
        now,
        now,
    )
    calculator = DeterministicRevisionCalculator(
        selection=lambda: _Judging("model-b", "judge:b")
    )

    delta = calculator.calculate((before, after), case, previous, repository)

    assert delta.unchanged == (after,)
    assert [
        (change.candidate.id, change.causes) for change in delta.changed
    ] == [(before.id, (ChangeCause.MODEL, ChangeCause.PROMPT))]


def test_an_unstamped_finding_is_not_re_judged_for_a_model_it_never_named(
    tmp_path: Path,
) -> None:
    """No record to decide from, so nothing is decided — the manifest's rule, for the stamps.

    A cause raised here is permanent: nothing ever writes a stamp onto a finding that was
    stored without one, so "changed" would be the answer on every run for ever. That is the
    shape of every returning form of this defect, and it is why a candidate the retrieval
    manifest says nothing about is left alone too.

    Unreachable from anything this build writes — every judge stamps both — and measured as
    unreachable in what is stored: 148 of 148 findings in `.archcompass/workspace.sqlite3`
    carry both stamps. It is guarded because the delta must state what the records establish,
    and an absent record establishes nothing.
    """

    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = RepositoryAtlas("atlas", repository)
    case = ArchitectureCase.create()
    candidate = Candidate.identified(
        pattern="dependency_direction",
        summary="Domain imports an adapter",
        participants=(Participant("domain.order", "source"),),
    )
    unstamped = Finding(candidate, Verdict.CLEARED, "No conflict was found.", (), ())
    now = utc_now()
    previous = Review(
        "review-1",
        1,
        repository,
        atlas,
        case,
        (unstamped,),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(candidate,)),
        now,
        now,
    )
    calculator = DeterministicRevisionCalculator(
        selection=lambda: _Judging("model-b", "judge:b")
    )

    delta = calculator.calculate((candidate,), case, previous, repository)

    assert delta.unchanged == (candidate,)
    assert delta.changed == ()


def test_a_stale_manifest_entry_does_not_move_the_corpus_for_everything_else(
    tmp_path: Path,
) -> None:
    """The corpus is read per candidate, so a leftover entry cannot speak for the rest.

    A boundary that was addressed leaves its provenance behind in the manifest, recorded
    against whatever corpus it was retrieved from. Comparing the manifest as a set made
    that one entry say the corpus had moved, on every later run, for a repository and a
    corpus nobody had touched.
    """

    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = RepositoryAtlas("atlas", repository)
    case = ArchitectureCase.create()
    surviving = Candidate.identified(
        pattern="sole_implementation",
        summary="One adapter behind a port",
        participants=(Participant("app.Port", "abstraction"),),
    )
    gone = Candidate.identified(
        pattern="duplicated_knowledge",
        summary="A constant stated twice",
        participants=(Participant("app.limits.RETRY", "copy"),),
    )
    now = utc_now()
    previous = Review(
        "review-1",
        1,
        repository,
        atlas,
        case,
        (Finding(surviving, Verdict.CLEARED, "No conflict was found.", (), ()),),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(unchanged=(surviving,)),
        now,
        now,
        retrieval_manifest=(
            RetrievalProvenance(
                gone.id, "any-strategy", "1", "old-corpus", ("policy-a",)
            ),
            RetrievalProvenance(
                surviving.id, "any-strategy", "1", "current-corpus", ("policy-a",)
            ),
        ),
    )
    calculator = DeterministicRevisionCalculator(
        corpus_fingerprint=lambda _: "current-corpus"
    )

    delta = calculator.calculate((surviving,), case, previous, repository)

    assert delta.unchanged == (surviving,)
    assert delta.changed == ()


def test_revision_calculator_records_succession_and_resurfacing(tmp_path: Path) -> None:
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = RepositoryAtlas("atlas", repository)
    case = ArchitectureCase.create()
    predecessor = Candidate.identified(
        pattern="dependency_direction",
        summary="Old boundary",
        participants=(Participant("old.Port", "source"),),
    )
    successor = Candidate.identified(
        pattern="dependency_direction",
        summary="Renamed boundary",
        participants=(Participant("new.Port", "source"),),
    )
    resurfaced = Candidate.identified(
        pattern="sole_implementation",
        summary="Port returned",
        participants=(Participant("Port", "interface"),),
    )
    now = utc_now()

    def review(review_id: str, sequence: int, candidate: Candidate) -> Review:
        return Review(
            review_id,
            sequence,
            repository,
            atlas,
            case,
            (Finding(candidate, Verdict.CLEARED, "Cleared.", (), ()),),
            (),
            ReviewStatus.COMPLETED,
            ReviewDelta(new=(candidate,)),
            now,
            now,
        )

    older = review("older", 1, resurfaced)
    previous = review("previous", 2, predecessor)

    delta = DeterministicRevisionCalculator().calculate(
        (successor, resurfaced), case, previous, repository, (previous, older)
    )

    changes = {str(item.candidate.id): item for item in delta.changed}
    assert changes[str(successor.id)].predecessor_id == predecessor.id
    assert changes[str(successor.id)].causes == (ChangeCause.SHAPE,)
    assert changes[str(resurfaced.id)].causes == (ChangeCause.RESURFACED,)
    assert delta.addressed == ()


def test_candidate_change_freezes_causes_sequence() -> None:
    candidate = Candidate.identified(
        pattern="dependency_direction",
        summary="Domain imports an adapter",
        participants=(Participant("domain.order", "source"),),
    )
    change = CandidateChange(candidate, [ChangeCause.MODEL, ChangeCause.PROMPT])  # type: ignore[arg-type]
    assert isinstance(change.causes, tuple)
    assert change.causes == (ChangeCause.MODEL, ChangeCause.PROMPT)


def test_offered_answers_keep_the_model_s_order_and_drop_repeats() -> None:
    """The model puts the likeliest answer first, so the offer is not sorted into another
    shape. A repeat in a different case is the same answer twice, which is one choice.
    """

    question = Question.create(
        text="Who owns persistence?",
        facet=CaseFacet.DECISION,
        candidate_ids=("candidate-1",),
        round=1,
        options=[
            "  The domain owns it  ",
            "The platform team owns it",
            "the domain owns it",
        ],
    )

    assert question.options == ("The domain owns it", "The platform team owns it")


def test_a_question_without_proposed_answers_is_still_a_question() -> None:
    question = Question.create(
        text="What changes next?",
        facet=CaseFacet.EXPECTED_CHANGE,
        candidate_ids=("candidate-1",),
        round=1,
    )

    assert question.options == ()


def test_proposed_answers_do_not_change_what_counts_as_the_same_question() -> None:
    """Equivalence stops the same question being asked twice. Two rounds proposing
    different answers to the same question of the same candidates are still one question.
    """

    first = Question.create(
        text="Who owns persistence?",
        facet=CaseFacet.DECISION,
        candidate_ids=("candidate-1",),
        round=1,
        options=("The domain owns it", "The platform team owns it"),
    )
    second = Question.create(
        text="Who owns persistence, exactly?",
        facet=CaseFacet.DECISION,
        candidate_ids=("candidate-1",),
        round=2,
    )

    assert first.equivalence_key == second.equivalence_key


def _decision(
    *,
    disposition: DecisionDisposition = DecisionDisposition.ACCEPT,
    author: str = "architect",
    reasoning: str | None = None,
) -> StandingDecision:
    return StandingDecision(
        id="decision-1",
        branch_id="branch-1",
        candidate_id=CandidateId("candidate-1"),
        disposition=disposition,
        author=author,
        reasoning=reasoning,
        decided_at=utc_now(),
        review_id="review-1",
        finding_verdict=Verdict.MATERIAL,
    )

def test_a_standing_decision_names_who_made_it() -> None:
    """A decision is a person's, and an unattributed one is not a decision.

    `StandingDecision` had no test at all — nor did `DecisionDisposition` — despite carrying
    two invariants that exist to keep the record answerable months later.
    """

    with pytest.raises(ValueError, match="decision author"):
        _decision(author="   ")


def test_a_waiver_says_why_and_the_other_dispositions_need_not() -> None:
    """The asymmetry is the point.

    Accepting or parking a finding is a judgement the verdict beside it already explains.
    Waiving one is a claim that a policy does not apply here, and the reason is the whole of
    what a later reader — or a later review carrying the decision through succession — has
    to go on.
    """

    with pytest.raises(ValueError, match="waiver must include reasoning"):
        _decision(disposition=DecisionDisposition.WAIVE, reasoning=None)
    with pytest.raises(ValueError, match="waiver must include reasoning"):
        _decision(disposition=DecisionDisposition.WAIVE, reasoning="  \n ")

    waived = _decision(
        disposition=DecisionDisposition.WAIVE, reasoning="This boundary is contractual."
    )
    assert waived.reasoning == "This boundary is contractual."
    # The other two are complete without one.
    assert _decision(disposition=DecisionDisposition.ACCEPT, reasoning=None).reasoning is None
    assert _decision(disposition=DecisionDisposition.PARK, reasoning=None).reasoning is None


def test_a_decision_keys_off_the_candidate_and_not_off_a_finding() -> None:
    """What keeps `Finding` and `StandingDecision` separable.

    A decision is about a shape in the repository, on a branch — not about one review's
    verdict on it. That is why it carries `branch_id` and `candidate_id` as its subject and
    the finding's identities only as provenance, and why a review has no decisions field.
    """

    decision = _decision()

    assert decision.branch_id and decision.candidate_id
    assert not hasattr(Review, "decisions")
    # The verdict it was made against is kept, so a later reader can see what the person was
    # looking at — but it is not what the decision is filed under.
    assert decision.finding_verdict is Verdict.MATERIAL
