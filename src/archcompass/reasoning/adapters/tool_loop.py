"""The turns a review may spend looking things up, and the record it leaves behind.

One loop. A caller gives a model a toolbox and its own question, the model asks the
repository, and this renders what was asked and what came back as one block of text for the
structured call that follows. Two caps bound it — how many turns, and how many characters of
findings — and both exist so an investigation terminates in front of a reader watching a
review run.

Failure here degrades rather than propagates. Investigating is an improvement to a question,
and the worst outcome allowed is a review that asks the way it asked before: a provider
error becomes a note on the record, and the hinge it could not settle stands.

Separate from `langchain.py` because it is a different kind of call. Everything there is one
structured request against a JSON schema; this is an unconstrained conversation that happens
before one. It deliberately imports nothing from there — both of that module's tool-using
callers import this, and a loop that reached back for a prompt would close the circle.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from archcompass.domain import (
    CandidateId,
    InvestigationLookup,
    RecordedInvestigation,
)
from archcompass.domain.errors import ProviderError
from archcompass.ports.investigation import SourceInvestigator, ToolSpec
from archcompass.retrying import call_with_retry

_log = logging.getLogger(__name__)

#: How many rounds of tool calling one investigation may take before it has to conclude with
#: what it has. Six is enough for a find, two relations and a read, which is the shape the
#: worthwhile lookups take; past that the pass is browsing. The failure a cap prevents is
#: not expense but an investigation that never terminates in front of a reader watching a
#: review run. The last turn is spent without a further model call: a turn the loop would
#: not act on is a request nobody reads.
MAX_INVESTIGATION_TURNS = 6

#: The ceiling on what one whole investigation may record, across every result. The
#: per-result clamp bounds one answer and the turn cap bounds the conversation's length, but
#: neither bounds their product: a model may put several calls in one turn. Lower than the
#: per-result clamp times the turn cap on purpose — this record is stored on every review
#: and projected on every listing of them.
MAX_INVESTIGATION_CHARACTERS = 10_000

INVESTIGATION_PROMPT_IDENTITY = "investigate-hinge:v1"


def _forced_first_call(model: BaseChatModel) -> str | None:
    """The word this provider uses for "you must call something", or None where it has none.

    Ollama's `bind_tools` accepts `tool_choice` and documents that it ignores it, so passing
    one there would be a silent no-op — worse than not passing it, because the loop would
    believe the opening turn was constrained when it was not. Detected by type rather than
    by inspecting `bind_tools`, because `ChatOpenAI` inherits its own from `BaseChatOpenAI`
    and every structural check for it answers wrongly.
    """

    if isinstance(model, ChatGoogleGenerativeAI):
        return "any"
    if isinstance(model, ChatOpenAI):
        return "required"
    return None


def _tool_definitions(specs: Sequence[ToolSpec]) -> list[dict[str, object]]:
    """The toolbox in the one shape all three vendors accept.

    Every integration runs `convert_to_openai_tool` over whatever it is handed, so a plain
    function dict passes through unchanged on all of them. That is why `ToolSpec.parameters`
    is JSON Schema data rather than a Pydantic model: assembled once, translated never.
    """

    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": dict(spec.parameters),
            },
        }
        for spec in specs
    ]


def investigate_with_tools(
    model: BaseChatModel,
    investigator: SourceInvestigator,
    *,
    system: str,
    opening: str,
    subject: str,
    force_first: bool = True,
) -> str:
    """Let the model look things up, and render what it looked at.

    Returns "" when nothing was rendered — a transport that cannot bind tools, or a model
    that decided immediately it had nothing to check. What comes back is a rendering of the
    *transcript*, not of the conversation: the transcript is the application's record of
    what was asked and what the repository said, and it is the only part of this a later
    verdict can be traced to. The model's closing prose is appended after it rather than
    interleaved, so it cannot be mistaken for a result.
    """

    definitions = _tool_definitions(investigator.tools)
    forced = _forced_first_call(model) if force_first else None
    messages: list[BaseMessage] = [SystemMessage(system), HumanMessage(opening)]
    closing = ""
    abandoned = ""
    for turn in range(MAX_INVESTIGATION_TURNS):
        # Only the opening turn is ever constrained, and only where the vendor has a mode
        # for it. From the second turn on, stopping is a judgement the model must be free
        # to make — a forced call on the last turn is a loop that cannot end.
        choice = forced if turn == 0 else None
        try:
            bound = (
                model.bind_tools(definitions, tool_choice=choice)
                if choice
                else model.bind_tools(definitions)
            )
        except (NotImplementedError, TypeError) as error:
            # This provider cannot be asked at all. Not recorded as an abandonment: nothing
            # was ever going to look, which is a different fact and belongs to the caller.
            _log.warning("%s cannot bind tools (%s); investigating was skipped", subject, error)
            return ""
        try:
            # Wrapping the turn rather than the loop is the whole point. The transcript is
            # stateful and `investigator.call` has already written to it, so retrying the
            # loop would record every lookup twice — and a rate limit on turn three should
            # cost a wait, not the two turns already spent.
            reply = call_with_retry(
                # Bound to this turn's runnable and this turn's history, both of which the
                # next turn replaces. A late-binding closure here would retry whatever the
                # loop had moved on to.
                lambda turn_model=bound, history=list(messages): turn_model.invoke(history),
                subject=f"Investigating {subject}",
            )
        except ProviderError as error:
            abandoned = str(error)
            break
        if not reply.tool_calls:
            # No calls is the terminating answer and the only one — the model saying it has
            # seen enough. There is no separate "done" signal, because a model that has to
            # remember to send one will eventually forget, and a turn with neither text nor
            # calls would then hang the loop rather than end it.
            closing = reply.text.strip()
            break
        # Appended as returned, never rebuilt. A vendor that receives tool results without
        # the calls they answer cannot pair them, and Gemini attaches a thought signature to
        # a function call that a reconstructed turn would strip off.
        messages.append(reply)
        # Every call is executed, including the ones after a failure, because a failure is a
        # result here — `call` never raises — and a model that asked three things is owed
        # three answers in the order it asked them.
        messages.extend(
            ToolMessage(
                content=investigator.call(call["name"], call["args"]),
                tool_call_id=call.get("id") or f"{turn}-{index}",
                name=call["name"],
            )
            for index, call in enumerate(reply.tool_calls)
        )
        # Measured over the record rather than over the messages, because the record is what
        # will be stored and shown, and it is the thing the ceiling exists to bound.
        if (
            sum(len(item.result) for item in investigator.transcript)
            >= MAX_INVESTIGATION_CHARACTERS
        ):
            abandoned = "its findings reached the size ceiling, so nothing further was looked up"
            break
    # Told to the investigator on every way out of the loop, before anything is rendered.
    # The rendering is spent on the next request; the investigator is what the caller still
    # holds, so this is the only route these two sentences have to a stored record.
    investigator.conclude(closing, abandoned)
    return _rendered(investigator, closing, abandoned)


def _rendered(investigator: SourceInvestigator, closing: str, abandoned: str) -> str:
    blocks = [
        f"{item.tool}({', '.join(f'{key}={value!r}' for key, value in item.arguments.items())})"
        f"\n{item.result}"
        for item in investigator.transcript
    ]
    if closing:
        blocks.append(closing)
    if abandoned:
        # Named where the findings are, not logged away from them. A caller shown two
        # results and no note would take them for the whole of what could be found.
        blocks.append(f"investigation abandoned: {abandoned}")
    return "\n\n".join(blocks)


def recorded_investigation(
    investigator: SourceInvestigator | None,
    *,
    candidate_id: str,
    withheld: str = "",
    resolved: bool = False,
    atlas_fingerprint: str = "",
    model_identity: str = "",
) -> RecordedInvestigation | None:
    """The transcript as the review will keep it, or None where there is nothing to keep."""

    lookups = (
        ()
        if investigator is None
        else tuple(
            InvestigationLookup(
                item.tool,
                tuple((key, str(value)) for key, value in sorted(item.arguments.items())),
                item.result,
            )
            for item in investigator.transcript
        )
    )
    closing = "" if investigator is None else investigator.closing
    abandoned = "" if investigator is None else investigator.abandoned
    if not lookups and not withheld and not abandoned:
        return None
    return RecordedInvestigation(
        candidate_id=CandidateId(candidate_id),
        lookups=lookups,
        closing=closing,
        withheld=withheld,
        abandoned=abandoned,
        resolved=resolved,
        atlas_fingerprint=atlas_fingerprint,
        prompt_identity=INVESTIGATION_PROMPT_IDENTITY,
        model_identity=model_identity,
    )


