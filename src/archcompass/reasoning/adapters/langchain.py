"""LangChain model boundary: Pydantic outside, frozen dataclasses inside."""

from __future__ import annotations

import json
from typing import Literal, cast

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field, model_validator

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    CaseFacet,
    Finding,
    PolicyBearing,
    Question,
    Review,
    Verdict,
)
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.ports.policy_retrieval import RetrievedPolicySet
from archcompass.ports.review_conversation import (
    ConversationAnswer,
    ConversationMessage,
)


class PolicyBearingOutput(BaseModel):
    policy_position: int = Field(ge=1)
    reasoning: str = Field(min_length=1)


class FindingOutput(BaseModel):
    material: bool
    reasoning: str = Field(min_length=1)
    policy_bearings: list[PolicyBearingOutput] = Field(
        default_factory=list[PolicyBearingOutput]
    )
    hinge: str | None = None
    recommended_response: str | None = None

    @model_validator(mode="after")
    def response_only_for_material_finding(self) -> FindingOutput:
        if self.hinge and self.recommended_response:
            raise ValueError(
                "a finding with an uncertainty hinge cannot recommend a response"
            )
        if not self.material and self.recommended_response:
            raise ValueError("only a material finding may recommend a response")
        return self


class QuestionOutput(BaseModel):
    text: str = Field(min_length=1)
    facet: Literal[
        "goal", "constraint", "decision", "assumption", "expected_change", "non_goal"
    ]
    candidate_positions: list[int] = Field(min_length=1)


class QuestionsOutput(BaseModel):
    questions: list[QuestionOutput] = Field(default_factory=list[QuestionOutput])


class ConversationAnswerOutput(BaseModel):
    answer: str = Field(min_length=1)
    candidate_positions: list[int] = Field(default_factory=list[int])


def _case_text(case: ArchitectureCase) -> str:
    return json.dumps(
        {
            "goal": case.goal,
            "constraints": [item.text for item in case.constraints],
            "decisions": [item.text for item in case.decisions],
            "answers": [
                {
                    "question": item.question.text,
                    "status": item.status.value,
                    "value": item.value,
                }
                for item in case.answers
            ],
        },
        ensure_ascii=False,
    )


def _structured[Output: BaseModel](
    model: BaseChatModel,
    schema: type[Output],
    prompt: str,
    *,
    subject: str,
    model_identity: str | None = None,
) -> Output:
    """One structured call, with the raw response kept so a refusal can be explained.

    `include_raw=True` is what makes a schema violation reportable instead of a bare
    `ValidationError` from somewhere inside the runnable: the call answers with the parsed
    value, the raw message, and the parsing error side by side. The cost is that the result
    is a mapping and never the schema, and forgetting that is exactly the bug this function
    exists to make impossible — two of the three callers used to cast the mapping straight to
    their schema and would have failed on the first attribute they read.
    """

    result = cast(
        dict[str, object],
        model.with_structured_output(
            schema, method="json_schema", include_raw=True
        ).invoke(prompt),
    )
    parsing_error = result.get("parsing_error")
    output = result.get("parsed")
    if parsing_error is None and isinstance(output, schema):
        return output

    raw_content = getattr(result.get("raw"), "content", "")
    preview = " ".join(str(raw_content).split())
    if len(preview) > 240:
        preview = preview[:237] + "..."

    named = (
        "The reasoning model"
        if model_identity is None
        else f"Reasoning model {model_identity}"
    )
    message = (
        f"{named} returned output that did not match the required JSON schema "
        f"for {subject}."
    )
    # The parser's own account of what was wrong, not just what was said. Without it a
    # cross-field rule the JSON schema cannot express — a hinge beside a recommendation —
    # reads as "the model returned nonsense", and the nonsense is well-formed JSON.
    if parsing_error is not None:
        reason = " ".join(str(parsing_error).split())
        message += f" The parser reported: {reason[:400]}"
    if preview:
        message += f" Response started with: {preview!r}."
    message += (
        " If you are using Ollama, try enabling Thinking or choose a model/runtime "
        "that supports structured JSON output."
    )
    if isinstance(parsing_error, Exception):
        raise ModelOutputValidationError(message) from parsing_error
    raise ModelOutputValidationError(message)


class LangChainArchitectureJudge:
    """One controlled structured call; the model never supplies ArchCompass identity."""

    def __init__(
        self,
        model: BaseChatModel,
        *,
        model_identity: str,
        prompt_identity: str = "judge:v2",
    ) -> None:
        self._model = model
        self._model_identity = model_identity
        self._prompt_identity = prompt_identity

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
    ) -> Finding:
        prompt = "\n\n".join(
            (
                "Judge whether this detected structure costs more than it earns. "
                "Use only the supplied evidence and case. Policies are numbered from 1; "
                "refer to them only by position. If missing human context could change the "
                "verdict, state one concise hinge and leave the recommended response empty: "
                "a judgement that is waiting on an answer does not yet recommend anything. "
                "Only a material finding with no hinge may recommend a response. "
                "Return only the structured response required by the supplied output schema. "
                "Do not return Markdown or explanatory prose outside the structured response.",
                f"CASE\n{_case_text(case)}",
                f"CANDIDATE\n{candidate}",
                "POLICIES\n"
                + "\n\n".join(
                    f"[{position}] {policy.title}\n{policy.body}"
                    for position, policy in enumerate(policies.policies, start=1)
                ),
            )
        )
        output = _structured(
            self._model,
            FindingOutput,
            prompt,
            subject="a review finding",
            model_identity=self._model_identity,
        )

        bearings: list[PolicyBearing] = []
        seen: set[int] = set()
        for bearing in output.policy_bearings:
            if bearing.policy_position > len(policies.policies):
                raise ValueError(
                    f"model cited policy position {bearing.policy_position}, but only "
                    f"{len(policies.policies)} policies were presented"
                )
            if bearing.policy_position in seen:
                raise ValueError("model cited one policy position more than once")
            seen.add(bearing.policy_position)
            bearings.append(
                PolicyBearing(
                    policies.policies[bearing.policy_position - 1], bearing.reasoning
                )
            )
        verdict = (
            Verdict.HELD
            if output.hinge
            else Verdict.MATERIAL if output.material else Verdict.CLEARED
        )
        return Finding(
            candidate=candidate,
            verdict=verdict,
            reasoning=output.reasoning,
            policies=tuple(bearings),
            evidence=candidate.evidence,
            hinge=output.hinge,
            recommended_response=output.recommended_response,
            model_identity=self._model_identity,
            prompt_identity=self._prompt_identity,
            retrieval_identity=policies.provenance.identity,
        )


class LangChainQuestionGenerator:
    def __init__(
        self, model: BaseChatModel, *, prompt_identity: str = "questions:v1"
    ) -> None:
        self._model = model
        self._prompt_identity = prompt_identity

    @property
    def prompt_identity(self) -> str:
        return self._prompt_identity

    def generate(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        round: int,
        excluded_equivalence_keys: frozenset[str],
    ) -> tuple[Question, ...]:
        if not findings or not any(finding.hinge for finding in findings):
            return ()
        prompt = "\n\n".join(
            (
                "Ask only questions whose answers could settle the supplied findings. "
                "Merge duplicates. Candidate positions are numbered from 1. Do not invent "
                "identifiers and do not ask about a finding without a hinge.",
                f"CASE\n{_case_text(case)}",
                "FINDINGS\n"
                + "\n".join(
                    f"[{position}] {finding.candidate.summary}; hinge={finding.hinge}"
                    for position, finding in enumerate(findings, start=1)
                ),
            )
        )
        output = _structured(
            self._model, QuestionsOutput, prompt, subject="the review's questions"
        )
        questions: list[Question] = []
        seen: set[str] = set()
        for proposed in output.questions:
            positions = tuple(sorted(set(proposed.candidate_positions)))
            if any(position < 1 or position > len(findings) for position in positions):
                raise ValueError("model returned an unknown candidate position")
            if any(not findings[position - 1].hinge for position in positions):
                raise ValueError(
                    "model returned a candidate position for a finding without a hinge"
                )
            question = Question.create(
                text=proposed.text,
                facet=CaseFacet(proposed.facet),
                candidate_ids=tuple(
                    str(findings[position - 1].candidate.id) for position in positions
                ),
                round=round,
            )
            if (
                question.equivalence_key not in excluded_equivalence_keys
                and question.equivalence_key not in seen
            ):
                seen.add(question.equivalence_key)
                questions.append(question)
        return tuple(questions)


class LangChainReviewAnswerer:
    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    def answer(
        self,
        review: Review,
        history: tuple[ConversationMessage, ...],
        question: str,
    ) -> ConversationAnswer:
        prompt = "\n\n".join(
            (
                "Answer the question using only this immutable architecture review. "
                "Cite supporting findings by their numbered positions. If the review "
                "does not answer it, say so explicitly.",
                "FINDINGS\n"
                + "\n".join(
                    f"[{position}] {finding.candidate.summary}: {finding.verdict.value}; "
                    f"{finding.reasoning}"
                    for position, finding in enumerate(review.findings, start=1)
                ),
                "HISTORY\n"
                + "\n".join(
                    f"Q: {item.question}\nA: {item.answer.text}" for item in history
                ),
                f"QUESTION\n{question}",
            )
        )
        output = _structured(
            self._model,
            ConversationAnswerOutput,
            prompt,
            subject="a grounded answer",
        )
        positions = tuple(sorted(set(output.candidate_positions)))
        if any(
            position < 1 or position > len(review.findings) for position in positions
        ):
            raise ValueError("model returned an unknown finding position")
        return ConversationAnswer(
            output.answer,
            tuple(
                str(review.findings[position - 1].candidate.id)
                for position in positions
            ),
        )
