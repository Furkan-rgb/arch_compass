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

import json
import math
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol, TypeVar, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from archcompass.adapters.models.prompt_contracts import STAGE_PROMPTS
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.base import canonical_json
from archcompass.domain.case import ArchitectureCase, CaseField
from archcompass.domain.errors import (
    ModelOutputValidationError,
    PromptBudgetExceededError,
    ProviderError,
)
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import (
    AnsweredQuestion,
    BoundaryExcerpt,
    BoundaryReview,
    CandidateVerdict,
    OpenQuestion,
    OverviewStatement,
    PolicyBearing,
    ReviewedBoundary,
    ReviewEvidence,
    ReviewOverview,
    VerdictHinge,
)
from archcompass.domain.review_conversation import ReviewAnswer, ReviewMessage
from archcompass.ports.reasoning import ReasoningTask, StreamingAnswerReasoner

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


def _grounded_questions(
    proposed: list[ProposedOpenQuestion],
    boundaries: list[ReviewedBoundary],
) -> list[OpenQuestion]:
    """Attach references from positions, drop what rests on nothing, and number what is left.

    `Q-n` is assigned here — after validation, in presentation order, by the application —
    for the same reason `BR-nnn` is: a reader will cite it, so it cannot be a value a model
    wrote (12.0). Numbering after the drop rather than before is what keeps the sequence
    gapless; a reader seeing Q-1 and Q-3 would reasonably ask what happened to the one in
    between, and the honest answer is that it was never a question.

    A question grounded on no boundary is discarded rather than kept, exactly as an
    ungrounded theme is. It is not a question about this repository at all: every real one
    traces to a verdict that admitted it turned on something.
    """

    questions: list[OpenQuestion] = []
    for item in proposed:
        references = [
            boundary.reference
            for boundary, supports in zip(boundaries, item.supported_by, strict=True)
            if supports
        ]
        if not references:
            continue
        questions.append(
            OpenQuestion(
                reference=f"Q-{len(questions) + 1}",
                what_the_review_saw=item.what_the_review_saw.strip(),
                unknown=item.unknown.strip(),
                why_it_matters=item.why_it_matters.strip(),
                question=item.question.strip(),
                answer_belongs_in=item.answer_belongs_in,
                supporting_references=references,
            )
        )
    return questions


def _hinge(proposed: ProposedVerdictHinge) -> VerdictHinge | None:
    """The declaration becomes an absence here, and nowhere else.

    One line of translation, like `material` beside it: the model says which of two things
    is true, and the domain carries `None` for the ordinary one. Nothing downstream reads a
    word, and nothing upstream infers a fact from a blank field.

    A hinge that declares itself and then says nothing is dropped rather than recorded or
    raised. The schema cannot prevent it — the three prose fields must stay optional for a
    verdict that stands either way, so nothing in the grammar stops a reply setting the word
    and leaving them blank, and a live run against `gemma4:26b` did exactly that on the
    fourth of eight boundaries.

    Dropping is the same treatment a policy bearing asserted without saying how already
    receives, and for the same reason: an unexplained flag is not a claim a reader can
    check. Failing instead was worse than either honest answer. It discarded three correct
    verdicts that had each cost a model call, over an optional field, on a boundary whose
    rationale, bearings and verdict were all sound — and it did so at the one point in the
    reply where nothing binds by position, so nothing could be silently re-attributed. Arity
    still fails loudly, because a short list of bearings shifts every later answer onto the
    wrong policy; a blank hinge shifts nothing.
    """

    if proposed.dependence != "turns_on_this_unknown":
        return None
    unknown = proposed.unknown.strip()
    if_confirmed = proposed.if_confirmed.strip()
    if_denied = proposed.if_denied.strip()
    if not (unknown and if_confirmed and if_denied):
        return None
    return VerdictHinge(
        unknown=unknown,
        if_confirmed=if_confirmed,
        if_denied=if_denied,
    )


def _prose_defects(field: str, value: str) -> list[str]:
    """Reject a prose field answered with a serialised object or list.

    A string field constrains the grammar to a string and nothing more, so a model that
    reads the stage's arity note as applying to every field can satisfy the schema by
    writing structure *inside* the string. That is not hypothetical: a live summary returned
    `{"statement": "...", "supported_by": [true, ...]}` as the text of `situation`, and
    because a JSON document is a perfectly valid string it validated, persisted, and printed
    verbatim as the conclusion at the top of the review page.

    Both conditions are required before anything is rejected. A sentence never begins with a
    brace and also parses as JSON, and a check on the leading character alone would refuse
    prose that happens to open with a quotation or a bracketed aside. What this cannot catch
    — an object with prose trailing after it — stays uncaught deliberately: the cost of a
    false positive here is a failed review, and the shape actually observed is the whole
    reply as one document.
    """

    text = value.strip()
    if not text.startswith(("{", "[")):
        return []
    try:
        json.loads(text)
    except ValueError:
        return []
    return [
        f"{field} must be prose written for a reader, but contains a serialised JSON "
        "document. Write sentences; grounding flags belong only to the fields that declare "
        "them."
    ]


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


class ProposedVerdictHinge(BaseModel):
    """What the verdict assumed because the case did not say it (master plan 6C.2).

    Required on every verdict, and `dependence` is why. "This one turns on nothing" has to
    be something the model *says*, because the alternative — reading an omitted or empty
    field as "nothing was open" — cannot tell a verdict that genuinely stands either way
    from one where the stage simply did not consider the question. Those are opposite facts
    and elicitation is built on the difference.

    Field order is the reasoning, as everywhere else. Naming the unknown and writing out the
    verdict under each answer comes first; whether it *is* a hinge is then read off those two
    branches rather than declared up front and argued for. Two branches that say the same
    thing are a verdict that stands either way, and a model that has just written them out
    can see that as easily as a reader can.

    `dependence` is a word rather than a flag for the same reason `verdict` is one. A
    boolean here would be read for polarity at every call site, and the field it sits beside
    is the one place in this codebase where that has already gone wrong in production.
    """

    model_config = ConfigDict(extra="forbid")

    #: The circumstance the case does not state. Empty only where nothing was open.
    unknown: str = ""
    #: The verdict this boundary gets under each answer, written out rather than named.
    if_confirmed: str = ""
    if_denied: str = ""
    dependence: Literal["stands_either_way", "turns_on_this_unknown"]


class ProposedCandidateVerdict(BaseModel):
    """Model-facing judgement of one detected pattern.

    No candidate_id: the request carries exactly one candidate, so asking for it back
    would be asking the model to copy a value ArchCompass already holds.

    Field order is load-bearing. A structured-output model fills the schema in order, so
    the verdict before `rationale` makes it commit and then argue for what it committed to.
    A live run produced exactly that: a cleared verdict beside a rationale concluding
    "removing the interface simplifies the call path without losing any necessary
    structural benefit". The argument is written first here so the conclusion follows it.

    The verdict is a word rather than a flag, and the flag it replaced is why. `material`
    was a bare `bool`, so the schema constraining generation said only `{"type":
    "boolean"}` — nothing at the point of writing carried which way it pointed. Read as
    ordinary English "is this boundary material?" asks whether it matters, and a model that
    had just argued the boundary was justified answered yes; ArchCompass read the same
    `true` as "the finding is material", meaning there is a problem here. Three live runs
    recorded the inversion, each unmistakable — one wrote "Retain the abstraction as it
    fulfills a mandatory technical constraint" into `recommended_response`, a field that
    exists only to say what to do about a problem, beside a flag saying the boundary should
    be removed. The report, the summary and every conversation about them inherited it.

    That trap was already documented three times in this codebase, at `_answer`, at the
    summary stage and in `BoundaryReviewReport.headline` — each time by spelling the verdict
    out in English before showing it to a model or a reader. All three are consumers. This
    is the producer, and it is the one place where being wrong cannot be recovered from.

    A boolean named anything still has to be read for polarity. A word is the conclusion.
    """

    model_config = ConfigDict(extra="forbid")

    rationale: str = Field(min_length=1)
    policy_bearings: list[ProposedPolicyBearing]
    #: Before the verdict, because a hinge is part of the argument: an argument states what
    #: it rests on before the conclusion that rests on it (6C.2). Placed after the bearings
    #: so the policies have been weighed before the stage says what it still lacked.
    hinge: ProposedVerdictHinge
    #: Neutral across all three patterns on purpose. Each names a different problem —
    #: indirection to remove, a fact needing one owner, knowledge to move back behind its
    #: boundary — and every one of them is a change, so this pair needs no per-pattern
    #: vocabulary and cannot drift out of step with one.
    verdict: Literal["leave_as_is", "should_change"]
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


class ProposedOpenQuestion(BaseModel):
    """One question the case would have to answer, grounded by position (6C.2).

    Composed here rather than beside each verdict because this is the only stage that can
    see the whole set, and merging is the entire point: four boundaries turning on the same
    unknown are one question citing four boundaries. Asked four times it is noise; asked
    once it is the most useful sentence in the report.

    Field order follows 6C.2 — what was seen, then the unknown it leaves, then which
    verdicts move and how, then the question a person can actually answer, and only then
    where the answer belongs. The destination is last because it is a routing decision about
    a question that must already exist, and it is an enumeration because the model picks a
    slot rather than naming a field (12.0).

    `what_the_review_saw` leads because it is the only field written from evidence rather
    than from the question, and putting it after would make it a justification composed to
    fit a question already asked.
    """

    model_config = ConfigDict(extra="forbid")

    what_the_review_saw: str = Field(min_length=1)
    unknown: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    #: Grounding sits with the claim it grounds: `why_it_matters` says which verdicts move,
    #: and these flags are that same statement in the form the application can resolve.
    supported_by: list[bool]
    question: str = Field(min_length=1)
    answer_belongs_in: CaseField


class ProposedElicitation(BaseModel):
    """Everything the first pass asks for, and nothing else.

    One field, which is the point. This shape was previously the tail of
    `ProposedReviewOverview`, where the stage producing it was also composing a conclusion —
    and on a first pass, whose case usually says nothing at all, that conclusion was drawn
    from silence and then discarded by the second pass. Asking is the whole of this call.

    A wrapper object rather than a bare array because a JSON Schema for structured output
    has to name a root object, and because the field's name is part of what the model is
    told it is doing.
    """

    model_config = ConfigDict(extra="forbid")

    #: No `max_length`. The bound is structural — every question must trace to a hinge, and
    #: hinges exist only where a verdict admitted contingency — so a numeric cap here would
    #: encode an opinion about how much uncertainty a review is allowed to admit, which is
    #: 8A.4's rule applied to questions (6C.5).
    open_questions: list[ProposedOpenQuestion] = Field(
        default_factory=list[ProposedOpenQuestion]
    )


class ProposedReviewOverview(BaseModel):
    """Model-facing synthesis of every verdict in one review.

    No verdict field of any kind. This stage is shown conclusions and asked what they mean
    together; a `material` flag here would let a summary silently contradict the judgement
    that produced it, and there would be no way to tell which one a reader should believe.

    No question field either, and its absence is load-bearing. Questions are asked by the
    first pass, before any conclusion exists; this stage runs only on the second, against a
    case the reader has just answered. A reply that could open a fresh round would leave the
    flow with no way to terminate, and removing the field enforces that in the grammar rather
    than in prose a model may or may not follow.

    Field order is the reasoning: the situation the case describes, then what the verdicts
    show against it, then what to do about that, and last what none of it could see.
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


class ProposedQuestionDiscussion(BaseModel):
    """Model-facing reply while a review is still waiting on the reader (§6C.7).

    `ProposedReviewAnswer` plus one field, and the fact that it is a separate shape rather
    than an optional tail of that one is what keeps the two stages apart. A conversation
    about a concluded review has no `suggested_answer` in its schema, so it cannot propose
    a case entry however it is prompted — the same grammatical enforcement that stops
    `summarise_review` reopening the elicitation loop (§6C.6).

    `suggested_answer` is last, after the prose and after the grounding, because it is a
    distillation of a conversation that has to have happened first. A model that writes it
    before reasoning is proposing an answer and then justifying it, which is the failure
    §6C.5 names as self-answering.
    """

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    supported_by: list[bool]
    #: Empty far more often than not, and no `min_length` for that reason. It is a phrasing
    #: of something the reader has said, so before they have said anything there is nothing
    #: honest to put here.
    suggested_answer: str = ""


@dataclass(frozen=True)
class ProsePreview:
    """Which string field to report as it is generated, and where to send it.

    A preview is a preview. Nothing sent to `emit` is stored, validated, or bound to
    anything: the reply that counts is the one this stage validates whole, after generation
    finishes, exactly as it would have without a preview. What the reader gains is the
    prose arriving as it is written rather than after the last token.

    Only a field the schema puts first can be previewed usefully, which is why
    `ProposedReviewAnswer` declares `answer` before `supported_by` — a reason it already had
    (master plan 12.0, field order) and now also depends on.
    """

    #: The name of the string property to decode a prefix of, as it appears in the schema.
    field: str
    #: Called with each new fragment of that field, never with text already sent.
    emit: Callable[[str], None]


def prose_prefix(field: str, partial: str) -> str:
    """Decode as much of one string field as has arrived in an incomplete JSON document.

    A streamed structured reply is not JSON until its last token, so nothing can parse it
    while it is growing. What can be done is narrower: find the field, then hand the bytes
    that have arrived to the real JSON decoder by closing the string. That keeps escape
    handling — `\\n`, `\\"`, `\\uXXXX` — in the decoder rather than reimplementing it here,
    where a subtly different reading would show the reader text the model did not write.

    Returns "" until the field's opening quote has arrived, and a growing prefix after that.
    The result never shrinks: an incomplete trailing escape is dropped and returns with the
    chunk that completes it, so a caller may treat the difference as the new fragment.
    """

    marker = f'"{field}"'
    key = partial.find(marker)
    if key < 0:
        return ""
    cursor = key + len(marker)
    # Only a colon and whitespace may sit between the key and its value. Anything else means
    # this is not the string property it names — a substring of some other field's text, or a
    # non-string value — and guessing would print the wrong thing.
    separator = partial[cursor:]
    stripped = separator.lstrip()
    if not stripped.startswith(":"):
        return ""
    value = stripped[1:].lstrip()
    if not value.startswith('"'):
        return ""
    body = value[1:]
    escaped = False
    for offset, character in enumerate(body):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"':
            body = body[:offset]
            break
    # Trim back over an escape the stream has not finished sending. `\uXXXX` is the longest,
    # so five characters is the whole search space; a still-unparseable tail is text this
    # cannot read and is reported as nothing rather than as a guess.
    for trim in range(6):
        candidate = body[: len(body) - trim] if trim else body
        try:
            decoded = json.loads(f'"{candidate}"')
        except ValueError:
            continue
        return decoded if isinstance(decoded, str) else ""
    return ""


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


@runtime_checkable
class StreamingChatTransport(Protocol):
    """A transport that can also report one reply's text as it is generated.

    Separate from `ChatTransport` and checked with `isinstance`, because streaming a
    schema-constrained reply is a property of a vendor's API rather than of this package: a
    transport that cannot do it omits the method and every stage still works, answering after
    the last token instead of during. Adding `stream` to `ChatTransport` would instead make
    every transport claim a capability and raise when asked to use it.

    That check is by name only. `runtime_checkable` compares which methods exist and nothing
    about their signatures, and a transport is held here as a `ChatTransport`, which says
    nothing about streaming — so a drifted `stream` would pass `isinstance` and fail on the
    call with nothing before it noticing. Every transport that streams therefore states its
    conformance to this protocol where it is defined.

    `stream` yields the same text `complete` would have returned, in order and in fragments
    of whatever size the vendor sends. Concatenated, the fragments are the whole reply and
    are validated as one — a stream changes when text arrives, never what is checked.

    A transient failure is retried only while nothing has been yielded. Once a fragment has
    been reported, a retry would replay text the reader has already seen, so a failure after
    that point is final and surfaces as `ProviderError` like any other.
    """

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        is_fast: bool,
        think: ThinkLevel,
        temperature: float | None,
    ) -> Iterator[str]: ...


def _accumulated(chunks: Iterable[str], preview: ProsePreview) -> str:
    """Join a streamed reply, reporting each new fragment of the previewed field.

    The decoded prefix only ever grows, so the difference in length is the fragment that
    just arrived. Emitting the difference rather than the whole prefix each time keeps this
    usable by a caller that appends — a wire protocol, a text node — without asking it to
    diff two strings.
    """

    content = ""
    reported = ""
    for chunk in chunks:
        content += chunk
        prose = prose_prefix(preview.field, content)
        if len(prose) > len(reported):
            preview.emit(prose[len(reported) :])
            reported = prose
    return content


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
        # The word becomes the domain's flag here and nowhere else. `material` keeps its
        # name in the domain, where it is read by code rather than written by a model, and
        # this single line is the whole of the translation.
        material = proposed.verdict == "should_change"
        return CandidateVerdict(
            candidate_id=candidate.candidate_id,
            material=material,
            rationale=proposed.rationale,
            policy_bearings=bearings,
            hinge=_hinge(proposed.hinge),
            recommended_response=(proposed.recommended_response.strip() if material else ""),
        )

    def elicit_questions(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> list[OpenQuestion]:
        expected = len(boundaries)
        proposed = self._complete(
            ReasoningTask.ELICIT_QUESTIONS,
            {
                "case": case.model_dump(mode="json"),
                "boundaries": self._boundaries_for_reading(boundaries),
            },
            ProposedElicitation,
            runtime_instruction=(
                f"Every entry in open_questions must carry exactly {expected} supported_by "
                "flags, one for each boundary, in the order the boundaries appear above."
            ),
            schema_override=self._grounded_schema(
                ProposedElicitation, boundary_count=expected
            ),
            candidate_validator=lambda item: [
                f"every supported_by must contain exactly {expected} flags, one per "
                f"boundary in order, but one entry contains {len(question.supported_by)}"
                for question in item.open_questions
                if len(question.supported_by) != expected
            ],
        )
        return _grounded_questions(proposed.open_questions, boundaries)


    @staticmethod
    def _elicitation_round(
        elicitation: list[AnsweredQuestion],
        *,
        answers_were_recorded: bool,
    ) -> list[dict[str, object]] | str:
        """The round of questions and answers behind this pass, as the stage is shown it.

        Both halves in one place and in the order they were asked, because the reader who
        asks about them is asking about a round they walked, not about two records.

        The three outcomes are spelled out rather than left to an absent key. An unanswered
        question read as "not mentioned" is exactly the misreading this presentation exists
        to prevent: a verdict that still hinges usually hinges on the question its reader
        chose to skip, and that is a finding about the review rather than a gap in it.
        """

        if not elicitation:
            return (
                "This review asked nothing — it is a first pass, or the pass that asked has "
                "since been deleted."
            )
        return [
            {
                "what_the_review_saw": item.question.what_the_review_saw,
                "question": item.question.question,
                "why_it_matters": item.question.why_it_matters,
                "answer": (
                    item.answer
                    if item.answer
                    else (
                        "skipped — the reader chose not to answer this one"
                        if answers_were_recorded
                        else "not recorded — this case revision was edited by hand, so no "
                        "line in it is attributable to any one question"
                    )
                ),
            }
            for item in elicitation
        ]

    @staticmethod
    def _source_for(
        excerpts: list[BoundaryExcerpt],
        reference: str,
    ) -> list[dict[str, object]]:
        """The code recorded for one boundary, as the conversation stages are shown it.

        Attached to the boundary rather than listed separately, because "which lines belong
        to which finding" is exactly what a reader is asking when they ask to see the code,
        and a flat list would make the stage rebuild that mapping from paths.

        An excerpt that could not be read carries its reason in place of its text. Presented
        rather than dropped: "this repository has changed since the review ran" is the
        honest answer to "show me the code", and silently omitting it would leave the stage
        to conclude the review has no source at all — which is the failure this exists to
        fix.
        """

        return [
            {
                "where": (
                    f"{item.location.path}:{item.location.start_line}"
                    if item.location is not None
                    else "not recorded"
                ),
                "what_it_contributes": item.role,
                "code": item.text or None,
                "why_there_is_no_code": item.unavailable or None,
            }
            for item in excerpts
            if item.reference == reference
        ]

    @staticmethod
    def _boundaries_for_reading(
        boundaries: list[ReviewedBoundary],
    ) -> list[dict[str, object]]:
        """Every verdict as the two set-wide stages are shown it.

        One presentation, shared, because the two stages read the same set for two different
        purposes and a boundary described differently to each would make their answers
        incomparable — the questions one asks are about the verdicts the other reports.

        No reference codes, for the same reason policies are presented without IDs: an
        identifier in the input is one the model can quote back, and position is already a
        complete and unforgeable binding (12.0).
        """

        return [
            {
                "position": index,
                "boundary": item.candidate.summary,
                # Spelled out rather than passed as `material`. A live run grouped a
                # boundary judged material among the ones "maintained for testability",
                # which is what that word invites: read as ordinary English it says the
                # boundary matters, and the verdict means the opposite. The settled verdict
                # must not be re-readable.
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
                # The detector's own statement of what it could not see. Without it a live
                # run filled the overview's `limits` field with "<No limits provided in
                # input>": the stage was asked to state the limits of a method it had never
                # been told anything about.
                "detection_limits": item.candidate.limitations,
                # What the *case* did not say, which is the other half of what the verdict
                # rested on and the only half a user can fix. Neither stage can consolidate
                # hinges it was never shown, and a question composed without them would be
                # that stage's own uncertainty rather than the judgement's (6C.2).
                "verdict_turns_on": (
                    {
                        "unknown": item.hinge.unknown,
                        "if_confirmed": item.hinge.if_confirmed,
                        "if_denied": item.hinge.if_denied,
                    }
                    if item.hinge is not None
                    # Spelled out rather than omitted, for the reason the verdict is: an
                    # absent key is read as "not mentioned", and this is a positive finding —
                    # the judgement considered what it lacked and concluded the verdict holds
                    # regardless.
                    else "nothing — this verdict stands whichever way the "
                    "unanswered questions about this case fall"
                ),
            }
            for index, item in enumerate(boundaries, start=1)
        ]

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
                "boundaries": self._boundaries_for_reading(boundaries),
            },
            ProposedReviewOverview,
            runtime_instruction=(
                f"Every entry in themes and recommended_sequence must carry exactly "
                f"{expected} supported_by flags, one for each boundary, in the order the "
                "boundaries appear above. situation and limits are prose and carry no flags."
            ),
            schema_override=self._grounded_schema(
                ProposedReviewOverview, boundary_count=expected
            ),
            candidate_validator=lambda item: [
                *_prose_defects("situation", item.situation),
                *_prose_defects("limits", item.limits),
                *(
                    f"every supported_by must contain exactly {expected} flags, one per "
                    f"boundary in order, but one entry contains "
                    f"{len(statement.supported_by)}"
                    for statement in (*item.themes, *item.recommended_sequence)
                    if len(statement.supported_by) != expected
                ),
            ],
        )
        # No `open_questions`. This stage runs only on a second pass and its schema has no
        # field for one, which is what stops the elicitation loop from reopening itself.
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
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
    ) -> ReviewAnswer:
        return self._answer(review, evidence, history, question, knowledge, preview=None)

    def stream_review_answer(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
        on_prose: Callable[[str], None],
    ) -> ReviewAnswer:
        """The same answer, with its prose reported as it is written.

        One code path, one validation, one returned answer: the preview is handed to the same
        call `answer_review_question` makes. Where the transport cannot stream, or the reply
        needs the repair round, nothing is emitted and the answer simply arrives at the end —
        so a caller never has to ask which of two behaviours it got.
        """

        return self._answer(
            review,
            evidence,
            history,
            question,
            knowledge,
            preview=ProsePreview(field="answer", emit=on_prose),
        )

    def _answer(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
        *,
        preview: ProsePreview | None,
    ) -> ReviewAnswer:
        report = review.report
        if report is None:
            raise ValueError("A review without a report cannot be questioned")
        boundaries = report.reviewed
        expected = len(boundaries)
        # Where each conclusion entry came from, by position rather than by code. A
        # statement stores `BR-` references, which must never enter an input the model can
        # quote back (12.0) — but the positions behind them are ArchCompass's own key and
        # are already the vocabulary every boundary below is presented in.
        #
        # Without this, "tell me more about recommendation 3" can only be answered by
        # matching words against the boundary list, and a live conversation showed what
        # that costs: three turns sourced from the conclusion's own summary, one of them
        # saying so outright, while citing a boundary whose record was never opened.
        position_of = {item.reference: index for index, item in enumerate(boundaries, start=1)}

        def rests_on(statement: OverviewStatement) -> list[int]:
            return sorted(
                position_of[reference]
                for reference in statement.supporting_references
                if reference in position_of
            )

        proposed = self._complete(
            ReasoningTask.ANSWER_REVIEW_QUESTION,
            {
                "case_title": report.case_title,
                # The case whole, not the report's two-sentence restatement of its problem.
                # It is half of what every verdict here was reached from — the judging stage
                # weighed each boundary against these constraints, non-goals and expected
                # changes — so an explanation that could not see them was explaining a
                # conclusion from half its evidence.
                "case": evidence.case.model_dump(mode="json"),
                "counts": report.headline,
                # The round that produced this pass, both halves together. Asked "what were
                # the questions and answers again?", this stage said the review holds no such
                # record — true of the review it was shown and false of what the workspace
                # keeps: the questions are pinned in the first pass for ever, the answers on
                # the case revision this pass runs against.
                #
                # No `Q-n` and no `BR-nnn`, for the reason nothing else here carries one.
                # A reader names a question by what it asked.
                "elicitation_round": self._elicitation_round(
                    evidence.elicitation,
                    answers_were_recorded=evidence.answers_were_recorded,
                ),
                # The conclusion a reader has in front of them, so a question about it is
                # answerable. Composed from these same verdicts by an earlier call, which is
                # why the contract names it as the review's own reading rather than as
                # evidence — it adds no fact about the repository.
                #
                # Text only. Every statement knows which boundaries it rests on, and those
                # references are exactly what must not appear in an input the model can quote
                # back (12.0); the boundaries themselves are all below with their reasoning.
                "conclusion": {
                    "situation": report.overview.situation,
                    "themes": [
                        {"text": item.text, "rests_on_boundary_positions": rests_on(item)}
                        for item in report.overview.themes
                    ],
                    # Numbered as the reader sees them. The page renders this as an ordered
                    # list, so "recommendation 3" is the third entry here and nothing has to
                    # be inferred from the order of a bare array.
                    "recommended_sequence": [
                        {
                            "number": number,
                            "text": item.text,
                            "rests_on_boundary_positions": rests_on(item),
                        }
                        for number, item in enumerate(
                            report.overview.recommended_sequence, start=1
                        )
                    ],
                    "limits": report.overview.limits,
                },
                # Background about the method, carried under a name that says what it is
                # and is not. It has no positions and nothing binds to it: an answer's
                # grounding is boundaries alone, so nothing here can be cited back — which
                # is also why the policies keep their titles here, unlike in the judging
                # stage where the reply must bind to them by position instead.
                "background_how_archcompass_works": knowledge.method,
                "background_policy_corpus": [
                    {"title": policy.title, "text": policy.body}
                    for policy in knowledge.policies
                ],
                # No reference codes. The model is shown the substance and answers by
                # position; codes exist for the reader, not for the model to quote back.
                "boundaries": [
                    {
                        "position": index,
                        "boundary": item.candidate.summary,
                        # Which of the three detectors found this. The advice for the two
                        # directions of the catalogue points opposite ways, so a question
                        # about what a boundary even is depends on knowing which it is.
                        "pattern": item.candidate.pattern.value,
                        # Spelled out, for the same reason the summary stage spells it out:
                        # read as ordinary English "material" says the boundary matters,
                        # and the verdict means the opposite.
                        "verdict": (
                            "NOT earning its place — this boundary should change"
                            if item.material
                            else "earning its place — this boundary should stay as it is"
                        ),
                        "reasoning": item.rationale,
                        "recommended_response": item.recommended_response,
                        # The numbers the pattern was detected from — four modules stating a
                        # constant, two distinct values among them. Without them a question
                        # like "how many copies are there?" is answerable only from whatever
                        # the prose happens to have restated.
                        "measurements": [
                            {"name": measure.name, "value": measure.value, "unit": measure.unit}
                            for measure in item.candidate.measurements
                        ],
                        "policies_that_bear": [
                            f"{bearing.policy_title}: {bearing.how}"
                            for bearing in item.policy_bearings
                        ],
                        "detection_limits": item.candidate.limitations,
                        # The lines this boundary was measured from, read from the repository
                        # it pinned. Without them a reader asking to see the leak was told
                        # the review "does not include the specific lines" — true of what
                        # reached this stage, and false of what the record holds.
                        "source": self._source_for(evidence.excerpts, item.reference),
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
            candidate_validator=lambda item: [
                *_prose_defects("answer", item.answer),
                *(
                    [
                        f"supported_by must contain exactly {expected} values, one per "
                        f"boundary in order, but contains {len(item.supported_by)}"
                    ]
                    if len(item.supported_by) != expected
                    else []
                ),
            ],
            preview=preview,
        )
        return ReviewAnswer(
            answer=proposed.answer,
            supporting_references=[
                item.reference
                for item, supports in zip(boundaries, proposed.supported_by, strict=True)
                if supports
            ],
        )

    def discuss_open_question(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        question: OpenQuestion,
        history: list[ReviewMessage],
        asked: str,
        knowledge: MethodKnowledge,
    ) -> ReviewAnswer:
        return self._discuss(
            review, evidence, question, history, asked, knowledge, preview=None
        )

    def stream_open_question_discussion(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        question: OpenQuestion,
        history: list[ReviewMessage],
        asked: str,
        knowledge: MethodKnowledge,
        on_prose: Callable[[str], None],
    ) -> ReviewAnswer:
        return self._discuss(
            review,
            evidence,
            question,
            history,
            asked,
            knowledge,
            preview=ProsePreview(field="answer", emit=on_prose),
        )

    def _discuss(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        question: OpenQuestion,
        history: list[ReviewMessage],
        asked: str,
        knowledge: MethodKnowledge,
        *,
        preview: ProsePreview | None,
    ) -> ReviewAnswer:
        report = review.report
        if report is None:
            raise ValueError("A review without a report cannot be discussed")
        # The cited boundaries and no others, in the order the report stores them. This is
        # the whole of what makes the stage safe to run while a first pass is withholding
        # its verdicts: the ones not cited are not in the input, so there is no side door to
        # the held set (§6C.6). It is also the honest scope — these are the verdicts this
        # question would settle, and the rest have nothing to do with it.
        cited = set(question.supporting_references)
        boundaries = [item for item in report.reviewed if item.reference in cited]
        if not boundaries:
            raise ValueError(
                f"Question {question.reference} cites no boundary this review contains"
            )
        expected = len(boundaries)
        proposed = self._complete(
            ReasoningTask.DISCUSS_OPEN_QUESTION,
            {
                "case_title": report.case_title,
                # The case whole, and it matters most here. The reader is being asked to add
                # something to this document, so "what does it already say about that" is
                # among the first things they will ask.
                #
                # This is the revision the review pinned, which means it holds what was
                # written before this round — including answers from any earlier round — and
                # not the answers being typed right now. Those batch into one revision at the
                # end (§6C.4). So this stage cannot see a reply the reader is still free to
                # change or delete, which is correct: an answer is not an answer until they
                # save it.
                "case": evidence.case.model_dump(mode="json"),
                # No conclusion and no counts. A first pass has neither — its overview is
                # composed from known facts with the themes left empty — and a stage that
                # asked for them would be reading a summary of the set this reader has
                # deliberately not been shown.
                "the_question_being_discussed": {
                    "what_the_review_saw": question.what_the_review_saw,
                    "the_unknown": question.unknown,
                    "why_it_matters": question.why_it_matters,
                    "question_put_to_the_reader": question.question,
                    "where_their_answer_would_be_recorded": (
                        question.answer_belongs_in.value
                    ),
                },
                "background_how_archcompass_works": knowledge.method,
                "background_policy_corpus": [
                    {"title": policy.title, "text": policy.body}
                    for policy in knowledge.policies
                ],
                # Presented as the answering stage presents them, minus the reference codes
                # for the usual reason (12.0). The same fields, because a reader asking
                # "why does this boundary make you ask that" needs what that stage needed.
                "boundaries_this_question_would_settle": [
                    {
                        "position": index,
                        "boundary": item.candidate.summary,
                        "pattern": item.candidate.pattern.value,
                        "verdict": (
                            "NOT earning its place — this boundary should change"
                            if item.material
                            else "earning its place — this boundary should stay as it is"
                        ),
                        "reasoning": item.rationale,
                        "recommended_response": item.recommended_response,
                        "measurements": [
                            {"name": measure.name, "value": measure.value, "unit": measure.unit}
                            for measure in item.candidate.measurements
                        ],
                        "policies_that_bear": [
                            f"{bearing.policy_title}: {bearing.how}"
                            for bearing in item.policy_bearings
                        ],
                        "detection_limits": item.candidate.limitations,
                        "source": self._source_for(evidence.excerpts, item.reference),
                        # What this verdict said it turned on, which is why this boundary is
                        # cited at all. Without it the reader can be told the verdict but not
                        # what their answer would do to it.
                        "verdict_turns_on": (
                            None
                            if item.hinge is None
                            else {
                                "unknown": item.hinge.unknown,
                                "if_confirmed": item.hinge.if_confirmed,
                                "if_denied": item.hinge.if_denied,
                            }
                        ),
                    }
                    for index, item in enumerate(boundaries, start=1)
                ],
                "earlier_turns": [
                    {
                        "asked": message.question,
                        "replied": "" if message.answer is None else message.answer.answer,
                    }
                    for message in history
                ],
                "asked": asked,
            },
            ProposedQuestionDiscussion,
            runtime_instruction=(
                f"Return exactly {expected} supported_by values, one for each boundary, in "
                "the order the boundaries appear above."
            ),
            schema_override=self._review_answer_schema(
                ProposedQuestionDiscussion, boundary_count=expected
            ),
            candidate_validator=lambda item: [
                *_prose_defects("answer", item.answer),
                *(
                    [
                        f"supported_by must contain exactly {expected} values, one per "
                        f"boundary in order, but contains {len(item.supported_by)}"
                    ]
                    if len(item.supported_by) != expected
                    else []
                ),
            ],
            preview=preview,
        )
        return ReviewAnswer(
            answer=proposed.answer,
            supporting_references=[
                item.reference
                for item, supports in zip(boundaries, proposed.supported_by, strict=True)
                if supports
            ],
            suggested_answer=proposed.suggested_answer.strip(),
        )

    @staticmethod
    def _grounded_schema(
        model: type[BaseModel],
        *,
        boundary_count: int,
    ) -> dict[str, object]:
        """Fix one grounding flag per boundary inside every grounded shape a reply nests.

        Applied to every definition carrying `supported_by` rather than to a named list, so a
        shape added to one of these replies is bounded by having the field rather than by
        being remembered here. Same binding as everywhere else: nothing in a flag says which
        boundary it belongs to, so a short list shifts every later flag onto the wrong
        boundary and still validates.
        """

        schema = model.model_json_schema()
        definitions = _object_mapping(schema.get("$defs"))
        if definitions is None:
            return schema
        for name, definition in list(definitions.items()):
            grounded = _object_mapping(definition)
            if grounded is None:
                continue
            properties = _object_mapping(grounded.get("properties"))
            if properties is None:
                continue
            supported = _object_mapping(properties.get("supported_by"))
            if supported is None:
                continue
            supported["minItems"] = boundary_count
            supported["maxItems"] = boundary_count
            properties["supported_by"] = supported
            grounded["properties"] = properties
            definitions[name] = grounded
        schema["$defs"] = definitions
        return schema

    @staticmethod
    def _review_answer_schema(
        model: type[BaseModel] = ProposedReviewAnswer,
        *,
        boundary_count: int,
    ) -> dict[str, object]:
        """Fix one grounding flag per boundary, in the order they were presented.

        Same binding as the verdict schema: nothing in the reply says which boundary a
        flag belongs to, so a short list silently shifts every later flag onto the wrong
        boundary and still validates.

        Takes the shape rather than naming one, because the discussion stage grounds
        identically over a subset of the same boundaries. Two stages binding the same way
        should not be able to drift into binding differently.
        """

        schema = model.model_json_schema()
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
        preview: ProsePreview | None = None,
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
                preview=preview,
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
            # Deliberately not previewed. The repair round rewrites a reply that failed
            # validation, so streaming it would replace text a reader is part-way through
            # with a second version of the same answer, and there is no honest way to
            # narrate that in a stream of fragments. The repaired answer lands whole.
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
        preview: ProsePreview | None = None,
    ) -> str:
        # The schema is the full JSON Schema, not a generic "return JSON" flag: that
        # constrains generation to the exact shape rather than merely to valid JSON,
        # which is what makes enumerated handles and dispositions unrepresentable.
        resolved_schema: Mapping[str, object] = (
            schema_override if schema_override is not None else output_type.model_json_schema()
        )
        self._guard_prompt_budget(task, messages, resolved_schema)
        transport = self._transport
        # The budget guard runs first either way. A preview asked for by a stage whose
        # transport cannot stream is not an error and not worth reporting: the answer is the
        # same one, and the only difference is that no fragment arrives before it.
        if preview is not None and isinstance(transport, StreamingChatTransport):
            return _accumulated(
                transport.stream(
                    messages,
                    schema=resolved_schema,
                    task=task,
                    is_fast=task in self._FAST_TASKS,
                    think=think,
                    temperature=temperature,
                ),
                preview,
            )
        return transport.complete(
            messages,
            schema=resolved_schema,
            task=task,
            is_fast=task in self._FAST_TASKS,
            think=think,
            temperature=temperature,
        )


#: Conformance to the optional streaming capability, stated so the type checker verifies it.
#: The application reaches this class through `isinstance`, which compares method names and
#: not signatures, so without this a drifted `stream_review_answer` would be caught by
#: nothing until it failed on the call. The class object rather than an instance: this needs
#: a configured transport to build, and nothing here needs one to check the signature.
_conforms: type[StreamingAnswerReasoner] = StructuredReasoningProvider
