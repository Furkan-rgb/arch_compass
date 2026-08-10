"""What a reply may look like, and what the application does with one before it counts.

Every `Proposed*` shape a stage constrains generation to, the three builders that pin a
reply's grounding flags to one per boundary or one per policy, and the handful of functions
that turn a validated reply into domain objects — attaching references from positions,
discarding what rests on nothing, tidying the prose a model writes unevenly.

Field order in these models is load-bearing throughout: a structured decoder fills a schema
in order, so a shape that puts its conclusion before its argument is a shape that samples
the conclusion first. Each model says so where it matters.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from archcompass.domain.case import CaseField
from archcompass.domain.review import (
    OpenQuestion,
    OverviewStatement,
    ReviewedBoundary,
    VerdictHinge,
)


def grounded_statements(
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


def tidied_options(proposed: list[str]) -> list[str]:
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


def grounded_questions(
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
                answer_options=tidied_options(item.answer_options),
                answer_belongs_in=item.answer_belongs_in,
                supporting_references=references,
            )
        )
    return questions


def verdict_hinge(proposed: ProposedVerdictHinge) -> VerdictHinge | None:
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


def prose_defects(field: str, value: str) -> list[str]:
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
    """One node of a generated JSON Schema as a plain dict, or nothing if it is not one.

    The schema builders below walk an untyped document, and every step of that walk has to
    ask the same question. Answering it once, and returning `None` rather than raising, is
    what lets each of them give up on a shape they did not expect and hand back the schema
    unchanged instead of failing a review over it.
    """

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
    which `verdict_hinge` discards.
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


def grounded_schema(
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

def review_answer_schema(
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

def verdict_schema(*, policy_count: int) -> dict[str, object]:
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
