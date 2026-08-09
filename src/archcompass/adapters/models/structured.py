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
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import (
    Annotated,
    ClassVar,
    Literal,
    Protocol,
    TypeVar,
    cast,
    runtime_checkable,
)

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from archcompass.adapters.models.prompt_contracts import STAGE_PROMPTS
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.atlas_map import AtlasMap
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
    ReviewStatus,
    VerdictHinge,
)
from archcompass.domain.review_conversation import ReviewAnswer, ReviewMessage
from archcompass.ports.investigation import RecordedLookup, SourceInvestigator, ToolSpec
from archcompass.ports.reasoning import ReasoningTask, StreamingAnswerReasoner

Item = TypeVar("Item", bound=BaseModel)

#: One turn of the conversation sent to a model, in the role/content form every chat
#: API accepts. A transport reshapes it into whatever its own SDK wants.
ChatMessage = dict[str, str]

#: How many rounds of tool calling one investigation may take before the stage has to ask
#: with what it has. Six is enough for a search, two reads and a check, which is the shape
#: the three worthwhile lookups take; past that a stage is browsing, and the failure a cap
#: prevents is not expense but an investigation that never terminates in front of a reader
#: watching a review run. The cap is spent without a further model call: a turn the loop
#: would not act on is a request nobody reads.
MAX_INVESTIGATION_TURNS = 6

#: The ceiling on what a whole investigation may hand the asking stage, in characters across
#: every recorded result. The per-result clamp bounds one answer and the turn cap bounds the
#: conversation's length, but neither bounds their product: a model may put several calls in
#: one turn, and six turns of many clamped results could still swell the elicitation request
#: until the budget guard refuses it — failing a stage whose worst permitted outcome is to
#: ask the way it always asked. Findings gathered before the ceiling are kept and said to be
#: cut short; five clamped results fit under it, which is more than any investigation worth
#: reading has needed.
MAX_INVESTIGATION_CHARACTERS = 20_000

#: Reasoning-effort control: off, on, or an explicit level. Named after Ollama's
#: `think` parameter because that is where it was first needed; a transport whose
#: vendor spells it differently maps it.
ThinkLevel = bool | Literal["low", "medium", "high"] | None


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


def opening_capital(value: str) -> str:
    """The same text with its first character upper-cased, and nothing else touched.

    Models write a question's fields as sentence fragments about half the time — "is there a
    requirement for a second sink?" — because that is how the field reads in the contract that
    asks for it. It is a sentence by the time a reader sees it: under a heading, in a numbered
    step of a walk, and now in the case itself as the question half of a clarification. A
    lower-case opening there reads as an unfinished thought rather than as something being
    asked of them.

    Fixed here rather than by asking the model, because a rule about capitalisation is a rule a
    model will follow unevenly and a rule the application can simply apply. Fixed in the data
    rather than with `::first-letter`, because there are now four places these strings render —
    the questions surface, the rendered markdown report, the answered-history panel, and the
    case's own clarifications — and a CSS fix reaches only the ones that are HTML.

    **The first character only, and only where it is a lower-case letter.** Anything more
    aggressive damages what people actually write in these fields: title-casing would wreck a
    sentence, and lower-casing anything would turn `SQLite` into `sQLite` and `BUILT_IN_VOICES`
    into something that cannot be grepped for. A string opening on a digit, a quote or a
    backtick is left exactly as it is, because there is no first letter to raise and guessing
    at where the sentence really starts is how a fix like this begins mangling identifiers.
    """

    if not value or not value[0].islower():
        return value
    return value[0].upper() + value[1:]


def _offered_options(proposed: list[str]) -> list[str]:
    """Tidy an offered option set: collapse whitespace, drop blanks, drop repeats.

    Distinctness is the one constraint the response schema cannot state, so it is repaired
    here rather than refused. Nothing in this list binds by position — an option is a
    suggestion the reader may take or ignore, and no record ever names one — so dropping a
    repeat re-attributes nothing, which is why this is the same treatment a blank hinge gets
    rather than the loud failure a short list of flags gets. The cap and the per-option
    minimum stay in the grammar, where a breach is a real breach.
    """

    offered: list[str] = []
    for option in proposed:
        text = opening_capital(" ".join(option.split()))
        if text and text not in offered:
            offered.append(text)
    return offered


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

    It is also where the four prose fields, and any offered answer options, get their opening
    capital. This is already the one
    place a question is normalized and numbered, so the strip and the capital belong together:
    both are the application tidying text on its way into a record, and neither is a judgement
    a model should be asked to make. See `opening_capital` for why it does no more than that.
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
                what_the_review_saw=opening_capital(item.what_the_review_saw.strip()),
                unknown=opening_capital(item.unknown.strip()),
                why_it_matters=opening_capital(item.why_it_matters.strip()),
                question=opening_capital(item.question.strip()),
                answer_options=_offered_options(item.answer_options),
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

    Two hinges are dropped rather than recorded or raised, and both are a declaration the
    reply does not support.

    The first says nothing. The grammar requires all three prose fields now, so this needs a
    whitespace-only answer to reach — but it is reached, and a live `gemma4:26b` run left
    them blank on the fourth of eight boundaries back when the grammar allowed it.

    The second says the same thing twice. Two branches whose text is identical are the model
    stating that the verdict does not move, and a declaration beside them saying it does is
    contradicted by the reply it sits in. Only exact equality is read that way, deliberately:
    whether "leave as is" and "the boundary should stay" mean one verdict is a judgement
    about prose, and code that guessed at it would discard a real hinge on nearly every
    honestly-written pair. This is the half of "read those two back" that is decidable, and
    it is the shortest way to satisfy three required fields without answering them — the
    same string twice — so it is the door those fields open.

    Dropping is the same treatment a policy bearing asserted without saying how already
    receives, and for the same reason: an unexplained flag is not a claim a reader can
    check. Failing instead was worse than either honest answer. It discarded three correct
    verdicts that had each cost a model call, over one field, on a boundary whose rationale,
    bearings and verdict were all sound — and it did so at the one point in the reply where
    nothing binds by position, so nothing could be silently re-attributed. Arity still fails
    loudly, because a short list of bearings shifts every later answer onto the wrong policy;
    a blank hinge shifts nothing.
    """

    if proposed.dependence != "turns_on_this_unknown":
        return None
    unknown = proposed.unknown.strip()
    if_confirmed = proposed.if_confirmed.strip()
    if_denied = proposed.if_denied.strip()
    if not (unknown and if_confirmed and if_denied):
        return None
    if if_confirmed == if_denied:
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

    All four are required, and the three prose fields being optional was the whole bug.
    While they were, the shortest legal reply was the declaration on its own — and a
    structured decoder fills fields in order, so `dependence` was sampled with the reasoning
    that decides it nowhere in the context at all. Three of six hinges in one measured run
    came back `{"unknown": "", "if_confirmed": "", "if_denied": "", "dependence":
    "stands_either_way"}`, and a review of eight boundaries against `gemini-3.5-flash-lite`
    gave that answer eight times and so asked nothing.

    It only looked like it worked because every run until then had thinking on and did the
    reading somewhere this schema cannot see. Requiring the fields puts both branches in the
    context window before the word that summarises them is chosen, which is what field order
    meant here in the first place. A verdict with nothing open pays one sentence for it,
    which `_hinge` discards.
    """

    model_config = ConfigDict(extra="forbid")

    #: The circumstance the case does not state. Written on every verdict, including the
    #: ordinary ones, where it is the record of what was considered and discarded rather
    #: than a claim that anything is contingent.
    unknown: str = Field(min_length=1)
    #: The verdict this boundary gets under each answer, written out rather than named. The
    #: same text twice is a verdict that does not move, whatever `dependence` then says.
    if_confirmed: str = Field(min_length=1)
    if_denied: str = Field(min_length=1)
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
    #: After the question, because an option is one answer to a question that must already
    #: exist; written first, the question would be composed to fit the options.
    #:
    #: The cap and the per-option minimum are stated here rather than in the request, so a
    #: fifth option is ungrammatical rather than discouraged. What the grammar cannot state —
    #: whether the answers to *this* question enumerate at all — is what the request explains,
    #: and an empty list is the ordinary reply.
    answer_options: list[Annotated[str, StringConstraints(min_length=1)]] = Field(
        default_factory=list[str], max_length=4
    )
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
        think: ThinkLevel,
        temperature: float | None,
    ) -> Iterator[str]: ...


@dataclass(frozen=True)
class ToolCall:
    """One tool a model asked for, as it asked for it.

    The arguments are carried as they arrived rather than validated here. Whether they make
    sense is the investigator's question, and it answers it in text the model reads — a
    transport that refused a malformed call would turn a model's bad guess into a failed
    stage.
    """

    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class ToolExchange:
    """One turn of an investigation: what the model said, and what it wants looked up.

    An empty `calls` is the terminating answer and the only one — the model saying it has
    seen enough. There is no separate "done" signal, because a model that has to remember to
    send one will eventually forget, and a turn with neither text nor calls would then hang
    the loop rather than end it.
    """

    #: Assistant prose, often empty. A model with tools to call frequently calls them
    #: without saying anything first, and that is not a defect worth prompting away.
    text: str
    calls: tuple[ToolCall, ...]
    #: Whatever the transport that produced this turn needs handed back when the turn is
    #: replayed, in whatever shape that vendor's SDK holds it. Written and read only there:
    #: nothing above the transport boundary may look inside it, compare it, or store it, and
    #: the loop that carries it from here onto the replayed turn is a courier rather than a
    #: reader. `None` is the ordinary value — a vendor with nothing to hand back, a fake, a
    #: transport written before any of this existed — and every path stays correct for it.
    vendor_state: object | None = None


@dataclass(frozen=True)
class AssistantToolTurn:
    """The model's own turn, replayed to it, with the calls it made attached.

    Replayed rather than summarised: a vendor that receives tool results without the calls
    they answer has no way to pair them, and pairing is positional — result *n* answers call
    *n* of the turn before it.
    """

    text: str
    calls: tuple[ToolCall, ...]
    #: The `ToolExchange.vendor_state` this turn was built from, carried back down to the
    #: transport that wrote it. Gemini's 3-series is the reason it exists: it attaches a
    #: thought signature to a function call and expects that signature returned with the
    #: history, and a turn rebuilt from `text` and `calls` alone is a turn with the signature
    #: stripped off. Provider-neutral dataclasses are the wrong place to hold a vendor's
    #: private token, so this holds it without describing it — opaque here, meaningful only
    #: where it came from, and never persisted with the review.
    vendor_state: object | None = None


@dataclass(frozen=True)
class ToolResultTurn:
    """What one tool answered, on its way back to the model.

    `call_name` rather than a call id, because the pairing is by position and the name is
    there for the vendors whose wire format asks for one. Two calls of the same tool in one
    turn are therefore distinguished by their order and by nothing else, which is exactly
    how they were sent.
    """

    call_name: str
    content: str


#: One turn of an investigation, in either direction. A closed union rather than a widened
#: `ChatMessage`, because a tool result is not a role and a call is not text: encoding them
#: as prose would leave every transport parsing its own history back out of strings.
InvestigationMessage = ChatMessage | AssistantToolTurn | ToolResultTurn


@runtime_checkable
class ToolCallingChatTransport(Protocol):
    """A transport that can also let a model call tools before it answers.

    Separate from `ChatTransport` and checked with `isinstance`, exactly as streaming is: a
    vendor either has a function-calling API or does not, and a transport without one omits
    the method while every stage goes on working — asking from pinned evidence alone, which
    is what every stage did before this existed. Putting `complete_with_tools` on
    `ChatTransport` would instead make every transport claim the capability and raise when
    it was used.

    That check is by name only. `runtime_checkable` compares which methods exist and nothing
    about their signatures, and a transport is held as a `ChatTransport`, which says nothing
    about tools — so a drifted `complete_with_tools` would pass `isinstance` and fail on the
    call. Every transport that can do this therefore states its conformance to this protocol
    where it is defined.

    No response schema on these requests, deliberately. An investigation is unconstrained
    text plus tool calls; the strict-schema call that composes the questions is unchanged
    and happens afterwards, so nothing about what a stage may *return* is loosened by this.

    `require_call` asks the vendor to constrain the reply to a tool call, where the API has
    such a mode (Gemini spells it function-calling mode ANY). The loop sets it on the first
    turn only: a prompt alone proved too weak an instruction for a small model, which spent
    its permission not to look exactly as written — and a stage that looked at nothing
    cannot tell the asking stage what was checked. Every later turn is the model's own
    judgement, because a forced call on the last turn would be a loop that cannot end.
    """

    def complete_with_tools(
        self,
        messages: list[InvestigationMessage],
        *,
        tools: Sequence[ToolSpec],
        require_call: bool,
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> ToolExchange: ...


def _rendered_investigation(
    transcript: Sequence[RecordedLookup],
    closing: str,
    abandoned: str,
) -> str:
    """What was looked up and what came back, as one block of text for the next stage.

    Rendered from the record rather than from the conversation, so what the asking stage
    reads is what a reader of this review could be shown: the call as it was made, with its
    arguments in the codebase's one canonical form, and the answer underneath it. Nothing is
    summarised — a lookup that found nothing is printed saying so, because "checked and
    empty" and "never checked" are opposite facts about a question.

    Empty when nothing happened at all, which is the signal the caller reads: no key is
    added, and the stage is told nothing rather than told that an investigation found
    nothing.
    """

    blocks = [
        f"{item.tool}({canonical_json(dict(item.arguments))})\n{item.result}"
        for item in transcript
    ]
    if closing:
        blocks.append(closing)
    if abandoned:
        # Named where the findings are, not logged away from them. A stage shown two results
        # and no note would take them for the whole of what could be found, and ask its
        # questions as though the repository had been read.
        blocks.append(f"investigation abandoned: {abandoned}")
    return "\n\n".join(blocks)


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

    def __init__(self, config: ReasoningModelConfig, transport: ChatTransport) -> None:
        self._config = config
        self._transport = transport

    @property
    def model_identity(self) -> str:
        return f"{self._config.provider}:{self._config.model}"

    @property
    def concurrent_requests(self) -> int:
        """Read off the configuration, because that is where the provider's answer lands.

        The number came from the provider's descriptor and may have been overridden by the
        environment on its way here, and neither is this class's business — it reasons with
        whatever configuration it was handed, and this is one more field of it.
        """

        return self._config.concurrent_requests

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

    def judge_finding_candidate(
        self,
        case: ArchitectureCase,
        candidate: FindingCandidate,
        policies: list[PolicyDocument],
        excerpts: list[BoundaryExcerpt] | None = None,
    ) -> CandidateVerdict:
        expected = len(policies)
        proposed = self._complete(
            ReasoningTask.JUDGE_FINDING_CANDIDATE,
            {
                "case": case.model_dump(mode="json"),
                "candidate": candidate.model_dump(mode="json"),
                # The code at the candidate's own spans, when the application read it. The
                # key is absent rather than empty where it did not: an empty list is a
                # statement — "these lines were looked for and are not there" — and the
                # contract says what a missing key means, which is that structure is the
                # whole of the evidence here.
                **(
                    {"source_evidence": self._source_entries(excerpts)}
                    if excerpts
                    else {}
                ),
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

    def _investigate(
        self,
        task: ReasoningTask,
        payload_json: str,
        investigator: SourceInvestigator | None,
        *,
        # Whether the opening turn must produce a tool call. True for elicitation, which runs
        # once per review and proved it would skip looking when it was allowed to. False for
        # a conversation turn, which runs once per message and is usually about text already
        # in front of the stage: a forced lookup there spends a call answering a question
        # about the review's own words, and every such call is a result the reply has to
        # carry. The two stages differ in the one thing this flag names, so it is a flag
        # rather than two loops.
        force_first: bool = True,
        think: ThinkLevel = None,
    ) -> str:
        """Let the model look things up, and render what it looked at.

        Returns "" whenever there is nothing to render — no investigator, or a transport
        without the capability, or a model that decided immediately that it had nothing to
        check. That empty string is what keeps every provider behaving exactly as it did
        before this existed: the caller adds no key, and the request it sends is byte for
        byte the one it sent yesterday.

        What comes back is a rendering of the *transcript*, not of the conversation. The
        difference matters: the transcript is the record of what was asked of the repository
        and what it said, produced by the application, and it is the only part of this a
        later question can be traced to. The model's closing prose is appended after it
        because it is the one thing the record cannot hold — which of those findings it
        thought mattered — and it is appended rather than interleaved so it cannot be
        mistaken for a result.

        A `ProviderError` mid-investigation degrades to a note and does not propagate.
        Investigating is an improvement to a question, and losing an improvement must never
        cost the review that the question belongs to: the worst outcome allowed here is a
        stage that asks the way it asked before.
        """

        transport = self._transport
        if investigator is None or not isinstance(transport, ToolCallingChatTransport):
            return ""
        contract = STAGE_PROMPTS[task]
        messages: list[InvestigationMessage] = [
            {"role": "system", "content": contract.system_prompt},
            {"role": "user", "content": f"{contract.request}\n\nInput:\n{payload_json}"},
        ]
        closing = ""
        abandoned = ""
        for turn in range(MAX_INVESTIGATION_TURNS):
            try:
                exchange = transport.complete_with_tools(
                    messages,
                    tools=investigator.tools,
                    # Only the opening turn is ever constrained, and only where the stage
                    # asked for it. Where it did, the repository gets first refusal on every
                    # question and a first look is how that rule survives a model inclined
                    # to skip it; from the second turn on, stopping is a judgement the model
                    # must be free to make.
                    require_call=force_first and turn == 0,
                    task=task,
                    think=self._think_for(think),
                    temperature=None,
                )
            except ProviderError as error:
                abandoned = str(error)
                break
            if not exchange.calls:
                closing = exchange.text.strip()
                break
            messages.append(
                AssistantToolTurn(
                    text=exchange.text,
                    calls=exchange.calls,
                    # Carried across untouched. What is in it is the transport's business —
                    # a Gemini thought signature today — and the loop's only part in it is
                    # not losing it on the way from the reply to the replay.
                    vendor_state=exchange.vendor_state,
                )
            )
            # Every call is executed, including the ones after a failure, because a failure
            # is a result here — `call` never raises — and a model that asked three things
            # is owed three answers in the order it asked them.
            messages.extend(
                ToolResultTurn(
                    call_name=call.name,
                    content=investigator.call(call.name, call.arguments),
                )
                for call in exchange.calls
            )
            # Measured over the record rather than over the messages, because the record is
            # what the rendering below will hand the asking stage — and that stage's request
            # is the one the ceiling exists to keep inside its budget.
            if (
                sum(len(item.result) for item in investigator.transcript)
                >= MAX_INVESTIGATION_CHARACTERS
            ):
                abandoned = (
                    "its findings reached the size ceiling, so nothing further was looked up"
                )
                break
        # Told to the investigator before anything is rendered, and on every way out of the
        # loop above. The rendering is spent on the next request; the investigator is what
        # the run that built it still holds, so this is the only route these two sentences
        # have to a record anybody can read afterwards.
        investigator.conclude(closing, abandoned)
        return _rendered_investigation(investigator.transcript, closing, abandoned)

    def elicit_questions(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
        investigator: SourceInvestigator | None = None,
    ) -> list[OpenQuestion]:
        expected = len(boundaries)
        payload: dict[str, object] = {
            "case": case.model_dump(mode="json"),
            "boundaries": self._boundaries_for_reading(boundaries),
        }
        # Before the questions and from the same input, so the stage investigates the
        # verdicts it is about to ask about rather than a summary of them. The findings then
        # enter that input as one more key: everything below — the grounded schema, the arity
        # validator, the repair round — is untouched by whether anything was looked up.
        findings = self._investigate(
            ReasoningTask.INVESTIGATE_USAGE,
            canonical_json(payload),
            investigator,
        )
        if findings:
            payload["investigation"] = findings
        proposed = self._complete(
            ReasoningTask.ELICIT_QUESTIONS,
            payload,
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
    def _structure_for(candidate: FindingCandidate) -> dict[str, object]:
        """The detector's own record of what makes up this boundary, for both talking stages.

        The judging stage always had this — which elements participate and which edges run
        among them — and the stages a person actually talks to did not, so "what implements
        this?" was answerable only from whatever the prose happened to restate. Participants
        are named by qualified name and never by node id, for the reason nothing else
        carries an id (12.0); edges are joined back through the participants so they read
        as names too, and an endpoint the detector did not list among the participants is
        said to be outside them rather than leaked as a raw id.

        An empty edge list is stated as a fact about the detector, not about the code: only
        one of the three patterns records edges, and a stage told nothing would report that
        the elements are unrelated.
        """

        names = {item.node_id: item.qualified_name for item in candidate.participants}
        outside = "an element outside this boundary's participants"
        return {
            "participants": [
                {
                    "qualified_name": item.qualified_name,
                    "part_played": item.role,
                    "where": (
                        f"{item.location.path}:{item.location.start_line}"
                        if item.location is not None
                        else "not recorded"
                    ),
                }
                for item in candidate.participants
            ],
            "relationships": (
                [
                    (
                        f"{names.get(edge.source_id, outside)}"
                        f" —{edge.edge_type.value}→ "
                        f"{names.get(edge.target_id, outside)}"
                    )
                    for edge in candidate.relationships
                ]
                if candidate.relationships
                else (
                    "none recorded — the "
                    f"{candidate.pattern.value} detector does not record edges between "
                    "its participants, which says nothing about whether the code relates "
                    "them"
                )
            ),
        }

    @staticmethod
    def _excerpt_note(item: BoundaryExcerpt) -> str | None:
        """Both captions an excerpt can carry, as one sentence or two, or nothing.

        An excerpt can be a pinned copy of a repository that has moved on and be clipped
        short of its recorded span at the same time; each caveat changes what the stage may
        claim from the code, so neither may displace the other.
        """

        captions: list[str] = []
        if item.provenance:
            captions.append(item.provenance)
        if item.truncated_after_line is not None and item.location is not None:
            captions.append(
                f"Truncated: the recorded span runs to line {item.location.end_line}, "
                f"but only lines up to {item.truncated_after_line} are shown. Never "
                "claim the lines past that point say nothing."
            )
        return " ".join(captions) or None

    @staticmethod
    def _atlas_map_payload(atlas_map: AtlasMap | None) -> object:
        """The repository's structure at review time, or a statement of why it is absent.

        Omitted counts render as sentences rather than bare numbers, because a trimmed map
        must not read as a complete one: "3 modules omitted" is the difference between
        "that module does not exist" and "that module was folded away for space".
        """

        if atlas_map is None:
            return "not assembled for this stage"
        if atlas_map.unavailable:
            return f"unavailable: {atlas_map.unavailable}"
        return {
            "modules": [
                {
                    "module": module.path,
                    "declares": module.members,
                    **(
                        {
                            "declarations_omitted": (
                                f"{module.members_omitted} declarations omitted to fit "
                                "the budget — absence from this list is not absence from "
                                "the module"
                            )
                        }
                        if module.members_omitted
                        else {}
                    ),
                }
                for module in atlas_map.modules
            ],
            "module_relationships": [
                f"{item.source_module} depends on {item.target_module}: {item.kinds}"
                for item in atlas_map.relations
            ],
            **(
                {
                    "modules_omitted": (
                        f"{atlas_map.modules_omitted} modules omitted to fit the budget"
                    )
                }
                if atlas_map.modules_omitted
                else {}
            ),
            **(
                {
                    "relationships_omitted": (
                        f"{atlas_map.relations_omitted} module relationships omitted to "
                        "fit the budget"
                    )
                }
                if atlas_map.relations_omitted
                else {}
            ),
        }

    @staticmethod
    def _policy_corpus_payload(knowledge: MethodKnowledge) -> object:
        """The corpus as background, or the reason there is none.

        The reason is presented instead of an empty list because the two mean different
        things: an empty corpus is a workspace without policies, while an unreadable one is
        a failure the stage should repeat to a reader who asks about policies rather than
        answering as though none exist.
        """

        if knowledge.policy_corpus_unavailable:
            return f"unavailable: {knowledge.policy_corpus_unavailable}"
        return [
            {"title": policy.title, "text": policy.body}
            for policy in knowledge.policies
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

        return StructuredReasoningProvider._source_entries(
            [item for item in excerpts if item.reference == reference]
        )

    @staticmethod
    def _source_entries(excerpts: list[BoundaryExcerpt]) -> list[dict[str, object]]:
        """The same rendering, for excerpts already narrowed to one thing.

        Split out because judging is shown the code at one candidate's spans, and that
        candidate has no `BR-nnn` yet — references are assigned from position once the
        verdicts exist. One shape for both, so what a judging stage sees and what a
        conversation stage sees are the same four fields in the same order.
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
                # A caption about the text, when the text needs one — a pinned copy served
                # because the repository has moved on, or a span the excerpt ceiling cut
                # short. Carried beside the code rather than folded into it, so the stage
                # can repeat the caveat without mistaking it for a line of the file.
                "note": StructuredReasoningProvider._excerpt_note(item),
            }
            for item in excerpts
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
        #
        # The other half of that termination is a stage away, in the judging contract: a second
        # pass hinges again unless it can see that the reader already answered, and it sees
        # that in the case's `clarifications` — the questions and answers of the first round,
        # kept as pairs. This schema makes re-asking unrepresentable; that list is what makes
        # re-hinging unnecessary.
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
        investigator: SourceInvestigator | None = None,
    ) -> ReviewAnswer:
        return self._answer(
            review, evidence, history, question, knowledge, investigator, preview=None
        )

    def stream_review_answer(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
        investigator: SourceInvestigator | None,
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
            investigator,
            preview=ProsePreview(field="answer", emit=on_prose),
        )

    def _answer(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
        investigator: SourceInvestigator | None,
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

        payload: dict[str, object] = {
            "case_title": report.case_title,
            # The case whole, not the report's two-sentence restatement of its problem.
            # It is half of what every verdict here was reached from — the judging stage
            # weighed each boundary against these constraints, non-goals and expected
            # changes — so an explanation that could not see them was explaining a
            # conclusion from half its evidence.
            "case": evidence.case.model_dump(mode="json"),
            # The whole repository's structure as it was when the review ran — what
            # exists and what depends on what, with no verdicts and no code. It is how
            # a question about a module no detector flagged gets a structural answer
            # instead of "I was not shown that", and nothing in a reply may cite it:
            # grounding stays boundaries-only.
            "pinned_atlas_map": self._atlas_map_payload(evidence.atlas_map),
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
            "background_policy_corpus": self._policy_corpus_payload(knowledge),
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
                    # Which elements make this boundary up and which edges the detector
                    # recorded among them — what the judging stage had and this one
                    # lacked, so "what implements this?" no longer depends on the prose
                    # having restated it.
                    **self._structure_for(item.candidate),
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
        }
        # Before the answer and from the same input, so the stage looks at the review it
        # is about to speak about rather than at a summary of it. The findings then enter
        # that input as one more key, exactly as they do at elicitation: the grounded
        # schema, the arity validator, the repair round and the preview are all untouched
        # by whether anything was looked up.
        #
        # And it happens here, before `_complete` is entered, which is what keeps a
        # streamed reply a reply: the preview begins with the first fragment of the answer
        # itself, and no part of an investigation is ever shown on its way past.
        findings = self._investigate(
            ReasoningTask.INVESTIGATE_FOR_ANSWER,
            canonical_json(payload),
            investigator,
            force_first=False,
        )
        if findings:
            payload["investigation"] = findings
        proposed = self._complete(
            ReasoningTask.ANSWER_REVIEW_QUESTION,
            payload,
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
        investigator: SourceInvestigator | None = None,
    ) -> ReviewAnswer:
        return self._discuss(
            review, evidence, question, history, asked, knowledge, investigator, preview=None
        )

    def stream_open_question_discussion(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        question: OpenQuestion,
        history: list[ReviewMessage],
        asked: str,
        knowledge: MethodKnowledge,
        investigator: SourceInvestigator | None,
        on_prose: Callable[[str], None],
    ) -> ReviewAnswer:
        return self._discuss(
            review,
            evidence,
            question,
            history,
            asked,
            knowledge,
            investigator,
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
        investigator: SourceInvestigator | None,
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
        # The conclusion is shown only once the review has concluded. Mid-elicitation the
        # overview is composed from known facts with the themes left empty, and a stage
        # that read it would be reading a summary of the set this reader has deliberately
        # not been shown (§6C.6). But this stage also serves question-scoped conversations
        # about reviews that have since concluded, where the conclusion is on the reader's
        # page and "how does this fit the overall recommendation?" deserves a grounded
        # answer rather than a stage that has never seen the recommendation.
        #
        # Its groundings need care: the conclusion's statements rest on the whole reviewed
        # set while only the cited subset is numbered here, so a full-set position would
        # collide with this payload's own vocabulary. A boundary in the subset is named by
        # its position; one outside it is named by its summary — public on a concluded
        # review — and marked as not shown, so nothing invites citing it.
        concluded = review.status is ReviewStatus.SUCCEEDED
        position_in_subset = {
            item.reference: index for index, item in enumerate(boundaries, start=1)
        }
        summaries = {item.reference: item.candidate.summary for item in report.reviewed}

        def resting(statement: OverviewStatement) -> list[dict[str, object]]:
            return [
                (
                    {"position": position_in_subset[reference]}
                    if reference in position_in_subset
                    else {"boundary_not_shown_in_this_discussion": summaries[reference]}
                )
                for reference in statement.supporting_references
                if reference in summaries
            ]

        # A waiting review may have been carried on from: the loop concludes in a *new*
        # review, so the conclusion the reader has on their page lives on the successor the
        # application looked up, not on the review this thread pins. Shown from there, with
        # its groundings matched back onto the cited subset by boundary fingerprint — the
        # structural identity that survives a re-run — and by summary where an older review
        # carries no fingerprint.
        successor = evidence.concluded_by.report if evidence.concluded_by else None

        def resting_on_successor(statement: OverviewStatement) -> list[dict[str, object]]:
            assert successor is not None
            by_fingerprint = {
                item.fingerprint: index
                for index, item in enumerate(boundaries, start=1)
                if item.fingerprint
            }
            by_summary = {
                item.candidate.summary: index
                for index, item in enumerate(boundaries, start=1)
            }
            entries: list[dict[str, object]] = []
            for reference in statement.supporting_references:
                match = next(
                    (item for item in successor.reviewed if item.reference == reference),
                    None,
                )
                if match is None:
                    continue
                position = (
                    by_fingerprint.get(match.fingerprint) if match.fingerprint else None
                ) or by_summary.get(match.candidate.summary)
                entries.append(
                    {"position": position}
                    if position is not None
                    else {"boundary_not_shown_in_this_discussion": match.candidate.summary}
                )
            return entries

        def rendered(
            overview: ReviewOverview,
            grounding: Callable[[OverviewStatement], list[dict[str, object]]],
        ) -> dict[str, object]:
            return {
                "situation": overview.situation,
                "themes": [
                    {"text": item.text, "rests_on": grounding(item)}
                    for item in overview.themes
                ],
                "recommended_sequence": [
                    {"number": number, "text": item.text, "rests_on": grounding(item)}
                    for number, item in enumerate(overview.recommended_sequence, start=1)
                ],
                "limits": overview.limits,
            }

        conclusion: object
        if concluded:
            conclusion = rendered(report.overview, resting)
        elif successor is not None:
            conclusion = {
                # Said in the payload, not only in the contract: the verdicts above are
                # this round's, and the conclusion came from the pass that ran after the
                # reader's answers — a re-judged boundary may have moved between the two.
                "reached_by": (
                    "a later pass that ran after this round's answers were recorded; the "
                    "verdicts shown above are this round's own"
                ),
                **rendered(successor.overview, resting_on_successor),
            }
        else:
            # Spelled out rather than omitted, as every absence here is: an absent key
            # reads as "reviews have no conclusions", and this one has one on the way.
            conclusion = (
                "withheld — this review is still waiting on answers, so its conclusion "
                "and the verdicts outside this question are not settled enough to show"
            )
        payload: dict[str, object] = {
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
            # As the answering stage carries it: structure only, no verdicts, so it
            # widens nothing the cited-boundaries scope protects.
            "pinned_atlas_map": self._atlas_map_payload(evidence.atlas_map),
            **(
                {"counts": report.headline}
                if concluded
                else {"counts": successor.headline} if successor is not None else {}
            ),
            "conclusion": conclusion,
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
            "background_policy_corpus": self._policy_corpus_payload(knowledge),
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
                    # As the answering stage carries it, and for the same reason: the
                    # reader being asked to settle what relates these elements needs
                    # what the detector recorded about how they relate.
                    **self._structure_for(item.candidate),
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
        }
        # As in `_answer`, and under the same contract: the looking happens before the reply
        # is composed, from the input the reply will be composed from, and its findings enter
        # that input as one key. The scope this stage is under is a scope on the verdicts it
        # is shown and not on the repository it may read — see where the toolbox is built.
        findings = self._investigate(
            ReasoningTask.INVESTIGATE_FOR_ANSWER,
            canonical_json(payload),
            investigator,
            force_first=False,
        )
        if findings:
            payload["investigation"] = findings
        proposed = self._complete(
            ReasoningTask.DISCUSS_OPEN_QUESTION,
            payload,
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
                    think=think,
                    temperature=temperature,
                ),
                preview,
            )
        return transport.complete(
            messages,
            schema=resolved_schema,
            task=task,
            think=think,
            temperature=temperature,
        )


#: Conformance to the optional streaming capability, stated so the type checker verifies it.
#: The application reaches this class through `isinstance`, which compares method names and
#: not signatures, so without this a drifted `stream_review_answer` would be caught by
#: nothing until it failed on the call. The class object rather than an instance: this needs
#: a configured transport to build, and nothing here needs one to check the signature.
_conforms: type[StreamingAnswerReasoner] = StructuredReasoningProvider
