"""LangChain model boundary: Pydantic outside, frozen dataclasses inside."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any, Final, Literal, cast

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import Runnable
from openai import ContentFilterFinishReasonError, LengthFinishReasonError
from pydantic import BaseModel, Field, ValidationError, model_validator

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    CaseFacet,
    Evidence,
    Finding,
    Measurement,
    Policy,
    PolicyBearing,
    Question,
    RecordedInvestigation,
    Review,
    ReviewDelta,
    Termination,
    Verdict,
)
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.ports.capabilities import ReviewedSubject, ReviewSynopsis
from archcompass.ports.policy_retrieval import RetrievedPolicySet
from archcompass.reasoning.adapters.tool_loop import (
    investigate_with_tools,
    recorded_investigation,
)
from archcompass.reasoning.ports import (
    ConversationAnswer,
    ConversationMessage,
    InvestigatorSource,
)
from archcompass.reasoning.records import JUDGE_PROMPT_IDENTITY
from archcompass.retrying import call_with_retry

_log = logging.getLogger(__name__)


class PolicyBearingOutput(BaseModel):
    """One policy this verdict rests on, and what it had to do with the verdict."""

    # Naming over indexing, from the charter: a model may name something the application
    # holds and may never index into the application's list, because an ordinal that is
    # wrong but in range cites the wrong policy and nothing can tell.
    policy_id: str = Field(
        min_length=1,
        description=(
            "The identifier of a policy you were shown, copied exactly as it appears after "
            "'Policy ID:'. Never its position in the list, and never a policy you were not "
            "given."
        ),
    )
    reasoning: str = Field(
        min_length=1,
        description="How this particular policy bears on this candidate, in a sentence or two.",
    )


class FindingOutput(BaseModel):
    """One judgement of one detected structure: the verdict, why, and what it rests on.

    The fields carry their own meaning because this schema is what the model is handed, and
    an output rule stated only in the prompt is a rule the schema cannot enforce and the
    model may not still be reading by the time it answers. Two of these rules were learned
    the hard way — `verdict` was a boolean the application turned into three outcomes, and
    `policy_bearings` was optional — and both cost real judgements before they moved here.

    Deliberately says nothing about how to investigate. What a judgement may look at and
    when it must is the reasoning contract's business, not this record's.
    """

    verdict: Literal["material", "cleared", "held"] = Field(
        description=(
            "Exactly one, and the one your reasoning argues for. 'material': this structure "
            "costs more than it earns. 'cleared': it does not. 'held': your verdict turns on "
            "a fact you cannot get from the repository or the supplied case — what this team "
            "decided, committed to, or already accepted."
        )
    )
    reasoning: str = Field(
        min_length=1,
        description=(
            "Your architectural reasoning for this verdict: what the structure costs, what it "
            "earns, and which evidence decided it. Prose, and not a substitute for the "
            "citations below."
        ),
    )
    # At least one, because a bearing is the record of why a verdict was reached. It was
    # optional, and a local model left it empty on two thirds of its judgements while naming
    # the policy inside `reasoning` — the reasoning was right and the record of it was thrown
    # away, because prose naming a policy is not a citation and nothing asked for one.
    policy_bearings: list[PolicyBearingOutput] = Field(
        min_length=1,
        description=(
            "Every policy this verdict actually rests on, by identifier. At least one, for "
            "all three verdicts: clearing a structure is a judgement against a policy just as "
            "finding it material is, and a held verdict turns on the policy whose exception "
            "you could not settle. Naming a policy in `reasoning` is not a citation."
        ),
    )
    hinge: str | None = Field(
        default=None,
        description=(
            "Required when the verdict is 'held' and forbidden otherwise. The single fact "
            "your verdict turns on, stated as one concise question for a person. It stops the "
            "review and interrupts someone, so it must be worth that: not something the "
            "supplied evidence already settles, and never a way to avoid committing."
        ),
    )
    recommended_response: str | None = Field(
        default=None,
        description=(
            "What to do about it, and only where the verdict is 'material'. A cleared finding "
            "has nothing to recommend and a held one is still waiting on an answer."
        ),
    )

    @model_validator(mode="after")
    def the_verdict_carries_what_it_is_allowed_to(self) -> FindingOutput:
        if self.verdict == "held" and not (self.hinge or "").strip():
            raise ValueError("a held finding must name the fact its verdict turns on")
        if self.verdict != "held" and (self.hinge or "").strip():
            raise ValueError("a finding that reached a verdict has nothing left to ask")
        if self.verdict != "material" and self.recommended_response:
            raise ValueError("only a material finding may recommend a response")
        return self


class QuestionOutput(BaseModel):
    """The question one held finding needs answered. It never says which finding.

    It used to. A single call saw every finding under a number and returned the numbers its
    questions covered — including, on occasion, the number of a finding that had no hinge,
    an entry the prompt listed and then forbade in prose. That raised, and the raise lost a
    whole review after every candidate had already been judged.

    The finding is now the one this call was made about, so the mapping is the application's
    and there is no number for a model to get wrong.
    """

    text: str = Field(min_length=1)
    facet: Literal[
        "goal", "constraint", "decision", "assumption", "expected_change", "non_goal"
    ]
    # Answers the model thinks likely, so the common case is a click rather than an essay.
    #
    # Required now, where it used to be optional "when the honest answers are too open to
    # enumerate". That reasoning had the escape hatch in the wrong place: the interface
    # always offers writing your own and skipping outright, structurally, under every
    # question — so a menu is never a closed set and never needs the model to leave room for
    # one. Optional in the schema meant an empty list in practice, and an empty list is a
    # blank box, which is the thing the charter's "never make someone type what they could
    # pick" exists to prevent.
    #
    # Capped at four because a list long enough to need reading is slower than the sentence
    # it replaced.
    options: list[str] = Field(min_length=2, max_length=4)


# The interface already offers writing your own answer and skipping the question, so a model
# that proposes those anyway is spending a choice on something the reviewer already has.
_ESCAPE_HATCHES = frozenset(
    {
        "dont know",
        "i dont know",
        "na",
        "none of the above",
        "none of these",
        "not applicable",
        "not sure",
        "other",
        "something else",
        "unknown",
        "unsure",
    }
)


def _is_escape_hatch(option: str) -> bool:
    bare = "".join(
        character
        for character in option.casefold()
        if character.isalnum() or character == " "
    )
    return bare.strip() in _ESCAPE_HATCHES


def _offered_answers(options: Sequence[str]) -> tuple[str, ...]:
    """The options worth showing: no escape hatches, and never a choice of one.

    Still tolerant of an empty result even though the schema now requires two. A model that
    spends both of its options on "other" and "not sure" has offered nothing, and the
    question is better asked with a blank box than with a menu of one.
    """

    kept = [option for option in options if not _is_escape_hatch(option)]
    return tuple(kept) if len(kept) > 1 else ()


class ConversationAnswerOutput(BaseModel):
    answer: str = Field(min_length=1)
    #: The identifiers of the findings the answer rests on, copied from the listing. One
    #: answer cites several findings at once, so this is the site the charter's rule cannot
    #: be satisfied by fanning out — it is satisfied by naming instead. An identifier the
    #: review does not hold is visibly wrong and is dropped; an ordinal that was wrong but
    #: in range would have grounded the answer on a finding it never read.
    candidate_ids: list[str] = Field(default_factory=list[str])


def case_text(case: ArchitectureCase, *, judging: bool = True) -> str:
    """What a person has told ArchCompass about this architecture, so far.

    An empty case used to reach the model as `{"constraints": [], "decisions": [],
    "answers": []}`. That is three empty arrays next to a fully-stocked policy corpus, and
    a model reading it has a rule to judge against and a blank where the team's intent
    would be — so the cheapest coherent move is to judge on the policy and never ask. The
    empty case now says what it is, in a sentence, because "nobody has told us anything
    about this repository yet" is a fact worth acting on and `[]` is punctuation.

    `judging` is what separates the two readers of that sentence. Everything else that takes
    a case is producing or defending a verdict and is right to be told to say when a missing
    answer would change one. The synopsist is not: it is summarising verdicts already made,
    and the instruction reaches it as "spend a sentence on the empty case", which is one of
    the three sentences a first review used to come back with.
    """

    if not case.answers:
        return (
            "Nobody has answered anything about this architecture yet. This is the first "
            "review, or no judgement has needed a person so far — either way you are "
            "reading this repository without the team's intent, and you should say so "
            "wherever it would change your verdict."
            if judging
            # The same fact, without the instruction attached to it. "Say so wherever it
            # would change your verdict" belongs to a prompt that is producing a verdict; a
            # summariser reading it spends one of its three sentences telling a reader that
            # the team's intent is not written down, which the reader knows and cannot act
            # on from a summary. The absence still has to be stated, because a summary that
            # assumed the case was full would overstate what the review was judged against.
            else (
                "Nobody has answered anything about this architecture yet, so every verdict "
                "below was reached without the team's intent. Context for you, not a "
                "sentence to write."
            )
        )
    return json.dumps(
        {
            "answers": [
                {
                    "question": item.question.text,
                    "status": item.status.value,
                    "value": item.value,
                }
                for item in case.answers
            ]
        },
        ensure_ascii=False,
    )


#: How much of a refused response is quoted back to the model that wrote it. Enough to
#: recognise its own answer, not so much that the repair prompt is the answer again.
_REPAIR_PREVIEW_CHARACTERS: Final = 2_000


#: One request to a model: a single prompt, or a conversation that has already happened.
#:
#: The second shape exists for a judgement that used tools. Its answer has to be reached from
#: the messages it has already exchanged, and flattening those into a string would lose which
#: turn each result belonged to — which is the only thing making the transcript readable.
type Request = str | list[BaseMessage]


def _repair_prompt(
    prompt: Request, parsing_error: object, raw: object
) -> Request | None:
    """The original request, the answer that was refused, and why — or nothing.

    `None` when there is no parser complaint to quote, because then there is nothing to say
    that the first prompt did not already say, and asking again would be the same request
    twice.

    A request is either one prompt or a conversation. A conversation gets the correction as
    a further turn rather than glued onto the end of the last one: a judgement that has
    already used tools carries its own tool messages, and concatenating text onto that would
    put the correction inside somebody else's turn.
    """

    if parsing_error is None:
        return None
    reason = " ".join(str(parsing_error).split())
    content = " ".join(str(getattr(raw, "content", "") or "").split())
    refused = (
        f"\n\nYour previous answer was:\n{content[:_REPAIR_PREVIEW_CHARACTERS]}"
        if content
        else ""
    )
    correction = (
        refused
        + "\n\nThat answer was refused: "
        + reason[:1_000]
        + "\n\nSome of the rules above are conditions between fields that the output "
        "schema cannot state on its own, so honouring the schema is not enough — read the "
        "instruction again and answer so that both hold. Return only the structured "
        "response."
    )
    if isinstance(prompt, str):
        return prompt + correction
    return [*prompt, HumanMessage(correction.lstrip())]


#: What "the model's answer was unusable" looks like, whichever transport produced it.
#:
#: `include_raw=True` promises a mapping carrying `parsing_error` rather than a raised
#: exception, and it keeps that promise on one transport of the three. Its fallback wraps the
#: *parser* only, so a transport that validates inside the model call raises before the
#: mapping is ever built — `langchain-openai` binds the Pydantic class to `response_format`,
#: and the OpenAI SDK then parses within the HTTP call itself.
#:
#: Measured on one prompt carrying a deliberate cross-field violation: Google answered with
#: `parsing_error=OutputParserException` and the repair below fixed it, while the same prompt
#: through `ChatOpenAI` raised `ValidationError`, so the repair never ran and one candidate
#: failed the whole review. They are the same event and are now the same code path.
#:
#: Exactly the failures that mean "what came back cannot be used", and nothing else. A
#: transport failure is not one of them: it belongs to `call_with_retry`, which sits *inside*
#: this net rather than outside it, so a rate limit still waits and asks again rather than
#: being mistaken for a bad answer.
_UNUSABLE_OUTPUT: Final = (
    ValidationError,
    OutputParserException,
    json.JSONDecodeError,
    LengthFinishReasonError,
    ContentFilterFinishReasonError,
)


def _attempt(
    structured: Runnable[Any, object], prompt: Request, *, subject: str
) -> tuple[object, object, object]:
    """One structured call as `(parsed, parsing_error, raw)`, however the transport says it.

    The point is that the caller never learns which of the two shapes it got. A raised
    refusal carries no raw message to quote, which `_repair_prompt` already copes with — and
    a Pydantic complaint names the offending value inside its own text, so the repair still
    says what was wrong with what.
    """

    try:
        result = cast(
            dict[str, object],
            call_with_retry(
                lambda: structured.invoke(prompt), subject=f"Producing {subject}"
            ),
        )
    except _UNUSABLE_OUTPUT as unusable:
        return None, unusable, None
    return result.get("parsed"), result.get("parsing_error"), result.get("raw")


def structured_output[Output: BaseModel](
    model: BaseChatModel,
    schema: type[Output],
    prompt: Request,
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

    Where a transport declines to keep that promise, `_attempt` keeps it on the transport's
    behalf, so everything below reads one shape.
    """

    # Every model call in the application arrives here, which is why the retry sits here
    # too: one place to be sure a rate limit costs a wait rather than the whole review.
    # It wraps the call and nothing else — a rate limit is a reason to wait and ask again,
    # and a response that arrives is not.
    structured = cast(
        "Runnable[Any, object]",
        model.with_structured_output(schema, method="json_schema", include_raw=True),
    )
    output, parsing_error, raw = _attempt(structured, prompt, subject=subject)
    if parsing_error is None and isinstance(output, schema):
        return output

    # One repair attempt, and only because it is not the same request twice.
    #
    # What fails here is almost never the JSON — the runtime constrains that — but a rule
    # the JSON schema cannot carry: a held verdict with nothing to ask, a recommendation on a
    # verdict that may not carry one, four options where two were the floor. The model was not
    # told what it broke, because nothing had gone wrong yet when the prompt was written. This
    # tells it, quoting the parser, and asks once more.
    #
    # It is worth a call because of what the alternative costs. A judgement that fails its
    # schema fails the whole review, after every other candidate has already been judged and
    # paid for; a hinge resolution that fails is caught, logged and thrown away, so the
    # question reaches a person unimproved and the manifest is silently empty. Both were
    # observed on a local model, and both survived a single restatement of the rule.
    #
    # Once, not until it works. A model that cannot honour a contract having just been shown
    # the contract and its own violation of it will not honour it on the fourth attempt
    # either, and the message below is the one a reader needs in that case.
    #
    # One cost to know about. A cross-field rule can usually be satisfied from either side,
    # and the model chooses which — so a rule stated only as "these two conflict" can be
    # honoured by dropping the half that mattered. `FindingOutput`'s rules are all anchored on
    # the verdict now, which is the field the model chose deliberately, so there is one way to
    # satisfy each; the prompts still say which side they mean rather than only that two
    # things conflict.
    # And a *systematic* violation doubles the call count for every candidate rather than
    # for one, which on a metered tier is a review costing twice what it should. Neither is
    # worth refusing the attempt over; both are worth knowing before raising the ceiling.
    repair = _repair_prompt(prompt, parsing_error, raw)
    if repair is not None:
        _log.warning(
            "%s did not match the schema for %s; asking once more with the violation named",
            model_identity or "The reasoning model",
            subject,
        )
        output, parsing_error, raw = _attempt(structured, repair, subject=subject)
        if parsing_error is None and isinstance(output, schema):
            return output

    raw_content = getattr(raw, "content", "")
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
        " Judging is a structured call against a JSON schema, and not every model honours "
        "one. Choose a model whose runtime supports structured JSON output, or — on a "
        "model that offers it — enable Thinking."
    )
    if isinstance(parsing_error, Exception):
        raise ModelOutputValidationError(message) from parsing_error
    raise ModelOutputValidationError(message)


# Asking is an outcome, not a failure to reach one.
#
# The instruction always permitted a hinge, and in practice a model given a well-stocked
# policy corpus and an empty case judges on the policy and never states one — so the
# clarification round, which is the product's answer to "a codebase records what was built,
# not what the team was trying to build", almost never ran. The permission was there; the
# standing was not. So the contract now says out loud what the charter says: a confident
# wrong answer is worth less than an honest question, and a policy is a rule about
# architectures in general while a hinge is about this team's.
#
# It is deliberately not an instruction to ask more often. A hinge on something the
# evidence already settles is worse than no hinge at all: it stops a review to ask a person
# a question the repository answered.
#: What the judgement is for, and how to weigh asking against deciding.
#:
#: Deliberately no longer says how to *fill* the output. Verdict meanings, the citation rule
#: and which fields each verdict may carry are on `FindingOutput`, where the model reads them
#: as it answers and where the validator can actually enforce them. One of them had also gone
#: stale: it told the model policies were "listed under an identifier in brackets" after the
#: rendering stopped using brackets.
#:
#: Two things moved out and had to come back, and both are worth recording because they look
#: like duplication and are not.
#:
#: "Return only the structured response" is not a field semantic at all — it is about what
#: surrounds the answer, and no field description can reach that. Without it a local model
#: stopped honouring the schema entirely: three runs of one candidate, three `Invalid json
#: output` failures and not one lookup, against three clean judgements with nine lookups each
#: once it was restored.
#:
#: The cross-field rules are stated in both places on purpose. They are on the fields, where
#: the validator backs them, and they are here, where the model is deciding which verdict to
#: reach — and a rule about the relationship *between* fields has no single field to live on.
#: Stated only on `recommended_response`, a hosted model attached a recommendation to held and
#: cleared findings often enough to exhaust the one repair and fail the judgement outright.
#:
#: The rest of what stays is the part no schema can hold — that asking is an outcome rather
#: than a failure to reach one, and what makes a question worth interrupting somebody for.
JUDGEMENT_INSTRUCTION = (
    "Judge whether this detected structure costs more than it earns. Use the supplied "
    "evidence and case, and the repository where it can settle something they cannot.\n\n"
    "Asking is a first-class outcome here, not a failure to decide. A policy tells you what "
    "is usually true of architectures; it cannot tell you what this team decided, what they "
    "are about to change, or what they already accepted and why. Where your verdict would "
    "turn on one of those, hold and name the single fact you would need.\n\n"
    "A hinge stops the review and puts your question to a person, so it is worth their "
    "interruption — do not hinge on something the supplied evidence already settles, and do "
    "not hinge merely to avoid committing. A held verdict carries its hinge and nothing "
    "else — a judgement waiting on an answer does not yet recommend anything — and only a "
    "material finding recommends a response.\n\n"
    "Return only the structured response, with no Markdown or prose around it."
)


#: What a hinge investigation established, rendered by the application from its own record.
#:
#: Deliberately not the investigating model's prose. That model wrote a paragraph about what
#: it had looked up; handing *that* to the judge would put an interpretation between the
#: repository and the verdict, and the judge would be reasoning over a summary rather than
#: over what the repository actually said. So this is built from `(tool, arguments, result)`
#: — the exact answers, in the order they were asked for.
#:
#: The heading says whose choice these were. Evidence under CANDIDATE was selected by a
#: detector; this was selected by a model, from the same pinned atlas and the same reviewed
#: revision. Both may be weighed. Neither may be mistaken for the other, and nothing here is
#: ever written into `Finding.evidence`.
OBSERVATIONS_INSTRUCTION: Final = (
    "OBSERVATIONS\n"
    "Lookups a previous pass made into this repository because your verdict turned on "
    "something the evidence above does not carry. They are exact answers from the reviewed "
    "revision, chosen by a model rather than by the detector, and they are not evidence: "
    "weigh them, do not cite them as though the detector had pinned them."
)


def observations_text(investigation: RecordedInvestigation) -> str:
    """One investigation as the judge reads it: what was asked, and what came back.

    A truncated investigation says so, because the difference between "the repository is
    silent" and "we stopped asking" is the difference between a verdict and a question, and
    a judge shown only the first three of six intended lookups would otherwise read them as
    the whole of what could be found. `None` is rendered as unrecorded rather than as a
    natural end: an investigation stored before terminations were recorded is one whose
    completeness is simply unknown.
    """

    if investigation.withheld:
        return f"{OBSERVATIONS_INSTRUCTION}\n\nNothing could be looked up: {investigation.withheld}"
    asked = "\n\n".join(
        f"{item.tool}({', '.join(f'{key}={value}' for key, value in item.arguments)})"
        f"\n{item.result}"
        for item in investigation.lookups
    )
    if investigation.termination is None:
        note = "It is not recorded why this investigation stopped, so it may be incomplete."
    elif investigation.termination is Termination.NATURAL_END:
        note = "The pass stopped looking of its own accord."
    else:
        note = (
            f"This investigation was cut short ({investigation.termination.value}), so it "
            "may be incomplete: treat silence here as unexplored rather than as absence."
        )
    return f"{OBSERVATIONS_INSTRUCTION}\n\n{asked or '(no lookup answered)'}\n\n{note}"


def judgement_prompt(
    candidate: Candidate,
    case: ArchitectureCase,
    policies: RetrievedPolicySet,
    investigation: RecordedInvestigation | None = None,
) -> str:
    """The one prompt every transport sends.

    One function rather than one per transport, because a judgement must not depend on
    which transport carried it — a review judged through Google is not allowed to have been
    asked a different question from one judged through Ollama.

    The three inputs are kept in three named blocks because they are three kinds of thing:
    CASE is what a person said, CANDIDATE carries evidence the detector chose, and
    OBSERVATIONS carries lookups a model chose. The last is absent on a first judgement and
    present on the second, which is the only difference between them.
    """

    return "\n\n".join(
        (
            JUDGEMENT_INSTRUCTION,
            f"CASE\n{case_text(case)}",
            f"CANDIDATE\n{candidate_text(candidate)}",
            "POLICIES\n"
            + "\n\n".join(
                # The id on its own line and labelled, because the citation check is exact
                # and this is the string it wants back. Rendered as `[id] Title` it was read
                # as part of the display: two model families cited
                # `[delay-premature-abstraction]`, brackets included, and every one of those
                # citations was refused. Nothing is repaired downstream — a fuzzy match would
                # make a wrong id look like a near miss — so the format has to be unambiguous
                # here instead.
                f"Policy ID: {policy.id}\n{policy.title}\n{policy.body}"
                for policy in policies.policies
            ),
            *((observations_text(investigation),) if investigation else ()),
        )
    )


#: The two resolvers that name an edge. Anything else in `resolved_by` came from a detector
#: inferring a relation rather than from a pass resolving one, and says so in its own words —
#: so it is printed as written instead of being called a pass it is not.
_RESOLVING_PASSES = ("parse", "types")


def _established_by(resolved_by: str) -> str:
    if resolved_by in _RESOLVING_PASSES:
        return f"the {resolved_by} pass"
    return resolved_by


def candidate_text(candidate: Candidate) -> str:
    """One candidate laid out as sections a model can address, rather than as a repr.

    The dataclass repr was doing this job, and it escapes every newline in an excerpt: the
    code arrived as one very long line punctuated by literal ``\\n``. Measurements arrived
    the same way, so the ``structural_proxy`` tag that says "this count is a hint, not a
    fact" was present and unreadable at the same time.

    Relationships are stated before the evidence on purpose. Placement is what the verdict
    rests on — which abstraction is implemented by which adapter, and whether the parser or
    the type checker established it — and it should be read before the code rather than
    reconstructed from underneath it.
    """

    blocks = [f"pattern: {candidate.pattern}", f"summary: {candidate.summary}"]
    blocks.append(
        "participants:\n"
        + "\n".join(
            f"  - {item.qualified_name} — {item.role}" for item in candidate.participants
        )
    )
    if candidate.relationships:
        blocks.append(
            "relationships:\n"
            + "\n".join(
                f"  - {item.source} --{item.kind}--> {item.target} "
                f"(established by {_established_by(item.resolved_by)})"
                for item in candidate.relationships
            )
        )
    if candidate.measurements:
        blocks.append(
            "measurements:\n"
            + "\n".join(_measurement_text(item) for item in candidate.measurements)
        )
    if candidate.evidence:
        blocks.append(
            "evidence:\n"
            + "\n\n".join(_evidence_text(item) for item in candidate.evidence)
        )
    if candidate.limitations:
        blocks.append(f"what this detection method cannot see: {candidate.limitations}")
    return "\n\n".join(blocks)


def _measurement_text(measurement: Measurement) -> str:
    lines = [
        f"  - {measurement.name} = {measurement.display} [{measurement.nature.value}]"
    ]
    if measurement.definition:
        lines.append(f"    counts: {measurement.definition}")
    if measurement.limitations:
        lines.append(f"    cannot establish: {measurement.limitations}")
    return "\n".join(lines)


def _evidence_text(evidence: Evidence) -> str:
    where = (
        "location not recorded"
        if evidence.location is None
        else f"{evidence.location.path}:{evidence.location.start_line}"
        f"-{evidence.location.end_line}"
    )
    lines = [f"  - {evidence.description}", f"    {where}"]
    if evidence.note:
        lines.append(f"    note: {evidence.note}")
    if evidence.excerpt:
        lines.append("    ```")
        lines.extend(f"    {line}" for line in evidence.excerpt.splitlines())
        lines.append("    ```")
    else:
        lines.append("    (no code was read at this location)")
    return "\n".join(lines)


def finding_from_output(
    output: FindingOutput,
    candidate: Candidate,
    policies: RetrievedPolicySet,
    *,
    model_identity: str,
    prompt_identity: str,
) -> Finding:
    """The validated response as a domain finding, with the model's citations resolved.

    A citation that names no presented policy is dropped rather than raised. That is the
    trade the charter's rule buys: a bearing is the record of why a verdict was reached, so
    losing one weakens the record, where raising here would destroy a review that has
    already been judged. It is only affordable because the citation is a name — a name that
    matches nothing is visibly wrong, while an ordinal that is wrong but in range resolves
    to the wrong policy and reads as a correct one for ever.
    """

    bearings: list[PolicyBearing] = []
    presented = {policy.id: policy for policy in policies.policies}
    seen: set[str] = set()
    for bearing in output.policy_bearings:
        policy = presented.get(bearing.policy_id)
        if policy is None:
            _log.warning(
                "Reasoning model %s cited policy %r, which it was not presented with",
                model_identity,
                bearing.policy_id,
            )
            continue
        if policy.id in seen:
            continue
        seen.add(policy.id)
        bearings.append(PolicyBearing(policy, bearing.reasoning))
    # Taken, not inferred. This read the hinge first and the boolean second, so a model that
    # asserted materiality *and* asked a question had its assertion silently discarded — the
    # two fields could disagree and nothing said so.
    verdict = Verdict(output.verdict)
    return Finding(
        candidate=candidate,
        verdict=verdict,
        reasoning=output.reasoning,
        policies=tuple(bearings),
        evidence=candidate.evidence,
        hinge=output.hinge,
        recommended_response=output.recommended_response,
        model_identity=model_identity,
        prompt_identity=prompt_identity,
        retrieval_identity=policies.provenance.identity,
    )


class LangChainArchitectureJudge:
    """One controlled structured call; the model never supplies ArchCompass identity."""

    def __init__(
        self,
        model: BaseChatModel,
        *,
        model_identity: str,
        prompt_identity: str = JUDGE_PROMPT_IDENTITY,
    ) -> None:
        self._model = model
        self._model_identity = model_identity
        self._prompt_identity = prompt_identity

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
        investigation: RecordedInvestigation | None = None,
        *,
        subject: ReviewedSubject | None = None,
    ) -> Finding:
        # One structured call and no tools, so there is nothing to look at. Taken to satisfy
        # the port; a judgement that reads the repository is `DeepArchitectureJudge`.
        del subject
        output = structured_output(
            self._model,
            FindingOutput,
            judgement_prompt(candidate, case, policies, investigation),
            subject="a review finding",
            model_identity=self._model_identity,
        )
        return finding_from_output(
            output,
            candidate,
            policies,
            model_identity=self._model_identity,
            prompt_identity=self._prompt_identity,
        )



QUESTION_INSTRUCTION = (
    "One finding below is held: a judgement stopped because it turns on a fact this "
    "repository cannot supply. Write the single question that would settle it, addressed to "
    "somebody on the team.\n\n"
    "Ask about the hinge and nothing else. The question interrupts a person, so it has to "
    "be worth the interruption: one sentence, about this team's intent rather than about "
    "the code, and answerable without opening the repository.\n\n"
    "Offer two to four answers you consider likely, in `options`, likeliest first. Each "
    "option must be a complete statement that could be recorded on the architecture case "
    "exactly as written — not a label like 'yes' or 'option A' — and the options must be "
    "mutually exclusive. Never offer 'other', 'none of these', 'unknown' or any variation: "
    "the reviewer is always offered writing their own answer and skipping the question, "
    "beneath every question, so offering it back to them wastes a choice. If you cannot "
    "name two likely answers, the question is too open to be worth a person's interruption "
    "— ask a narrower one instead."
)


def question_prompt(finding: Finding, case: ArchitectureCase) -> str:
    """The one held finding a question is asked about, and nothing it could point at."""

    candidate = finding.candidate
    return "\n\n".join(
        (
            QUESTION_INSTRUCTION,
            f"CASE\n{case_text(case)}",
            "THE HELD FINDING\n"
            + "\n".join(
                (
                    f"  {candidate.summary}",
                    f"  pattern: {candidate.pattern}",
                    "  participants: "
                    + ", ".join(
                        item.qualified_name for item in candidate.participants
                    ),
                    f"  why it was held: {finding.reasoning}",
                    f"  waiting on: {finding.hinge}",
                )
            ),
        )
    )


class LangChainQuestionGenerator:
    """One question per held finding, asked one call at a time.

    The finding a question belongs to is the finding the call was made about, so the model
    is never asked to point at one. It used to be, and the pointing is what broke: a single
    call was shown every finding under a number — cleared ones included — told in prose not
    to pick the ones without a hinge, and the code then raised when it did. A review that
    had judged every candidate was thrown away over a number.

    What the single call could do and this cannot is merge. Six findings that share a hinge
    were one question there and are six here. That is left standing on purpose: the
    duplicates are visible in a round's output, and a merge is worth building when they turn
    up rather than in advance of them.
    """

    def __init__(
        self, model: BaseChatModel, *, prompt_identity: str = "questions:v2"
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
        # Every hinge, not the first eight of them. The cap was there because nine questions
        # in a form is a form nobody finishes, and deferring the rest to the next round read
        # as costless — but a review seals at round three, so a hinge deferred twice is a
        # hinge never asked, and the finding it belonged to was sealed on a verdict reached
        # without it. A question that had to be asked is worth the length of the form.
        held = tuple(finding for finding in findings if finding.hinge)
        questions: list[Question] = []
        seen: set[str] = set()
        lost = 0
        for finding in held:
            question = self._ask_about(finding, case, round=round)
            if question is None:
                lost += 1
                continue
            if (
                question.equivalence_key in excluded_equivalence_keys
                or question.equivalence_key in seen
            ):
                continue
            seen.add(question.equivalence_key)
            questions.append(question)
        if lost:
            # Counted and said out loud, because the two ways to end this loop with nothing
            # are opposite facts and used to look identical downstream. No held findings
            # means the review settled everything and is finished; every held finding losing
            # its question means the review has uncertainty it could not put into words, and
            # `_after_questions` seals the case for both. A per-question warning could not
            # say which had happened — only this can, and at ERROR because a review that
            # asked nothing for this reason is a review that quietly stopped short.
            log = _log.error if lost == len(held) else _log.warning
            log(
                "%d of %d held finding(s) reached no question this round; "
                "the review will not ask about them",
                lost,
                len(held),
            )
        return tuple(questions)

    def _ask_about(
        self, finding: Finding, case: ArchitectureCase, *, round: int
    ) -> Question | None:
        """The question for one finding, or none if the model would not write one.

        A lost question costs the round one question. The finding it belonged to goes on
        being held, which is what it already was — so this degrades the way an investigation
        does rather than taking the other findings' questions down with it.
        """

        try:
            output = structured_output(
                self._model,
                QuestionOutput,
                question_prompt(finding, case),
                subject="a question for the team",
            )
        except Exception:
            _log.warning(
                "The hinge on %s was not turned into a question",
                finding.candidate.id,
                exc_info=True,
            )
            return None
        return Question.create(
            text=output.text,
            facet=CaseFacet(output.facet),
            candidate_ids=(str(finding.candidate.id),),
            round=round,
            options=_offered_answers(output.options),
        )


# The contract a conversation is held to. It is deliberately not the judgement contract.
#
# A reader arrives at this box having already read a finding, and the question they type is
# usually "so what do I do about it". Answering that with "the review does not contain any
# information on how to fix the identified issues" is technically true of a document and
# useless to a person: what to do follows from what was found, and following from it is the
# job. So facts stay pinned to the review while reasoning over those facts is expected, and
# the answer says which of the two the reader is looking at.
CONVERSATION_CONTRACT = (
    "A reader has this architecture review open and is asking you about it.\n\n"
    "Two kinds of question arrive here. Some ask what the review found — answer those from "
    "the review alone. Others ask what to do about what it found: how a finding would be "
    "fixed, what the options are, which to take first. Answer those too. They are not "
    "outside the review; they are why somebody read it. Reason from the findings, the "
    "policies they bear on and any recommended response already recorded, and make plain "
    "which part of your answer the review records and which part is you reasoning from "
    "it.\n\n"
    "Facts about this codebase come only from the review. Do not invent a module, a call "
    "site or a name you were not shown. Where a fix turns on something the review does not "
    "establish, say what would have to be true and which finding's evidence would settle "
    "it. Say the review cannot answer only when it lacks the facts the question needs — "
    "never merely because the question asks for judgement.\n\n"
    "You are told where each piece of evidence sits, but not what the code at those lines "
    "says. So describe a fix as structure and placement, cite the locations, and do not "
    "write a patch as though you had read the file.\n\n"
    "Cite the findings you relied on. In your prose, name one by its backticked "
    "participant, the way the listing does. In `candidate_ids`, return the bracketed "
    "identifier of each one you used, copied exactly — an identifier you were not shown "
    "is dropped, so an invented one grounds nothing. Write prose a reader can act on: no "
    "headings, no restating the question."
)

#: Added to the contract only where the reader's repository can actually be asked. Kept
#: apart from `CONVERSATION_CONTRACT` because the sentence "you may look it up" is false
#: wherever no toolbox was offered, and a contract that says it anyway teaches a model to
#: claim it checked.
CONVERSATION_LOOKUPS = (
    "You can also ask this repository structural questions directly — what implements "
    "something, what depends on it, what calls it, what tests it, and what the code at a "
    "named part of it says. Use that where the review does not settle a question and the "
    "structure would. A fact still has to come from the review or from something you "
    "actually looked up; say which."
)


#: How many of a review's policies the conversation is given, most-borne-on first.
#:
#: A bound rather than a preference. This used to be every policy every finding cited, at
#: full length, and it is the one section of this prompt that grows with the size of the
#: repository rather than with the question: fifty findings citing the whole corpus came to
#: 350,000 characters, which is more than any context window this product configures. Ollama
#: does not refuse an oversize prompt — it keeps the tail — so the section that would have
#: been discarded first is the contract at the top, and the answer comes back fluent, and
#: nothing says the rules were dropped.
#:
#: Twenty, because that is what retrieval hands a judgement, and a conversation that ranged
#: over more rules than any single verdict rested on would be answering from a corpus rather
#: than from this review.
MAX_CONVERSATION_POLICIES: Final = 20

#: The two sections of a policy that state the rule. The rest — signals, diagnostics,
#: consequences, exceptions, both examples, the related list — is what makes a *judgement*
#: rigorous, and a judgement reads one policy set for one candidate. A conversation reads
#: twenty at once, and this is the same trade `_conversation_finding_text` already makes
#: with the code behind a finding: breadth, and the depth is a click away.
_CONVERSATION_POLICY_SECTIONS: Final = ("Intent", "Guidance")


def _conversation_policies(review: Review) -> tuple[tuple[Policy, int], ...]:
    """The policies this review's findings bear on, with how many bear on each.

    Gathered here rather than repeated under each finding because the rule a fix has to
    respect is the same rule however many findings bore on it, and its wording is what makes
    a proposed fix answerable against it.

    Ordered by how many findings cite it, because the section is capped and a cap has to
    drop something: the rule three findings turn on belongs in front of the one that came up
    once. Ties break on the identifier so the prompt is the same prompt twice.
    """

    seen: dict[str, Policy] = {}
    borne: dict[str, int] = {}
    for finding in review.findings:
        for bearing in finding.policies:
            seen.setdefault(bearing.policy.id, bearing.policy)
            borne[bearing.policy.id] = borne.get(bearing.policy.id, 0) + 1
    ranked = sorted(seen, key=lambda policy_id: (-borne[policy_id], policy_id))
    return tuple((seen[policy_id], borne[policy_id]) for policy_id in ranked)


def _conversation_policy_text(policy: Policy) -> str:
    """One policy as the rule it states, without the material that argues for it."""

    kept = [
        section
        for section in policy.body.split("\n## ")
        if section.removeprefix("## ").split("\n", 1)[0] in _CONVERSATION_POLICY_SECTIONS
    ]
    body = "\n## ".join(kept).strip() if kept else policy.body.strip()
    return f"'{policy.title}' ({policy.strength.value})\n{body}"


def _conversation_finding_text(finding: Finding) -> str:
    """One finding as breadth rather than depth.

    Judgement reads a single candidate in full, code included. A conversation ranges over
    every finding at once and cannot afford that, so it is given what each finding is, what
    it bears on, what was recommended, and where the evidence sits — but not the code at
    those lines. That is a click away in the workbench, which is exactly where citing a
    finding puts the reader.
    """

    candidate = finding.candidate
    lines = [
        # The identifier first because it is what a citation has to copy, and the backticked
        # participant beside it because that is what the answer calls the finding in prose.
        # A reader is shown the prose, and `candidate_9fa3…` is not a name anybody reads.
        f"[{candidate.id}] `{candidate.participants[0].qualified_name}`",
        f"    summary: {candidate.summary}",
        f"    pattern: {candidate.pattern}",
        f"    verdict: {finding.verdict.value}",
        f"    reasoning: {finding.reasoning}",
    ]
    if finding.recommended_response:
        lines.append(f"    recommended response: {finding.recommended_response}")
    if finding.hinge:
        lines.append(f"    held, waiting on: {finding.hinge}")
    lines.extend(
        f"    bears on '{bearing.policy.title}' ({bearing.policy.strength.value}): "
        f"{bearing.reasoning}"
        for bearing in finding.policies
    )
    if candidate.participants:
        lines.append(
            "    participants: "
            + ", ".join(
                f"{item.qualified_name} ({item.role})" for item in candidate.participants
            )
        )
    lines.extend(
        f"    {item.source} --{item.kind}--> {item.target}"
        for item in candidate.relationships
    )
    lines.extend(
        f"    measured: {item.name} = {item.display} [{item.nature.value}]"
        + (f"; counts {item.definition}" if item.definition else "")
        for item in candidate.measurements
    )
    # `finding.evidence` is not a second, judged selection: every producer copies
    # `candidate.evidence` into it whole. Listing both put every excerpt in twice.
    lines.extend(
        f"    evidence: {_conversation_evidence_text(item)}"
        for item in candidate.evidence
    )
    if candidate.limitations:
        lines.append(f"    this detection cannot see: {candidate.limitations}")
    return "\n".join(lines)


def _conversation_evidence_text(evidence: Evidence) -> str:
    where = (
        "location not recorded"
        if evidence.location is None
        else f"{evidence.location.path}:{evidence.location.start_line}"
        f"-{evidence.location.end_line}"
    )
    note = f"; {evidence.note}" if evidence.note else ""
    return f"{evidence.description} ({where}){note}"


def conversation_prompt(
    review: Review,
    history: Sequence[ConversationMessage],
    question: str,
    *,
    transcript: str = "",
    can_look: bool = False,
    for_lookups: bool = False,
) -> str:
    repository = review.repository
    where = str(repository.path)
    if repository.branch:
        where += f" on {repository.branch}"
    if repository.commit:
        where += f" at {repository.commit[:12]}"
    sections = [
        *(
            ()
            if for_lookups
            # The loop sends the contract as a system message, so the turn that opens it
            # would otherwise state the rules twice.
            else (CONVERSATION_CONTRACT + (f"\n\n{CONVERSATION_LOOKUPS}" if can_look else ""),)
        ),
        f"REVIEW\nnumber {review.sequence} of {where}\nstatus: {review.status.value}",
        f"CASE\n{case_text(review.case)}",
    ]
    if review.questions:
        sections.append(
            "STILL UNANSWERED BY THE TEAM\n"
            + "\n".join(f"  - {item.text}" for item in review.questions)
        )
    policies = _conversation_policies(review)
    if policies:
        shown = policies[:MAX_CONVERSATION_POLICIES]
        # Said out loud when the cap bites, because a model that cannot see a rule must not
        # answer as though the review rested on nothing else.
        omitted = (
            ""
            if len(shown) == len(policies)
            else (
                f"\n\n{len(policies) - len(shown)} further policies this review cites are "
                "not listed here; say so rather than assuming they say nothing."
            )
        )
        sections.append(
            "POLICIES THESE FINDINGS BEAR ON\n"
            + "\n\n".join(_conversation_policy_text(policy) for policy, _ in shown)
            + omitted
        )
    sections.append(
        "FINDINGS\n"
        + "\n\n".join(
            _conversation_finding_text(finding) for finding in review.findings
        )
    )
    if history:
        sections.append(
            "WHAT HAS ALREADY BEEN ASKED HERE\n"
            + "\n".join(f"Q: {item.question}\nA: {item.answer.text}" for item in history)
        )
    if transcript:
        sections.append(f"WHAT YOU LOOKED UP\n{transcript}")
    sections.append(f"QUESTION\n{question}")
    return "\n\n".join(sections)


def _cited_candidates(cited: Sequence[str], review: Review) -> tuple[str, ...]:
    """The findings an answer says it rested on, kept where the review actually holds them.

    An identifier the review does not hold is dropped and logged, never raised. The answer
    itself is still an answer — the reader loses one grounding chip, not the reply — and a
    name that matches nothing is detectably wrong, which is the property an ordinal never
    had. In the model's order, because that is the order it reasoned in.
    """

    known = {str(finding.candidate.id) for finding in review.findings}
    kept: list[str] = []
    for candidate_id in cited:
        if candidate_id not in known:
            _log.warning(
                "An answer about review %s cited %r, which the review does not hold",
                review.id,
                candidate_id,
            )
            continue
        if candidate_id not in kept:
            kept.append(candidate_id)
    return tuple(kept)


class LangChainReviewAnswerer:
    """A grounded answer, after whatever the reader's question made worth looking up.

    The lookups are optional and the first turn is never forced, unlike a hinge
    investigation's. A reader is usually asking about text already in front of them — "what
    does this finding mean", "which of these first" — and a forced call there spends a round
    trip asking the repository about the review's own words. Where the question *is* about
    the repository, the model reaches for the toolbox itself.
    """

    def __init__(
        self,
        model: BaseChatModel,
        investigators: InvestigatorSource | None = None,
    ) -> None:
        self._model = model
        self._investigators = investigators

    def answer(
        self,
        review: Review,
        history: tuple[ConversationMessage, ...],
        question: str,
    ) -> ConversationAnswer:
        offered = (
            None
            if self._investigators is None
            else self._investigators.for_review(review.repository, review.atlas)
        )
        investigator = None if offered is None else offered.investigator
        transcript = ""
        if investigator is not None:
            transcript = investigate_with_tools(
                self._model,
                investigator,
                system=CONVERSATION_CONTRACT + "\n\n" + CONVERSATION_LOOKUPS,
                opening=conversation_prompt(
                    review, history, question, can_look=True, for_lookups=True
                ),
                subject="a reader's question about this review",
                force_first=False,
            )
        output = structured_output(
            self._model,
            ConversationAnswerOutput,
            conversation_prompt(
                review,
                history,
                question,
                transcript=transcript,
                can_look=investigator is not None,
            ),
            subject="a grounded answer",
        )
        return ConversationAnswer(
            output.answer,
            _cited_candidates(output.candidate_ids, review),
            recorded_investigation(
                investigator,
                candidate_id="",
                withheld="" if offered is None else offered.withheld,
                atlas_fingerprint=review.repository.content_id,
            ),
        )


# The contract the review's opening paragraph is held to.
#
# The report already told the reader how many candidates were judged and in what states. A
# number is orientation and not an answer: "two material, three held" does not say whether
# the two are one problem seen twice, whether either can wait, or which one a person should
# open first. That is what this paragraph is for, and it is the only place in the product
# where the model is asked about a review rather than about a candidate.
#
# Everything it may say has already been judged. It is summarising, not judging again — so
# it gets verdicts, hinges, policies and delta states, and it gets no evidence, no
# measurements and no atlas, because a sentence about a line of code is a sentence it would
# be inventing.
#
# The length rule is a ceiling and never a floor, and that is the correction this paragraph
# has already needed once. It used to ask for "three to five sentences", which is an
# instruction to pad: a review with one material finding in it got the one sentence that
# said so and then two more manufactured to reach the floor — that this was the first review,
# that there was nothing to compare it against, that the team's intent was not written down.
# Every one of those is true, none of them is news to the reader, and all three were produced
# because the prompt asked for a word count instead of an answer.
#
# The floor cannot be replaced by a schema constraint either. `structured_output` treats a
# response that fails its schema as a hard failure and deliberately does not retry it, so a
# `max_length` on `SynopsisOutput.summary` would trade a long summary for a failed review —
# and the summary is the one part of a review that a reader can do without.
SYNOPSIS_CONTRACT = (
    "You are writing the opening paragraph of an architecture review. It is read away from "
    "the tool — attached to a pull request, downloaded as a document, pasted into a "
    "channel — by somebody deciding whether to open the review at all.\n\n"
    "Say what this review amounts to. What needs a person comes first: the material "
    "findings, whether they are separate problems or one problem in several places, and "
    "which to take first. After that, what judgement is waiting on, and what moved since "
    "the previous review. That is an order of priority and not a list to work through — "
    "each of them earns a place only if there is something to say about it, and a review "
    "with nothing waiting on it says nothing about waiting. Candidates that were cleared "
    "are worth a clause at most.\n\n"
    "Every fact must come from the findings below. Do not name a module, a metric or a "
    "policy you were not shown. Do not make a verdict sound stronger or weaker than it was "
    "recorded, do not recommend a fix that no finding recommends, and do not tell the "
    "reader the architecture is sound — this review saw the candidates it was given and "
    "nothing else. Where you say two findings are related, that relation has to be visible "
    "in what you were shown.\n\n"
    "Name a candidate by the identifier you were given, in backticks, and only where naming "
    "it is what makes the sentence useful.\n\n"
    "Be short. Three sentences is the ceiling and not the target: a review with one thing in "
    "it gets one sentence. Lead with the thing rather than with a sentence about the review "
    "— \"`a.B` and `c.D` state the branch name separately\", not \"This review requires "
    "attention regarding a material finding in `a.B` due to duplicated knowledge\". Prefer "
    "the words somebody would use saying this to a colleague out loud.\n\n"
    "Say nothing the reader has already been told. Not the counts. Not that this is the "
    "first review, or that there is no previous one to compare against, or that the team's "
    "intent is not written down yet — the reader knows which review they opened, and the "
    "report says the rest. Do not restate a recommended response the report prints in full "
    "below. No headings and no bullets.\n\n"
    "Short is not the same as bare, and the two failures are worth as much as each other. A "
    "sentence naming a finding and stopping has spent itself on an identifier: say what was "
    "found and what it costs, in however few words that takes. If that fits in one clause, "
    "the clause is the whole summary."
)


class SynopsisOutput(BaseModel):
    summary: str = Field(min_length=1)


def _synopsis_finding_text(finding: Finding, delta_state: str | None) -> str:
    """One judged candidate, reduced to what a summary can honestly use."""

    name = finding.candidate.participants[0].qualified_name
    parts = [
        f"`{name}` — {finding.verdict.value}",
        f"pattern: {finding.candidate.pattern}",
        f"summary: {finding.candidate.summary}",
        f"reasoning: {finding.reasoning}",
    ]
    if delta_state:
        parts.append(f"since the previous review: {delta_state}")
    if finding.hinge:
        parts.append(f"waiting on: {finding.hinge}")
    if finding.recommended_response:
        parts.append(f"recommended response: {finding.recommended_response}")
    if finding.policies:
        parts.append(
            "bears on: "
            + "; ".join(item.policy.title for item in finding.policies)
        )
    return "\n  ".join(parts)


def _synopsis_delta_states(delta: ReviewDelta) -> dict[str, str]:
    states = {str(item.id): "new" for item in delta.new}
    for change in delta.changed:
        causes = ", ".join(cause.value for cause in change.causes)
        states[str(change.candidate.id)] = f"changed ({causes})" if causes else "changed"
    for item in delta.unchanged:
        states[str(item.id)] = "unchanged"
    return states


def synopsis_prompt(
    case: ArchitectureCase,
    findings: Sequence[Finding],
    *,
    questions: Sequence[Question],
    delta: ReviewDelta,
    previous_sequence: int | None,
    waiting: bool,
) -> str:
    """The one prompt the summary is written from."""

    states = _synopsis_delta_states(delta)
    sections = [SYNOPSIS_CONTRACT, f"CASE\n{case_text(case, judging=False)}"]
    if waiting:
        sections.append(
            "THIS REVIEW IS NOT FINISHED. It is waiting on answers before it can judge "
            "everything, and the reader is told so above your paragraph. Summarise what it "
            "has so far and do not present it as settled."
        )
    sections.append(
        "FINDINGS\n"
        + "\n\n".join(
            _synopsis_finding_text(finding, states.get(str(finding.candidate.id)))
            for finding in findings
        )
    )
    if previous_sequence is None:
        sections.append(
            "This is the first review in its lineage, so there is nothing to compare it "
            "against and nothing has moved. That is context for you, not a fact to report: "
            "a sentence saying that nothing has moved yet is a sentence spent saying "
            "nothing, and the reader can see which review they opened."
        )
    elif delta.addressed:
        sections.append(
            f"NO LONGER DETECTED SINCE REVIEW {previous_sequence}\n"
            + "\n".join(
                f"- {item.title} (last judged {item.last_verdict.value})"
                for item in delta.addressed
            )
        )
    if questions:
        sections.append(
            "QUESTIONS THIS REVIEW IS ASKING\n"
            + "\n".join(f"- {question.text}" for question in questions)
        )
    return "\n\n".join(sections)


class LangChainReviewSynopsist:
    """The model's account of the review it has just finished judging."""

    def __init__(self, model: BaseChatModel, *, model_identity: str = "") -> None:
        self._model = model
        self._model_identity = model_identity

    def write(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        questions: tuple[Question, ...],
        delta: ReviewDelta,
        previous: Review | None,
        waiting: bool,
    ) -> ReviewSynopsis | None:
        # Nothing judged is not a summary of nothing; it is a report that opens on the
        # sentence it already has, which says the analysis found no candidates and declines
        # to call that a clean bill of health. A model asked to summarise an empty list
        # would write the second half of that on its own.
        if not findings:
            return None
        prompt = synopsis_prompt(
            case,
            findings,
            questions=questions,
            delta=delta,
            previous_sequence=None if previous is None else previous.sequence,
            waiting=waiting,
        )
        output = structured_output(
            self._model,
            SynopsisOutput,
            prompt,
            subject="the review's summary",
            model_identity=self._model_identity or None,
        )
        text = output.summary.strip()
        return ReviewSynopsis(text, self._model_identity) if text else None
