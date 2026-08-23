from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from archcompass.configuration import ReasoningModelConfig
from archcompass.domain import (
    Answer,
    AnswerStatus,
    ArchitectureCase,
    Candidate,
    CaseFacet,
    Evidence,
    Finding,
    Participant,
    Policy,
    PolicyBearing,
    PolicyScope,
    PolicyStrength,
    RepositoryAtlas,
    RepositoryRef,
    RetrievalProvenance,
    Review,
    ReviewDelta,
    ReviewStatus,
    SourceLocation,
    Verdict,
)
from archcompass.domain._support import utc_now
from archcompass.domain.case import Question
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.ports.policy_retrieval import PolicySelection, RetrievedPolicySet
from archcompass.reasoning.adapters.langchain import (
    CONVERSATION_CONTRACT,
    LangChainArchitectureJudge,
    LangChainQuestionGenerator,
    LangChainReviewAnswerer,
    QuestionOutput,
    conversation_prompt,
    judgement_prompt,
    question_prompt,
)
from archcompass.reasoning.records import JUDGE_PROMPT_IDENTITY, model_identity


class StructuredReply:
    """What `with_structured_output(..., include_raw=True)` actually answers with.

    A mapping of `parsed`, `raw` and `parsing_error` — never the schema, and never an
    exception. A double that returned the validated model instead would let the adapter cast
    the result straight to its schema and still pass here, which is the bug that reached a
    real provider once already.
    """

    def __init__(self, schema: type[Any], document: dict[str, object]) -> None:
        self._schema = schema
        self._document = document

    def invoke(self, prompt: str) -> dict[str, object]:
        assert prompt
        raw = SimpleNamespace(content=json.dumps(self._document))
        try:
            parsed = self._schema.model_validate(self._document)
        except ValidationError as error:
            return {"raw": raw, "parsed": None, "parsing_error": error}
        return {"raw": raw, "parsed": parsed, "parsing_error": None}


class StructuredModel:
    def __init__(self, document: dict[str, object]) -> None:
        self._document = document

    def with_structured_output(
        self, schema: type[Any], method: str = "json_schema", *, include_raw: bool = False
    ) -> StructuredReply:
        assert method == "json_schema"
        assert include_raw, "the adapter needs the raw response to explain a refusal"
        return StructuredReply(schema, self._document)


#: A selection to take an identity from. Any provider would do; this is the one the local
#: end-to-end suite runs on.
_CONFIG = ReasoningModelConfig(
    provider="ollama",
    model="qwen3.8:27b",
    timeout_seconds=1.0,
    thinking=False,
)


def _input() -> tuple[Candidate, ArchitectureCase, RetrievedPolicySet]:
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    policy = Policy(
        "policy-a",
        "Delay abstraction",
        "Keep a boundary only when it hides meaningful variation.",
        PolicyScope.GENERAL,
        PolicyStrength.GUIDANCE,
        "hash-a",
    )
    provenance = RetrievalProvenance(
        candidate.id, "test", "1", "corpus", (policy.id,)
    )
    return (
        candidate,
        ArchitectureCase.create(),
        RetrievedPolicySet(
            str(candidate.id), (PolicySelection(policy),), provenance
        ),
    )


def test_model_policy_citations_are_resolved_before_finding_construction() -> None:
    candidate, case, policies = _input()
    judge = LangChainArchitectureJudge(
        StructuredModel(
            {
                "verdict": "material",
                "reasoning": "The port hides no expected variation.",
                "policy_bearings": [
                    {"policy_id": "policy-a", "reasoning": "This policy bears directly."}
                ],
                "recommended_response": "Remove the pass-through port.",
            }
        ),  # type: ignore[arg-type]
        model_identity="test:model",
    )

    finding = judge.judge(candidate, case, policies)

    assert finding.verdict is Verdict.MATERIAL
    assert finding.policies[0].policy is policies.policies[0]
    assert finding.retrieval_identity == policies.provenance.identity


def test_a_policy_citation_naming_nothing_is_dropped_rather_than_fatal() -> None:
    """The trade that naming buys, and the reason the old ordinal could not buy it.

    A citation that names no presented policy is visibly wrong, so the bearing is dropped
    and the verdict still stands. An ordinal could not be checked that way: 2 out of 1 was
    fatal, and 1 out of 2 was silently the wrong policy, recorded as though it were right.
    """

    candidate, case, policies = _input()
    judge = LangChainArchitectureJudge(
        StructuredModel(
            {
                "verdict": "cleared",
                "reasoning": "No conflict.",
                "policy_bearings": [
                    {"policy_id": "policy-invented", "reasoning": "Unknown policy."}
                ],
            }
        ),  # type: ignore[arg-type]
        model_identity="test:model",
    )

    finding = judge.judge(candidate, case, policies)

    assert finding.verdict is Verdict.CLEARED
    assert finding.policies == ()


def test_a_policy_is_offered_to_the_judge_under_its_identifier() -> None:
    candidate, case, policies = _input()

    prompt = judgement_prompt(candidate, case, policies)

    assert "[policy-a] Delay abstraction" in prompt
    assert "cite one by copying that identifier exactly" in prompt


def test_hinge_and_recommendation_are_rejected_at_structured_boundary() -> None:
    candidate, case, policies = _input()
    judge = LangChainArchitectureJudge(
        StructuredModel(
            {
                "verdict": "material",
                "reasoning": "Ownership could change the verdict.",
                "hinge": "the owning team",
                "recommended_response": "Move the module.",
            }
        ),  # type: ignore[arg-type]
        model_identity="test:model",
    )

    # The schema rejects the pairing, and `include_raw=True` turns that rejection into a
    # `parsing_error` rather than a raise — so what reaches the caller is ArchCompass's
    # own error naming the model, not a Pydantic traceback from inside the runnable.
    with pytest.raises(ModelOutputValidationError, match="test:model"):
        judge.judge(candidate, case, policies)


def test_a_question_belongs_to_the_finding_it_was_asked_about() -> None:
    """A finding with no hinge cannot be asked about, because it is never asked about.

    This used to be a rule stated in prose and enforced with a raise: one call saw every
    finding under a number, cleared ones included, and returning the wrong number lost the
    whole review. The mapping is the application's now — one call per held finding — so the
    cleared finding is not in the call at all and there is no number to get wrong.
    """

    candidate, case, _ = _input()
    settled = Finding(candidate, Verdict.CLEARED, "No conflict.", (), ())
    uncertain_candidate = Candidate.identified(
        pattern="dependency_direction",
        summary="Ownership is unclear",
        participants=(Participant("domain.order", "source"),),
    )
    uncertain = Finding(
        uncertain_candidate,
        Verdict.HELD,
        "Ownership could change the verdict.",
        (),
        (),
        hinge="the owning team",
    )
    generator = LangChainQuestionGenerator(
        StructuredModel(
            {
                "text": "Who owns this?",
                "facet": "decision",
                "options": ["Payments owns it", "Platform owns it"],
            }
        )  # type: ignore[arg-type]
    )

    questions = generator.generate(
        case,
        (settled, uncertain),
        round=1,
        excluded_equivalence_keys=frozenset(),
    )

    assert len(questions) == 1
    assert questions[0].candidate_ids == (str(uncertain_candidate.id),)


def test_the_model_is_shown_one_held_finding_and_no_list_to_point_into() -> None:
    candidate, case, _ = _input()
    uncertain = Finding(
        candidate,
        Verdict.HELD,
        "Ownership could change the verdict.",
        (),
        (),
        hinge="the owning team",
    )

    prompt = question_prompt(uncertain, case)

    assert "waiting on: the owning team" in prompt
    assert "Port has one implementation" in prompt
    assert "numbered" not in prompt


def test_proposed_answers_survive_but_escape_hatches_do_not() -> None:
    """The interface already offers writing your own answer and skipping the question.

    A model that proposes "Other" is spending one of a handful of choices on something the
    reviewer has anyway, so it is dropped here rather than shown twice.
    """

    candidate, case, _ = _input()
    uncertain = Finding(
        candidate,
        Verdict.HELD,
        "Ownership could change the verdict.",
        (),
        (),
        hinge="the owning team",
    )
    generator = LangChainQuestionGenerator(
        StructuredModel(
            {
                "text": "Who owns this?",
                "facet": "decision",
                "options": [
                    "The domain team owns it",
                    "The platform team owns it",
                    "Other",
                    "Not sure",
                ],
            }
        )  # type: ignore[arg-type]
    )

    questions = generator.generate(
        case, (uncertain,), round=1, excluded_equivalence_keys=frozenset()
    )

    assert questions[0].options == (
        "The domain team owns it",
        "The platform team owns it",
    )


def test_a_choice_of_one_is_not_offered_as_a_choice() -> None:
    candidate, case, _ = _input()
    uncertain = Finding(
        candidate,
        Verdict.HELD,
        "Ownership could change the verdict.",
        (),
        (),
        hinge="the owning team",
    )
    generator = LangChainQuestionGenerator(
        StructuredModel(
            {
                "text": "Who owns this?",
                "facet": "decision",
                "options": ["The domain team owns it", "None of these"],
            }
        )  # type: ignore[arg-type]
    )

    questions = generator.generate(
        case, (uncertain,), round=1, excluded_equivalence_keys=frozenset()
    )

    assert questions[0].options == ()


def _answered_review(tmp_path: Path) -> Review:
    """A review whose material finding already says what to do about it."""

    candidate = Candidate.identified(
        pattern="leaky_abstraction",
        summary="Provider named outside its boundary",
        participants=(Participant("audiobook.synthesis.providers.qwen", "adapter"),),
        evidence=(
            Evidence(
                "'qwen' is named in 5 modules outside its package",
                SourceLocation("src/audiobook/synthesis/pipeline.py", 42, 48),
            ),
        ),
    )
    policy = Policy(
        "policy-a",
        "Keep a provider behind its port",
        "An implementation name outside its package is a boundary that is not holding.",
        PolicyScope.GENERAL,
        PolicyStrength.REQUIRED,
        "hash-a",
    )
    finding = Finding(
        candidate,
        Verdict.MATERIAL,
        "Five modules reach past the port.",
        (PolicyBearing(policy, "The port is named around, not through."),),
        (),
        recommended_response="Resolve the provider through a factory at composition time.",
    )
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    now = utc_now()
    return Review(
        "review-1",
        1,
        repository,
        RepositoryAtlas("atlas", repository),
        ArchitectureCase.create(),
        (finding,),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(candidate,)),
        now,
        now,
    )


def test_a_conversation_is_shown_what_the_review_says_to_do(tmp_path: Path) -> None:
    # "How would it be fixed?" was answered with "the review does not contain any
    # information on how to fix the identified issues" while the finding it was about
    # carried a recommended response the prompt never included. What a fix has to respect —
    # the policy wording — and where the evidence sits were missing for the same reason.
    prompt = conversation_prompt(_answered_review(tmp_path), (), "How would it be fixed?")

    assert "Resolve the provider through a factory at composition time." in prompt
    assert "An implementation name outside its package" in prompt
    assert "src/audiobook/synthesis/pipeline.py:42-48" in prompt


def test_a_conversation_may_reason_past_what_the_review_records() -> None:
    # Asking what to do about a finding is not a question the review is missing the facts
    # for; it is the question the reader came with. The contract has to permit an answer
    # and still pin every fact in it to the review.
    assert "how a finding would be fixed" in CONVERSATION_CONTRACT
    assert "Facts about this codebase come only from the review." in CONVERSATION_CONTRACT


def test_a_cited_finding_is_returned_as_the_candidate_it_belongs_to(tmp_path: Path) -> None:
    review = _answered_review(tmp_path)
    cited = str(review.findings[0].candidate.id)
    answerer = LangChainReviewAnswerer(
        StructuredModel(
            {
                "answer": "Resolve it through a factory; the review recommends as much.",
                "candidate_ids": [cited],
            }
        )  # type: ignore[arg-type]
    )

    answer = answerer.answer(review, (), "How would it be fixed?")

    assert answer.supporting_candidate_ids == (cited,)


def test_a_finding_the_review_does_not_hold_grounds_nothing(tmp_path: Path) -> None:
    """The answer survives its own bad citation, because the citation is a name.

    An identifier the review does not hold matches nothing and is dropped, so the reader
    loses one grounding chip and keeps the reply. The ordinal this replaced had no such
    reading: in range it grounded the answer on a finding the model never used, and out of
    range it raised.
    """

    review = _answered_review(tmp_path)
    answerer = LangChainReviewAnswerer(
        StructuredModel(
            {
                "answer": "Resolve it through a factory.",
                "candidate_ids": ["candidate_invented", str(review.findings[0].candidate.id)],
            }
        )  # type: ignore[arg-type]
    )

    answer = answerer.answer(review, (), "How would it be fixed?")

    assert answer.text == "Resolve it through a factory."
    assert answer.supporting_candidate_ids == (str(review.findings[0].candidate.id),)


def test_a_conversation_lists_every_finding_under_its_identifier(tmp_path: Path) -> None:
    review = _answered_review(tmp_path)

    prompt = conversation_prompt(review, (), "How would it be fixed?")

    assert f"[{review.findings[0].candidate.id}]" in prompt
    assert "return the bracketed identifier of each one you used" in CONVERSATION_CONTRACT


def test_an_empty_case_says_so_rather_than_arriving_as_empty_arrays() -> None:
    """The reason a real model never asked anything.

    An empty case used to reach the judge as `{"constraints": [], "decisions": [],
    "answers": []}` — three empty arrays beside a fully-stocked policy corpus. A model
    reading that has a rule to judge against and punctuation where the team's intent would
    be, so it judges on the policy and the clarification round never runs. The prompt now
    says what an empty case is, and gives asking standing rather than mere permission.
    """

    candidate, case, policies = _input()

    prompt = judgement_prompt(candidate, case, policies)

    assert "Nobody has answered anything about this architecture yet" in prompt
    assert '"constraints": []' not in prompt
    assert "Asking is a first-class outcome here" in prompt
    # And it is not an instruction to hedge: a hinge interrupts a person, so the contract
    # says when not to raise one as plainly as when to.
    assert "do not hinge merely to avoid committing" in prompt


def test_an_answered_case_is_carried_as_what_was_asked_and_said() -> None:
    candidate, _, policies = _input()
    question = Question.create(
        text="Is one implementation deliberate?",
        facet=CaseFacet.DECISION,
        candidate_ids=(str(candidate.id),),
        round=1,
    )
    case = ArchitectureCase.create().with_answer(
        Answer(question, AnswerStatus.ANSWERED, "Yes, a second is coming", "architect", utc_now())
    )

    prompt = judgement_prompt(candidate, case, policies)

    assert "Is one implementation deliberate?" in prompt
    assert "Yes, a second is coming" in prompt
    assert "Nobody has answered anything" not in prompt


def test_a_question_without_proposed_answers_is_rejected_at_the_boundary() -> None:
    """A blank box is what the round looked like, and the schema now refuses to produce one.

    The interface offers writing your own answer and skipping under every question,
    structurally — so a menu is never a closed set and the model does not need to leave room
    for one by returning nothing.
    """

    with pytest.raises(ValidationError):
        QuestionOutput.model_validate(
            {"text": "Who owns this?", "facet": "decision", "options": []}
        )


def test_a_refused_question_costs_the_round_that_question_and_no_more() -> None:
    """One finding's question is lost; the review that earned it is not.

    Every candidate has already been retrieved for, judged and investigated by the time a
    question is asked. A schema violation here used to propagate out of the graph and throw
    all of that away, which is how a clarification round — an improvement to a review — came
    to be able to destroy one.
    """

    candidate, case, _ = _input()
    uncertain = Finding(
        candidate,
        Verdict.HELD,
        "Ownership could change the verdict.",
        (),
        (),
        hinge="the owning team",
    )
    generator = LangChainQuestionGenerator(
        StructuredModel(
            {"text": "Who owns this?", "facet": "decision", "options": []}
        )  # type: ignore[arg-type]
    )

    assert (
        generator.generate(
            case, (uncertain,), round=1, excluded_equivalence_keys=frozenset()
        )
        == ()
    )


def test_a_judgement_is_stamped_with_the_identity_the_delta_will_compare_it_against() -> None:
    """The two halves of one comparison, asserted to be one value.

    `DeterministicRevisionCalculator` asks whether the stamp on a stored finding still
    matches what this process would produce, and reports `ChangeCause.PROMPT` when it does
    not. So the string the adapters write and the string `bootstrap` computes have to be
    the same string — and for a while they were three literals and two f-strings across
    four modules, agreeing by coincidence.

    `analysis/delta.py` records what the disagreement costs: every candidate of every
    review reports a changed prompt for ever, and the comment there says the corpus
    fingerprint had already done exactly that once.
    """

    candidate, case, policies = _input()
    judge = LangChainArchitectureJudge(
        StructuredModel(
            {"verdict": "cleared", "reasoning": "The boundary earns its keep."}
        ),  # type: ignore[arg-type]
        model_identity=model_identity(_CONFIG),
    )

    finding = judge.judge(candidate, case, policies)

    # What the adapter stamped, against what the revision calculator will compare it to.
    assert finding.prompt_identity == JUDGE_PROMPT_IDENTITY
    assert finding.model_identity == model_identity(_CONFIG)
    assert finding.model_identity == "ollama:qwen3.8:27b:thinking=False"
    # Thinking belongs in the identity: the same model asked to think is not the same judge,
    # and a cache that ignored it would hand back the other one's answer.
    assert model_identity(_CONFIG) != model_identity(
        _CONFIG.model_copy(update={"thinking": True})
    )


def test_a_held_verdict_must_name_the_fact_it_turns_on() -> None:
    """`held` is a question, and a question with nothing in it is a verdict in disguise.

    It used to be unrepresentable the other way round: the verdict was inferred *from* the
    hinge, so held-without-a-hinge could not be expressed and material-with-a-hinge silently
    became held with the materiality discarded. Now the verdict is chosen and the hinge is
    what it is allowed to carry, so both halves are checked in the same place.
    """

    from archcompass.reasoning.adapters.langchain import FindingOutput

    with pytest.raises(ValidationError, match="must name the fact"):
        FindingOutput(verdict="held", reasoning="I cannot tell.")

    settled = FindingOutput(
        verdict="held", reasoning="I cannot tell.", hinge="Is a second one planned?"
    )
    assert settled.hinge


@pytest.mark.parametrize("verdict", ["material", "cleared"])
def test_a_verdict_that_answered_has_nothing_left_to_ask(verdict: str) -> None:
    """A finding cannot both decide and ask. The old shape could say both and lost one."""

    from archcompass.reasoning.adapters.langchain import FindingOutput

    with pytest.raises(ValidationError, match="nothing left to ask"):
        FindingOutput(
            verdict=verdict,  # type: ignore[arg-type]
            reasoning="Decided.",
            hinge="but also, is a second one planned?",
        )


@pytest.mark.parametrize("verdict", ["cleared", "held"])
def test_only_a_material_finding_recommends_a_response(verdict: str) -> None:
    """Unchanged in substance, anchored on the verdict rather than on the boolean."""

    from archcompass.reasoning.adapters.langchain import FindingOutput

    with pytest.raises(ValidationError, match="only a material finding"):
        FindingOutput(
            verdict=verdict,  # type: ignore[arg-type]
            reasoning="Decided.",
            hinge="Is a second one planned?" if verdict == "held" else None,
            recommended_response="Collapse the port.",
        )


def test_the_verdict_is_taken_from_the_model_rather_than_inferred() -> None:
    """Each of the three arrives as itself, and none is reconstructed from another field."""

    from archcompass.reasoning.adapters.langchain import FindingOutput, finding_from_output

    candidate, _case, policies = _input()
    for chosen, expected in (
        ("material", Verdict.MATERIAL),
        ("cleared", Verdict.CLEARED),
        ("held", Verdict.HELD),
    ):
        output = FindingOutput(
            verdict=chosen,  # type: ignore[arg-type]
            reasoning="Because.",
            hinge="Is a second one planned?" if chosen == "held" else None,
        )
        finding = finding_from_output(
            output, candidate, policies, model_identity="m", prompt_identity="p"
        )
        assert finding.verdict is expected
