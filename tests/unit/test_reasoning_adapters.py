from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final

import pytest
from pydantic import ValidationError

from archcompass.configuration import EmbeddingModelConfig, ReasoningModelConfig
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
from archcompass.domain.errors import ModelOutputValidationError, ProviderError
from archcompass.ports.policy_retrieval import PolicySelection, RetrievedPolicySet
from archcompass.reasoning.adapters.factory import build_embeddings
from archcompass.reasoning.adapters.langchain import (
    CONVERSATION_CONTRACT,
    LangChainArchitectureJudge,
    LangChainQuestionGenerator,
    LangChainReviewAnswerer,
    PolicyBearingOutput,
    QuestionOutput,
    conversation_prompt,
    judgement_prompt,
    question_prompt,
)
from archcompass.reasoning.adapters.selected import SelectedLangChainChatModel
from archcompass.reasoning.records import JUDGE_PROMPT_IDENTITY, model_identity

#: One citation, so a construction testing some *other* invariant satisfies the one every
#: verdict carries. The tests that are about the citation itself say so in their own names.
_CITED: Final = [PolicyBearingOutput(policy_id="policy-a", reasoning="It applies.")]


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


class RaisingStructuredReply:
    """The other shape a transport answers a refused schema in: a raise, not a mapping.

    `include_raw=True` promises the mapping above, and `langchain-openai` does not deliver
    it — it binds the Pydantic class to `response_format`, so the OpenAI SDK validates
    inside the HTTP call and a violation escapes before any mapping is built. Measured: the
    same deliberate cross-field violation came back as `parsing_error` on Google and as a
    raised `ValidationError` through `ChatOpenAI`, where it skipped the repair entirely and
    failed the whole review over one candidate.

    Scripted rather than fixed, so a test can say what the second answer is and count how
    many were asked for.
    """

    def __init__(self, schema: type[Any], documents: Sequence[dict[str, object]]) -> None:
        self._schema = schema
        self._documents = list(documents)
        self.calls = 0

    def invoke(self, prompt: str) -> dict[str, object]:
        assert prompt
        self.calls += 1
        document = self._documents[min(self.calls, len(self._documents)) - 1]
        # No try/except: escaping is the whole point of this double.
        parsed = self._schema.model_validate(document)
        return {
            "raw": SimpleNamespace(content=json.dumps(document)),
            "parsed": parsed,
            "parsing_error": None,
        }


class RaisingStructuredModel:
    def __init__(self, documents: Sequence[dict[str, object]]) -> None:
        self._documents = documents
        self.reply: RaisingStructuredReply | None = None

    def with_structured_output(
        self, schema: type[Any], method: str = "json_schema", *, include_raw: bool = False
    ) -> RaisingStructuredReply:
        assert method == "json_schema"
        assert include_raw, "the adapter needs the raw response to explain a refusal"
        self.reply = RaisingStructuredReply(schema, self._documents)
        return self.reply


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
    """Labelled and on its own line, because the citation check is exact.

    It used to read `[policy-a] Delay abstraction`, and two model families cited
    `[policy-a]` — brackets included — which the check refused every time. Nothing repairs a
    near miss downstream, because a fuzzy match would make a wrong identifier look like a
    typo, so the format has to leave no room for the question here.
    """

    candidate, case, policies = _input()

    prompt = judgement_prompt(candidate, case, policies)

    assert "Policy ID: policy-a\nDelay abstraction" in prompt
    assert "[policy-a]" not in prompt
    assert "cite one by copying that identifier exactly" in prompt


_VIOLATION: Final = {
    "verdict": "material",
    "reasoning": "Ownership could change the verdict.",
    "hinge": "the owning team",
    "recommended_response": "Move the module.",
    # Cited, so what this violates is the cross-field rule it is named for and not the
    # citation requirement underneath it.
    "policy_bearings": [{"policy_id": "policy-a", "reasoning": "It applies."}],
}
_HONOURED: Final = {
    "verdict": "cleared",
    "reasoning": "The boundary hides a real variation.",
    "policy_bearings": [{"policy_id": "policy-a", "reasoning": "It applies."}],
}


def test_a_transport_that_raises_is_repaired_like_one_that_reports() -> None:
    """Both shapes of refusal buy the same one repair.

    `with_structured_output(include_raw=True)` says a violation arrives as `parsing_error`.
    One transport of three raises instead, and the repair used to be skipped on that one —
    so a cross-field violation that Google recovered from killed the review on `ChatOpenAI`.
    The two are the same event, and the point of this test is that they are now one path.
    """

    candidate, case, policies = _input()
    model = RaisingStructuredModel([_VIOLATION, _HONOURED])
    judge = LangChainArchitectureJudge(model, model_identity="test:model")  # type: ignore[arg-type]

    finding = judge.judge(candidate, case, policies)

    assert finding.verdict is Verdict.CLEARED
    assert model.reply is not None
    assert model.reply.calls == 2, "the violation should have bought exactly one repair"


def test_a_transport_that_keeps_raising_fails_as_our_error_and_asks_once() -> None:
    """Visible, named, and asked for once — not a Pydantic traceback, and not a loop.

    A model that cannot honour a contract having just been shown the contract and its own
    violation of it will not honour it on the fourth attempt either, so the ceiling is one
    repair whichever way the transport reports the first refusal.
    """

    candidate, case, policies = _input()
    model = RaisingStructuredModel([_VIOLATION])
    judge = LangChainArchitectureJudge(model, model_identity="test:model")  # type: ignore[arg-type]

    with pytest.raises(ModelOutputValidationError, match="test:model") as refused:
        judge.judge(candidate, case, policies)

    assert "a finding that reached a verdict has nothing left to ask" in str(refused.value)
    assert model.reply is not None
    assert model.reply.calls == 2, "one attempt and one repair, never a retry loop"


def test_a_transport_failure_is_not_read_as_a_bad_answer() -> None:
    """The net around the parse must not swallow the transport underneath it.

    `call_with_retry` sits inside `_attempt`, so a provider refusal still reaches the caller
    as a `ProviderError` to be waited on or reported — never as "the model wrote something
    unusable", which would spend a repair call on a rate limit.
    """

    candidate, case, policies = _input()

    class Refusing:
        def with_structured_output(
            self, schema: type[Any], method: str = "json_schema", *, include_raw: bool = False
        ) -> Any:
            assert schema and method and include_raw

            class Reply:
                def invoke(self, prompt: str) -> dict[str, object]:
                    assert prompt
                    raise ProviderError("the provider is unreachable")

            return Reply()

    judge = LangChainArchitectureJudge(Refusing(), model_identity="test:model")  # type: ignore[arg-type]

    with pytest.raises(ProviderError, match="unreachable"):
        judge.judge(candidate, case, policies)


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
            {
                "verdict": "cleared",
                "reasoning": "The boundary earns its keep.",
                "policy_bearings": [
                    {"policy_id": "policy-a", "reasoning": "It applies."}
                ],
            }
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
        FindingOutput(verdict="held", reasoning="I cannot tell.", policy_bearings=_CITED)

    settled = FindingOutput(
        verdict="held",
        reasoning="I cannot tell.",
        hinge="Is a second one planned?",
        policy_bearings=_CITED,
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
            policy_bearings=_CITED,
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
            policy_bearings=_CITED,
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
            policy_bearings=_CITED,
        )
        finding = finding_from_output(
            output, candidate, policies, model_identity="m", prompt_identity="p"
        )
        assert finding.verdict is expected


def test_a_verdict_outside_the_three_is_refused_rather_than_guessed_at() -> None:
    """The path that cannot normally happen, guarded for when it does.

    `with_structured_output(..., method="json_schema")` puts the `Literal` into the decoder's
    grammar, so a supported provider cannot emit a fourth word — asked three times, in so
    many words, for a verdict of `catastrophic`, a local model answered `cleared` every time.
    This covers what is left: a provider whose constraint does not hold, a proxy that rewrites
    the response, a future transport that sends the schema as documentation rather than as a
    grammar.

    What must not happen is a guess. There is no default verdict and no nearest-match: an
    unrecognised word is a model that did not answer the question, and a review that invented
    `cleared` for it would be recording a judgement nobody made.
    """

    candidate, case, policies = _input()
    judge = LangChainArchitectureJudge(
        StructuredModel(
            {"verdict": "catastrophic", "reasoning": "The port hides no variation."}
        ),  # type: ignore[arg-type]
        model_identity="test:model",
    )

    with pytest.raises(ModelOutputValidationError, match="did not match the required"):
        judge.judge(candidate, case, policies)


def test_every_client_on_the_review_path_has_a_deadline() -> None:
    """A client with no timeout does not fail a review, it hangs one.

    `OllamaEmbeddings` was built with none: `sync_client_kwargs` defaults to `{}`, the ollama
    client's own default is `timeout=None`, and httpx reads `None` as wait forever. Retrieval
    runs once per candidate and before any judging, so a local embedder that stopped
    answering left the run with nothing judged, no error, and nothing to end it — which is
    indistinguishable from a run that is simply slow.

    Asked of the built object rather than of the call site, because what matters is the
    deadline the transport actually carries.
    """

    embeddings = build_embeddings(
        EmbeddingModelConfig(
            provider="ollama",
            model="embeddinggemma",
            dimensions=768,
            base_url="http://localhost:11434",
        )
    )
    # `TaskPromptedEmbeddings` wraps the real one for models that take a task prefix.
    inner = getattr(embeddings, "_inner", embeddings)
    configured = inner.sync_client_kwargs or {}
    assert configured.get("timeout"), (
        "the ollama embedding client carries no timeout, so a retrieval that stops "
        "answering hangs the review instead of failing it"
    )
    assert configured["timeout"] <= 360.0, (
        "an embedding is a forward pass, not a model thinking; it should not be allowed "
        "the budget a judgement gets"
    )


def _ollama_config(*, parallel: int) -> ReasoningModelConfig:
    return ReasoningModelConfig(
        provider="ollama",
        model="qwen3.8:27b",
        base_url="http://localhost:11434",
        timeout_seconds=360.0,
        context_window_tokens=65536,
        max_output_tokens=8192,
        max_parallel_requests=parallel,
    )


class _Selection:
    """A workspace's model choice, which a test can change between calls like a person can."""

    def __init__(self, config: ReasoningModelConfig) -> None:
        self.config = config

    def current(self) -> ReasoningModelConfig | None:
        return self.config


def test_a_single_slot_provider_is_asked_for_one_judgement_at_a_time() -> None:
    """The bound that stops a fan-out from becoming a queue somebody's deadline expires in.

    A review dispatches every selected candidate at once — forty-six is an ordinary number
    on a real repository — and each branch is one request. Against a local runner with one
    slot that is not forty-six judgements in parallel, it is one judgement and forty-five
    requests waiting their turn on a clock that started when they were sent. Measured at
    about thirty-five seconds a judgement against a 360-second deadline, everything past the
    tenth is unreachable: the observed run reported nine judged, stopped moving, and had
    thirty-six timeouts queued behind it.
    """

    selected = SelectedLangChainChatModel(_Selection(_ollama_config(parallel=1)))
    holding = threading.Event()
    release = threading.Event()
    second_entered = threading.Event()

    def first() -> None:
        with selected.in_use():
            holding.set()
            release.wait(timeout=5)

    def second() -> None:
        with selected.in_use():
            second_entered.set()

    one = threading.Thread(target=first)
    one.start()
    assert holding.wait(timeout=5)

    two = threading.Thread(target=second)
    two.start()
    # The whole of the fix: while one caller has the slot, the next one waits rather than
    # sending a request the provider will not look at for another five minutes.
    assert not second_entered.wait(timeout=0.25)

    release.set()
    # And waits rather than never arriving: the slot is handed on, not withheld.
    assert second_entered.wait(timeout=5)
    one.join(timeout=5)
    two.join(timeout=5)


def test_a_provider_that_answers_in_parallel_is_not_narrowed_to_one() -> None:
    """The number is the provider's, not a blanket serialisation of the review.

    Four callers must be inside at once for the barrier to release; a gate that admitted one
    would leave it broken. Otherwise the fix for a local runner would have quietly turned a
    hosted review — where the fan-out is the point — into a single file.
    """

    selected = SelectedLangChainChatModel(_Selection(_ollama_config(parallel=4)))
    together = threading.Barrier(4)
    failures: list[BaseException] = []

    def use() -> None:
        try:
            with selected.in_use():
                together.wait(timeout=5)
        except BaseException as error:
            failures.append(error)

    threads = [threading.Thread(target=use) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not failures


def test_switching_model_switches_the_slots_it_is_asked_for() -> None:
    """A workspace that moves off the local runner must not keep its single slot.

    The selection changes while the process runs — it is a `PUT` away — so the gate is a
    property of the transport in force rather than of the object that hands transports out.
    """

    selection = _Selection(_ollama_config(parallel=1))
    selected = SelectedLangChainChatModel(selection)
    with selected.in_use() as (first_model, _):
        pass

    selection.config = _ollama_config(parallel=4).model_copy(
        update={"model": "gemma4:26b-mlx"}
    )
    together = threading.Barrier(4)
    failures: list[BaseException] = []

    def use() -> None:
        try:
            with selected.in_use() as (model, _):
                assert model is not first_model
                together.wait(timeout=5)
        except BaseException as error:
            failures.append(error)

    threads = [threading.Thread(target=use) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not failures


def test_a_verdict_must_cite_a_policy_rather_than_only_mention_one() -> None:
    """A bearing is the record of why a verdict was reached, so a verdict carries one.

    The field was optional and a local model left it empty on two thirds of its judgements
    — while naming the policy inside `reasoning`, quoting the exception it turned on, and
    weighing the measurement against its own stated limits. The reasoning was sound and the
    record of it was dropped on the floor, because prose naming a policy is not a citation
    and nothing was asking for one.

    Required for all three verdicts, not only `material`: clearing a structure is a
    judgement against a policy just as finding it material is, and it is the clearings a
    reader is least able to reconstruct without one.
    """

    from archcompass.reasoning.adapters.langchain import FindingOutput

    for verdict in ("material", "cleared", "held"):
        with pytest.raises(ValidationError, match="policy_bearings"):
            FindingOutput(
                verdict=verdict,  # type: ignore[arg-type]
                reasoning="Under [policy-a] the boundary earns its keep.",
                hinge="Is a second one planned?" if verdict == "held" else None,
            )


def test_every_held_finding_is_asked_about() -> None:
    """No ceiling on questions either, and this overflow was the worse of the two.

    The cap read as a deferral — the hinges past it stayed held and the next round asked
    them. But a review seals at `round >= 3`, so a hinge deferred twice is a hinge never
    asked, and the finding it belonged to was sealed on a verdict reached without the answer
    it turned on. A form nobody finishes is a smaller problem than a question nobody hears.
    """

    from archcompass.reasoning.adapters import langchain

    assert not hasattr(langchain, "MAX_ASKED_HINGES")

    source = Path(langchain.__file__).read_text(encoding="utf-8")
    line = next(
        item
        for item in source.splitlines()
        if "held = tuple(finding for finding in findings if finding.hinge)" in item
    )
    assert not line.rstrip().endswith("]"), "held findings are still being sliced"
