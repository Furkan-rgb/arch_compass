"""The turns a review may spend looking things up, and the record it leaves behind.

A caller gives a model a toolbox and its own question, the model asks the repository, and
this renders what was asked and what came back as one block of text for the structured call
that follows. Two caps bound it — how many turns, and how many characters of findings — and
both exist so an investigation terminates in front of a reader watching a review run.

The loop itself is `langchain.agents.create_agent`. It used to be written out here: sixty
lines appending replies, pairing tool-call ids onto `ToolMessage`s and counting turns, which
is the one part of this that is not about ArchCompass at all. What is about ArchCompass is
everything wrapped around it, and that is what the middleware below holds — the opening turn
being forced where a vendor has a mode for it, the ceiling on what one investigation may
record, and a retry that wraps a *turn* rather than the loop.

That last one is not a detail. `investigator.call` writes to a transcript as it goes, so
retrying the loop would record every lookup twice; a rate limit on turn three has to cost a
wait, not the two turns already spent.

Failure here degrades rather than propagates. Investigating is an improvement to a question,
and the worst outcome allowed is a review that asks the way it asked before: a provider
error becomes a note on the record, and the hinge it could not settle stands.

Separate from `langchain.py` because it is a different kind of call. Everything there is one
structured request against a JSON schema; this is an unconstrained conversation that happens
before one. It deliberately imports nothing from there — both of that module's tool-using
callers import this, and a loop that reached back for a prompt would close the circle.
"""

# `create_agent` is three overloads whose return type is generic in the response format,
# and pyright cannot narrow the unparameterised call into any of them. It executes fine —
# the agent is cast to the one shape this module uses, and the e2e suite drives it against
# a live model. The same gap is suppressed the same way in `workflow/graph.py`.
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import StructuredTool
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
#: review run.
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


def _as_tool(investigator: SourceInvestigator, spec: ToolSpec) -> StructuredTool:
    """One entry of the toolbox as the agent takes it, still answered by the investigator.

    The call goes through `investigator.call` and nowhere else, which is what keeps the
    transcript the single account of what was asked: the agent sees a tool, the review sees
    a recorded lookup, and they are the same call.

    `args_schema` is the spec's own JSON Schema rather than a generated model. It was
    assembled once, in the toolbox, in the shape all three vendors accept, and translating
    it into a Pydantic model here only to have it translated back is a round trip that can
    disagree with itself.
    """

    def answer(**arguments: object) -> str:
        return investigator.call(spec.name, arguments)

    return StructuredTool.from_function(
        func=answer,
        name=spec.name,
        description=spec.description,
        args_schema=dict(spec.parameters),
    )


class _InvestigationBounds(AgentMiddleware[Any, Any]):
    """The two rules the loop cannot express, and the retry that has to wrap one turn.

    Middleware rather than a hand-written loop because each of these is a decision about one
    model call, which is exactly the seam `wrap_model_call` is: what the opening turn is
    allowed to do, whether a refused turn is retried, and whether there is any point asking
    for another one.
    """

    def __init__(self, investigator: SourceInvestigator, *, forced: str | None, subject: str):
        super().__init__()
        self._investigator = investigator
        self._forced = forced
        self._subject = subject
        self._turns = 0
        self.abandoned = ""

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any] | AIMessage:
        self._turns += 1
        # Only the opening turn is ever constrained, and only where the vendor has a mode
        # for it. From the second turn on, stopping is a judgement the model must be free to
        # make — a forced call on the last turn is a loop that cannot end.
        if self._turns == 1 and self._forced:
            request.tool_choice = self._forced
        # Measured over the record rather than over the messages, because the record is what
        # will be stored and shown, and it is the thing the ceiling exists to bound. Checked
        # before asking rather than after answering: once the findings are this large there
        # is nothing a further turn could add that would be kept.
        if self._recorded() >= MAX_INVESTIGATION_CHARACTERS:
            self.abandoned = (
                "its findings reached the size ceiling, so nothing further was looked up"
            )
            return AIMessage("")
        try:
            # Wrapping the turn rather than the run is the whole point. The transcript is
            # stateful and `investigator.call` has already written to it, so retrying the
            # run would record every lookup twice — and a rate limit on turn three should
            # cost a wait, not the two turns already spent.
            return call_with_retry(
                lambda: handler(request), subject=f"Investigating {self._subject}"
            )
        except ProviderError as error:
            # Ended here rather than raised, because an investigation that stopped early is
            # still an investigation: what it did look up stands, and the note says why
            # there is no more of it. An empty answer carries no tool calls, which is how
            # the agent is told there is nothing left to do.
            self.abandoned = str(error)
            return AIMessage("")

    def _recorded(self) -> int:
        return sum(len(item.result) for item in self._investigator.transcript)


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

    bounds = _InvestigationBounds(
        investigator,
        forced=_forced_first_call(model) if force_first else None,
        subject=subject,
    )
    tools = [_as_tool(investigator, spec) for spec in investigator.tools]
    try:
        # Asked of the transport directly, before the agent is built, and this narrowness is
        # deliberate. A provider that cannot be given tools raises here and nowhere else, so
        # catching it here means a `TypeError` from inside a *tool* — a real defect — is not
        # quietly reported as "this model cannot look things up".
        model.bind_tools(tools)
    except (NotImplementedError, TypeError) as error:
        # This provider cannot be asked at all. Not recorded as an abandonment: nothing was
        # ever going to look, which is a different fact and belongs to the caller.
        _log.warning("%s cannot bind tools (%s); investigating was skipped", subject, error)
        return ""

    agent = cast(
        "Runnable[dict[str, object], dict[str, object]]",
        create_agent(
            model,
            tools,
            system_prompt=system,
            middleware=[
                # Ends the run rather than raising, which is what the hand-written loop did
                # when it ran out of turns: conclude with what you have.
                ModelCallLimitMiddleware(
                    run_limit=MAX_INVESTIGATION_TURNS, exit_behavior="end"
                ),
                bounds,
            ],
        ),
    )
    final = agent.invoke({"messages": [HumanMessage(opening)]})

    closing = _closing_text(final)
    # Told to the investigator before anything is rendered. The rendering is spent on the
    # next request; the investigator is what the caller still holds, so this is the only
    # route these two sentences have to a stored record.
    investigator.conclude(closing, bounds.abandoned)
    return _rendered(investigator, closing, bounds.abandoned)


def _closing_text(final: Mapping[str, object]) -> str:
    """What the model said when it stopped calling things, or nothing if it said nothing.

    The last message, and only if it is the model's and carries no calls. A run that ended
    on the turn cap or on a refusal ends on an empty message, and an empty closing is the
    honest record of that: the transcript stands on its own.
    """

    messages = cast("Sequence[object]", final.get("messages") or ())
    last = messages[-1] if messages else None
    if not isinstance(last, AIMessage) or last.tool_calls:
        return ""
    return last.text.strip()


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
