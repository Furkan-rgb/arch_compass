"""Provider-neutral structured reasoning over a pluggable chat transport.

Every reasoning stage decides the same three things regardless of which vendor answers
it: what the model is told, which handles it may reference, and what shape the reply
must take. Those decisions live here, once. A `ChatTransport` owns only the part that
genuinely differs between vendors - request options, timeouts, retries, and translating
a failure into `ProviderError`.

This split is what `separate-model-context-from-provider-transport` asks for: the
semantic context and its response grammar are assembled above the transport boundary,
and an adapter merely encodes an already-decided request.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import ClassVar, Literal, Protocol, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from archcompass.adapters.models.prompt_contracts import STAGE_PROMPTS
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.base import canonical_json
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.errors import (
    ModelOutputValidationError,
    PromptBudgetExceededError,
    ProviderError,
)
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import (
    BoundaryReview,
    CandidateVerdict,
    OverviewStatement,
    PolicyBearing,
    ReviewedBoundary,
    ReviewOverview,
)
from archcompass.domain.review_conversation import ReviewAnswer, ReviewMessage
from archcompass.ports.reasoning import ReasoningTask

Item = TypeVar("Item", bound=BaseModel)

#: One turn of the conversation sent to a model, in the role/content form every chat
#: API accepts. A transport reshapes it into whatever its own SDK wants.
ChatMessage = dict[str, str]

#: Reasoning-effort control: off, on, or an explicit level. Named after Ollama's
#: `think` parameter because that is where it was first needed; a transport whose
#: vendor spells it differently maps it.
ThinkLevel = bool | Literal["low", "medium", "high"] | None


def timeout_seconds(config: ReasoningModelConfig, *, is_fast: bool) -> float:
    """The timeout a stage runs under, given its budget class."""

    configured = config.fast_timeout_seconds if is_fast else config.deep_timeout_seconds
    return configured if configured is not None else config.timeout_seconds


def _grounded_statements(
    proposed: list[ProposedOverviewStatement],
    boundaries: list[ReviewedBoundary],
) -> list[OverviewStatement]:
    """Attach references from positions, and drop what rests on nothing.

    A statement flagging no boundary is discarded rather than kept as unsupported prose —
    the same treatment a policy bearing asserted without saying how receives. It is dropped
    instead of failing the review because the verdicts underneath it are already correct and
    already cost a model call each; what is lost is a sentence, and what would be lost by
    failing is the whole run.
    """

    statements: list[OverviewStatement] = []
    for item in proposed:
        references = [
            boundary.reference
            for boundary, supports in zip(boundaries, item.supported_by, strict=True)
            if supports
        ]
        if not references or not item.text.strip():
            continue
        statements.append(
            OverviewStatement(text=item.text.strip(), supporting_references=references)
        )
    return statements


def _object_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    source = cast(Mapping[object, object], value)
    return {str(key): item for key, item in source.items()}


class ProposedPolicyBearing(BaseModel):
    """One policy's bearing on a candidate, identified only by its position.

    There is no policy field. The request presents the corpus in a fixed order and the
    reply answers slot by slot, so the model never writes an identifier ArchCompass then
    has to trust (master plan 12.0).
    """

    model_config = ConfigDict(extra="forbid")

    bears_on: bool
    how: str = ""


class ProposedCandidateVerdict(BaseModel):
    """Model-facing judgement of one detected pattern.

    No candidate_id: the request carries exactly one candidate, so asking for it back
    would be asking the model to copy a value ArchCompass already holds.

    Field order is load-bearing. A structured-output model fills the schema in order, so
    `material` before `rationale` makes it commit to a verdict and then argue for it. A
    live run produced exactly that: `material=false` beside a rationale concluding
    "removing the interface simplifies the call path without losing any necessary
    structural benefit". The argument is written first here so the conclusion follows it.
    """

    model_config = ConfigDict(extra="forbid")

    rationale: str = Field(min_length=1)
    policy_bearings: list[ProposedPolicyBearing]
    material: bool
    recommended_response: str = ""


class ProposedOverviewStatement(BaseModel):
    """One claim about the whole review, grounded by position.

    `text` before `supported_by` so the claim is written first and the grounding describes
    what was actually said, rather than the model picking boundaries and then writing to fit
    them (master plan 12.0, field order).
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    supported_by: list[bool]


class ProposedReviewOverview(BaseModel):
    """Model-facing synthesis of every verdict in one review.

    No verdict field of any kind. This stage is shown conclusions and asked what they mean
    together; a `material` flag here would let a summary silently contradict the judgement
    that produced it, and there would be no way to tell which one a reader should believe.

    Field order is the reasoning: the situation the case describes, then what the verdicts
    show against it, then what to do about that, then what none of it could see.
    """

    model_config = ConfigDict(extra="forbid")

    situation: str = Field(min_length=1)
    themes: list[ProposedOverviewStatement] = Field(
        default_factory=list[ProposedOverviewStatement], max_length=4
    )
    recommended_sequence: list[ProposedOverviewStatement] = Field(
        default_factory=list[ProposedOverviewStatement], max_length=4
    )
    limits: str = Field(min_length=1)


class ProposedReviewAnswer(BaseModel):
    """Model-facing answer about a review, grounded by position.

    `answer` before `supported_by` so the prose is written first and the grounding
    describes what was actually said, rather than the model committing to a set of
    boundaries and then writing to fit them (master plan 12.0, field order).
    """

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    supported_by: list[bool]


class ChatTransport(Protocol):
    """One vendor's chat API, reduced to the single call this package needs.

    An implementation encodes the supplied messages and JSON Schema for its API, applies
    its own options and retry policy, and returns the response text. It decides nothing
    about content: the messages, the schema, and the budget check have already happened.

    Every failure it cannot complete must surface as `ProviderError`, so the stage logic
    above never handles a vendor's exception types.
    """

    #: How this provider is named in an error a user reads, e.g. "Ollama".
    provider_label: str

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        is_fast: bool,
        think: ThinkLevel,
        temperature: float | None,
    ) -> str: ...


class StructuredReasoningProvider:
    """Every reasoning stage, resolved against whichever transport is supplied."""

    _PROMPTS: ClassVar[dict[ReasoningTask, str]] = {
        task: contract.identity for task, contract in STAGE_PROMPTS.items()
    }

    #: Stages whose response is a short structured decision rather than a full artifact.
    #: Empty now: both remaining stages read a substantial input — the whole policy corpus
    #: for a verdict, the whole review for an answer — and produce considered prose, so
    #: neither belongs in the fast budget. The distinction is kept rather than deleted
    #: because it is a property of a stage, and the next one added may well be fast.
    _FAST_TASKS: ClassVar[frozenset[ReasoningTask]] = frozenset()

    def __init__(self, config: ReasoningModelConfig, transport: ChatTransport) -> None:
        self._config = config
        self._transport = transport

    @property
    def model_identity(self) -> str:
        return f"{self._config.provider}:{self._config.model}"

    def prompt_identity(self, task: ReasoningTask) -> str:
        return self._PROMPTS[task]

    def _think_for(self, requested: ThinkLevel) -> ThinkLevel:
        """The configured setting, unless a stage asked for a specific level.

        `None` means "no opinion" at both levels, and passing it on is what leaves the
        model to its own default — which is a third behaviour, not a synonym for off. A
        stage that names a level keeps it, because a stage asking for less reasoning than
        the model is capable of has a reason to.
        """

        return self._config.thinking if requested is None else requested

    def _timeout_for(self, task: ReasoningTask) -> float:
        """The timeout a stage runs under, which is its class's client timeout."""

        return timeout_seconds(self._config, is_fast=task in self._FAST_TASKS)

    def judge_finding_candidate(
        self,
        case: ArchitectureCase,
        candidate: FindingCandidate,
        policies: list[PolicyDocument],
    ) -> CandidateVerdict:
        expected = len(policies)
        proposed = self._complete(
            ReasoningTask.JUDGE_FINDING_CANDIDATE,
            {
                "case": case.model_dump(mode="json"),
                "candidate": candidate.model_dump(mode="json"),
                # Presented without IDs on purpose. An identifier in the input is an
                # identifier the model can quote back, and position is already a complete
                # and unforgeable binding.
                "policies": [
                    {
                        "position": index,
                        "title": policy.title,
                        "scope": policy.scope.value,
                        "strength": policy.strength.value,
                        "applies_to": policy.applies_to,
                        "body": policy.body,
                    }
                    for index, policy in enumerate(policies, start=1)
                ],
            },
            ProposedCandidateVerdict,
            runtime_instruction=(
                f"Return exactly {expected} policy_bearings entries, one for each supplied "
                "policy, in the order the policies appear above."
            ),
            schema_override=self._verdict_schema(policy_count=expected),
            # The schema fixes the arity and the repair round exists for the model that
            # ignores it. Position is the only thing tying a bearing to a policy, so a
            # short list would silently re-map every entry after the gap.
            candidate_validator=lambda item: (
                []
                if len(item.policy_bearings) == expected
                else [
                    f"policy_bearings must contain exactly {expected} entries, one per "
                    f"supplied policy in order, but contains {len(item.policy_bearings)}"
                ]
            ),
        )
        bearings = [
            PolicyBearing(policy_id=policy.id, policy_title=policy.title, how=item.how.strip())
            for policy, item in zip(policies, proposed.policy_bearings, strict=True)
            # A bearing asserted without saying how is not a bearing. Recording it as a
            # bare flag would put an unexplained policy name in a report, so it is dropped
            # rather than kept as something a reader cannot check.
            if item.bears_on and item.how.strip()
        ]
        return CandidateVerdict(
            candidate_id=candidate.candidate_id,
            material=proposed.material,
            rationale=proposed.rationale,
            policy_bearings=bearings,
            recommended_response=(
                proposed.recommended_response.strip() if proposed.material else ""
            ),
        )

    def summarise_review(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> ReviewOverview:
        expected = len(boundaries)
        proposed = self._complete(
            ReasoningTask.SUMMARISE_REVIEW,
            {
                "case": case.model_dump(mode="json"),
                # No reference codes, for the same reason policies are presented without
                # IDs: an identifier in the input is one the model can quote back, and
                # position is already a complete and unforgeable binding.
                "boundaries": [
                    {
                        "position": index,
                        "boundary": item.candidate.summary,
                        # Spelled out rather than passed as `material`. A live run grouped a
                        # boundary judged material among the ones "maintained for
                        # testability", which is what that word invites: read as ordinary
                        # English it says the boundary matters, and the verdict means the
                        # opposite. The settled verdict must not be re-readable.
                        "verdict": (
                            "NOT earning its place — this boundary should change"
                            if item.material
                            else "earning its place — this boundary should stay as it is"
                        ),
                        "reasoning": item.rationale,
                        "recommended_response": item.recommended_response,
                        "policies_that_bear": [
                            f"{bearing.policy_title}: {bearing.how}"
                            for bearing in item.policy_bearings
                        ],
                        # The detector's own statement of what it could not see. Without it
                        # a live run filled the overview's `limits` field with "<No limits
                        # provided in input>": the stage was asked to state the limits of a
                        # method it had never been told anything about.
                        "detection_limits": item.candidate.limitations,
                    }
                    for index, item in enumerate(boundaries, start=1)
                ],
            },
            ProposedReviewOverview,
            runtime_instruction=(
                f"Every statement must carry exactly {expected} supported_by flags, one for "
                "each boundary, in the order the boundaries appear above."
            ),
            schema_override=self._overview_schema(boundary_count=expected),
            candidate_validator=lambda item: [
                f"every supported_by must contain exactly {expected} flags, one per "
                f"boundary in order, but one statement contains {len(statement.supported_by)}"
                for statement in (*item.themes, *item.recommended_sequence)
                if len(statement.supported_by) != expected
            ],
        )
        return ReviewOverview(
            situation=proposed.situation.strip(),
            themes=_grounded_statements(proposed.themes, boundaries),
            recommended_sequence=_grounded_statements(
                proposed.recommended_sequence, boundaries
            ),
            limits=proposed.limits.strip(),
        )

    def answer_review_question(
        self,
        review: BoundaryReview,
        history: list[ReviewMessage],
        question: str,
    ) -> ReviewAnswer:
        report = review.report
        if report is None:
            raise ValueError("A review without a report cannot be questioned")
        boundaries = report.reviewed
        expected = len(boundaries)
        proposed = self._complete(
            ReasoningTask.ANSWER_REVIEW_QUESTION,
            {
                "case_title": report.case_title,
                "case": report.problem_and_desired_outcome,
                "overview": report.headline,
                # No reference codes. The model is shown the substance and answers by
                # position; codes exist for the reader, not for the model to quote back.
                "boundaries": [
                    {
                        "position": index,
                        "boundary": item.candidate.summary,
                        "verdict": "material" if item.material else "not material",
                        "reasoning": item.rationale,
                        "recommended_response": item.recommended_response,
                        "policies_that_bear": [
                            f"{bearing.policy_title}: {bearing.how}"
                            for bearing in item.policy_bearings
                        ],
                        "detection_limits": item.candidate.limitations,
                    }
                    for index, item in enumerate(boundaries, start=1)
                ],
                "earlier_questions": [
                    {
                        "question": message.question,
                        "answer": "" if message.answer is None else message.answer.answer,
                    }
                    for message in history
                ],
                "question": question,
            },
            ProposedReviewAnswer,
            runtime_instruction=(
                f"Return exactly {expected} supported_by values, one for each boundary, in "
                "the order the boundaries appear above."
            ),
            schema_override=self._review_answer_schema(boundary_count=expected),
            candidate_validator=lambda item: (
                []
                if len(item.supported_by) == expected
                else [
                    f"supported_by must contain exactly {expected} values, one per boundary "
                    f"in order, but contains {len(item.supported_by)}"
                ]
            ),
        )
        return ReviewAnswer(
            answer=proposed.answer,
            supporting_references=[
                item.reference
                for item, supports in zip(boundaries, proposed.supported_by, strict=True)
                if supports
            ],
        )



    @staticmethod
    def _overview_schema(*, boundary_count: int) -> dict[str, object]:
        """Fix one grounding flag per boundary inside every statement.

        The statement shape is a single definition shared by both lists, so bounding it once
        bounds every statement in the reply. Same binding as everywhere else: nothing in a
        flag says which boundary it belongs to, so a short list shifts every later flag onto
        the wrong boundary and still validates.
        """

        schema = ProposedReviewOverview.model_json_schema()
        definitions = _object_mapping(schema.get("$defs"))
        if definitions is None:
            return schema
        statement = _object_mapping(definitions.get("ProposedOverviewStatement"))
        if statement is None:
            return schema
        properties = _object_mapping(statement.get("properties"))
        if properties is None:
            return schema
        supported = _object_mapping(properties.get("supported_by"))
        if supported is None:
            return schema
        supported["minItems"] = boundary_count
        supported["maxItems"] = boundary_count
        properties["supported_by"] = supported
        statement["properties"] = properties
        definitions["ProposedOverviewStatement"] = statement
        schema["$defs"] = definitions
        return schema

    @staticmethod
    def _review_answer_schema(*, boundary_count: int) -> dict[str, object]:
        """Fix one grounding flag per boundary, in the order they were presented.

        Same binding as the verdict schema: nothing in the reply says which boundary a
        flag belongs to, so a short list silently shifts every later flag onto the wrong
        boundary and still validates.
        """

        schema = ProposedReviewAnswer.model_json_schema()
        properties = _object_mapping(schema.get("properties"))
        if properties is None:
            return schema
        supported = _object_mapping(properties.get("supported_by"))
        if supported is None:
            return schema
        supported["minItems"] = boundary_count
        supported["maxItems"] = boundary_count
        properties["supported_by"] = supported
        schema["properties"] = properties
        return schema

    @staticmethod
    def _verdict_schema(*, policy_count: int) -> dict[str, object]:
        """Fix the reply to one bearing per presented policy, in the presented order.

        Arity is the whole binding. Nothing in the response says which policy an entry is
        about, so a list one entry short does not lose one answer — it shifts every answer
        after the gap onto the wrong policy, and the result still validates. Stating the
        bound in the grammar means the common case never gets that far.
        """

        schema = ProposedCandidateVerdict.model_json_schema()
        properties = _object_mapping(schema.get("properties"))
        if properties is None:
            return schema
        bearings = _object_mapping(properties.get("policy_bearings"))
        if bearings is None:
            return schema
        bearings["minItems"] = policy_count
        bearings["maxItems"] = policy_count
        properties["policy_bearings"] = bearings
        schema["properties"] = properties
        return schema


    def _complete(
        self,
        task: ReasoningTask,
        payload: BaseModel | Mapping[str, object],
        output_type: type[Item],
        *,
        runtime_instruction: str = "",
        schema_override: Mapping[str, object] | None = None,
        candidate_validator: Callable[[Item], list[str]] | None = None,
        candidate_error_factory: (Callable[[Item], ModelOutputValidationError] | None) = None,
        allow_repair: bool = True,
        think: ThinkLevel = None,
        temperature: float | None = None,
    ) -> Item:
        contract = STAGE_PROMPTS[task]
        label = self._transport.provider_label
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else dict(payload)
        instruction = contract.request
        if runtime_instruction:
            instruction = f"{instruction}\n\nRun-specific constraints:\n{runtime_instruction}"
        messages = [
            {
                "role": "system",
                "content": contract.system_prompt,
            },
            {
                "role": "user",
                "content": f"{instruction}\n\nInput:\n{canonical_json(data)}",
            },
        ]
        try:
            content = self._chat(
                output_type,
                messages,
                task=task,
                schema_override=schema_override,
                think=self._think_for(think),
                temperature=temperature,
            )
            try:
                candidate = output_type.model_validate_json(content)
            except ValidationError as first_error:
                validation_errors = str(first_error)
            else:
                candidate_errors = (
                    candidate_validator(candidate) if candidate_validator is not None else []
                )
                if not candidate_errors:
                    return candidate
                validation_errors = "; ".join(candidate_errors)
            if not allow_repair:
                raise ModelOutputValidationError(
                    f"{label} returned invalid structured output: {validation_errors}"
                )
            repair_messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "The previous JSON failed validation. Return the complete corrected "
                        "JSON object only, under the same schema. Do not omit valid content. "
                        f"Validation errors:\n{validation_errors}"
                    ),
                },
            ]
            repaired = self._chat(
                output_type,
                repair_messages,
                task=task,
                schema_override=schema_override,
                think=self._think_for(think),
                temperature=temperature,
            )
            try:
                candidate = output_type.model_validate_json(repaired)
            except ValidationError as final_error:
                raise ModelOutputValidationError(
                    f"{label} returned invalid structured output after one repair pass: "
                    f"{final_error}"
                ) from final_error
            candidate_errors = (
                candidate_validator(candidate) if candidate_validator is not None else []
            )
            if candidate_errors:
                if candidate_error_factory is not None:
                    raise candidate_error_factory(candidate)
                raise ModelOutputValidationError(
                    f"{label} returned invalid structured output after one repair pass: "
                    + "; ".join(candidate_errors)
                )
            return candidate
        except (KeyError, TypeError, ValueError) as error:
            # A malformed response can still surface as one of these while it is mapped
            # back onto domain types. Transport failures are already `ProviderError`.
            raise ProviderError(f"{label} reasoning request failed: {error}") from error





    def _guard_prompt_budget(
        self,
        task: ReasoningTask,
        messages: list[ChatMessage],
        format_value: Mapping[str, object],
    ) -> None:
        """Refuse a request that cannot fit, rather than let it be truncated.

        The response schema is counted. Whether a provider spends prompt tokens on it or
        compiles it to a sampler grammar is a property of the build being talked to, and
        the fail-safe direction is to count it: over-counting refuses a borderline
        request with an explicit message, while under-counting reproduces exactly the
        silent front-truncation this exists to prevent.
        """

        prompt_characters = sum(
            len(message["role"]) + len(message["content"]) for message in messages
        )
        schema_characters = len(canonical_json(dict(format_value)))
        estimated_tokens = math.ceil(
            (prompt_characters + schema_characters) / self._config.chars_per_token
        )
        budget = self._config.context_window_tokens - self._config.max_output_tokens
        if estimated_tokens <= budget:
            return
        raise PromptBudgetExceededError(
            f"The {task.value} request does not fit the context window: "
            f"~{estimated_tokens} estimated prompt tokens "
            f"({prompt_characters} prompt characters plus {schema_characters} schema "
            f"characters at {self._config.chars_per_token} characters per token) "
            f"exceed the {budget} tokens left by a "
            f"{self._config.context_window_tokens}-token window reserving "
            f"{self._config.max_output_tokens} for output."
        )

    def _chat(
        self,
        output_type: type[Item],
        messages: list[ChatMessage],
        *,
        task: ReasoningTask,
        schema_override: Mapping[str, object] | None = None,
        think: ThinkLevel = None,
        temperature: float | None = None,
    ) -> str:
        # The schema is the full JSON Schema, not a generic "return JSON" flag: that
        # constrains generation to the exact shape rather than merely to valid JSON,
        # which is what makes enumerated handles and dispositions unrepresentable.
        resolved_schema: Mapping[str, object] = (
            schema_override if schema_override is not None else output_type.model_json_schema()
        )
        self._guard_prompt_budget(task, messages, resolved_schema)
        return self._transport.complete(
            messages,
            schema=resolved_schema,
            task=task,
            is_fast=task in self._FAST_TASKS,
            think=think,
            temperature=temperature,
        )
