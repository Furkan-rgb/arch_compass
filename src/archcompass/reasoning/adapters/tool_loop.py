"""The turns a review may spend looking things up, and the record it leaves behind.

A caller gives a model a toolbox and its own question, the model asks the repository, and
what it asked and what came back is recorded as it goes. Four guards bound it, each with one
job: a lookup budget for how much may be explored, a model-call limit for a loop that will
not terminate, a size ceiling for an abnormal run, and the transport's own wall clock. Which
one ended a run is recorded, because "the repository is silent" and "we stopped asking" are
opposite facts about a hinge.

The loop itself is `langchain.agents.create_agent`. It used to be written out here: sixty
lines appending replies, pairing tool-call ids onto `ToolMessage`s and counting turns, which
is the one part of this that is not about ArchCompass at all. What is about ArchCompass is
everything wrapped around it, and that is what the middleware below holds — the opening turn
being forced where a vendor has a mode for it, the lookup budget and the size ceiling, the
account of why a run ended, and a retry that wraps a *turn* rather than the loop.

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
    Termination,
)
from archcompass.domain.errors import ProviderError
from archcompass.reasoning.ports import SourceInvestigator, ToolSpec
from archcompass.retrying import call_with_retry

_log = logging.getLogger(__name__)

#: How many lookups one investigation may make. The budget that bounds *exploration*, and
#: the first of the four guards to fire in ordinary operation.
#:
#: A model turn may carry several tool calls, so this and the turn cap bound different
#: things: how much of the repository was read, against how many times the model was asked.
#: Exploration is what an investigation spends, which is why this is the primary bound.
#:
#: Twelve, measured rather than guessed. Six held candidates were each investigated at
#: ceilings of 8, 10, 12 and 14 against one pinned atlas and one set of policies. Eight and
#: ten measurably lose investigation — three and four of six hinges resolved against four at
#: twelve, and two candidates that finish on their own at twelve are still mid-question at
#: ten. Fourteen buys nothing: its one extra resolution is a candidate that alternates
#: verdict at every ceiling, and two of six runs hit the size guard instead, so fourteen is
#: not really fourteen. Twelve is the first ceiling at which any investigation ends because
#: it has run out of questions rather than out of budget.
#:
#: Approximate by one turn. It is checked between turns, because that is where a run can be
#: ended without discarding a call already paid for — so a turn that issues several calls at
#: once may finish above the ceiling rather than at it.
MAX_INVESTIGATION_LOOKUPS = 12

#: How many times the model may be asked. A runaway guard rather than a budget.
#:
#: Six was the budget, and the reason it stopped being one is measured: with no conclusion to
#: write, an investigation has no reason of its own to stop, and every one of six consecutive
#: investigations ended here rather than at a natural end. A limit that always fires is not
#: bounding a decision, it is making one. What it is for is a loop that will not terminate in
#: front of a reader watching a review run, and for that it must sit clear of the exploration
#: budget rather than under it.
#:
#: Twelve against an observed maximum of nine calls at the chosen lookup budget. The margin
#: is the point: a guard one call above the working range is a co-binding limit wearing a
#: guard's name.
MAX_INVESTIGATION_TURNS = 12

#: The ceiling on what one whole investigation may record, across every result. A guard
#: against an abnormal run rather than a budget: it bounds the product the other two do not,
#: since a model may put several calls in one turn and any one answer may be long.
#:
#: Twelve thousand, raised from ten. At the chosen lookup budget a real investigation reached
#: 9,508 characters — close enough that ordinary variation in source text or tool formatting
#: would have made this the normal limiter, which would quietly demote the lookup budget from
#: primary to nominal. It was already firing first in two of six runs one ceiling higher.
#:
#: Still bounded, and deliberately: this record is stored on every review and projected on
#: every listing of them.
MAX_INVESTIGATION_CHARACTERS = 12_000

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
    """The rules the loop cannot express, and the retry that has to wrap one turn.

    Middleware rather than a hand-written loop because each of these is a decision about one
    model call, which is exactly the seam `wrap_model_call` is: what the opening turn is
    allowed to do, whether there is any point asking for another one, and whether a refused
    turn is retried.

    It also keeps the one thing `ModelCallLimitMiddleware` does not report — why the run
    ended. That middleware ends a run by appending a message of its own and says so nowhere a
    caller can read, so exhausting the budget was indistinguishable from a model that had
    finished asking.
    """

    def __init__(self, investigator: SourceInvestigator, *, forced: str | None, subject: str):
        super().__init__()
        self._investigator = investigator
        self._forced = forced
        self._subject = subject
        self._turns = 0
        #: Why the loop stopped. Set on every path that ends it early; left None while the
        #: run is still going, and read as `NATURAL_END` by the caller only when the agent
        #: returns without one of these having fired.
        self.termination: Termination | None = None
        self.detail = ""
        #: Whether the last turn this middleware saw asked for more tools.
        #:
        #: The discriminator between "the model stopped" and "the model was stopped", and it
        #: has to be this rather than the turn count. `ModelCallLimitMiddleware` refuses in
        #: `before_model`, so the turn it cuts off never reaches here — a model that used its
        #: last allowed call to write a conclusion and a model that used it on one more
        #: lookup both leave the counter at the limit, and only the second was cut short.
        self.asked_for_more = False

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
        # The exploration budget first, because it is the primary bound: a run that has spent
        # it should say so, not report whichever guard happened to be checked first.
        if len(self._investigator.transcript) >= MAX_INVESTIGATION_LOOKUPS:
            self.termination = Termination.LOOKUP_LIMIT
            return AIMessage("")
        # Measured over the record rather than over the messages, because the record is what
        # will be stored and shown, and it is the thing the ceiling exists to bound. Both are
        # checked before asking rather than after answering: once a run is over either line,
        # there is nothing a further turn could add that would be kept.
        if self._recorded() >= MAX_INVESTIGATION_CHARACTERS:
            self.termination = Termination.INVESTIGATION_SIZE_LIMIT
            return AIMessage("")
        try:
            # Wrapping the turn rather than the run is the whole point. The transcript is
            # stateful and `investigator.call` has already written to it, so retrying the
            # run would record every lookup twice — and a rate limit on turn three should
            # cost a wait, not the two turns already spent.
            response = call_with_retry(
                lambda: handler(request), subject=f"Investigating {self._subject}"
            )
            self.asked_for_more = any(
                bool(getattr(message, "tool_calls", None)) for message in response.result
            )
            return response
        except ProviderError as error:
            # Ended here rather than raised, because an investigation that stopped early is
            # still an investigation: what it did look up stands, and the termination says
            # why there is no more of it. An empty answer carries no tool calls, which is
            # how the agent is told there is nothing left to do.
            self.termination = Termination.PROVIDER_ERROR
            self.detail = str(error)
            return AIMessage("")

    def _recorded(self) -> int:
        return sum(len(item.result) for item in self._investigator.transcript)

    def was_cut_off(self) -> bool:
        """Whether the run ended because it ran out of calls rather than out of questions.

        `ModelCallLimitMiddleware` ends the run rather than raising and says so nowhere a
        caller can read, so exhausting the budget looked exactly like a model that had
        finished. Both halves are needed: the count says the budget is spent, and
        `asked_for_more` says the model was mid-sentence when it was. A model that spent its
        last allowed call writing a conclusion reached its own end, and recording that as a
        truncation would tell the judge to treat a complete search as partial.
        """

        return self._turns >= MAX_INVESTIGATION_TURNS and self.asked_for_more


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

    # A run that spent its whole exploration budget spent it, whichever guard noticed. A
    # model that asks one thing per turn reaches the last lookup on its last allowed call, so
    # the call cap fires on the turn the budget would have been noticed — and reporting that
    # as a truncation tells the judge to treat a fully-spent budget as unexplored. Measured:
    # one lookup per call, two, and three all reach twelve; only the report differed.
    spent = len(investigator.transcript) >= MAX_INVESTIGATION_LOOKUPS
    cut_off = bounds.was_cut_off() and not spent
    # Dropped where the run was cut off, because the last message is then not the model's.
    # `ModelCallLimitMiddleware` ends a run by appending an `AIMessage` of its own —
    # "Model call limits exceeded: run limit (6/6)" — and `_closing_text` cannot tell that
    # from a conclusion. It was stored as `RecordedInvestigation.closing` and shown to a
    # reader as the model's own account of what it found.
    closing = "" if cut_off or bounds.termination else _closing_text(final)
    termination = bounds.termination or (
        Termination.MODEL_CALL_LIMIT
        if cut_off
        else Termination.LOOKUP_LIMIT
        if spent
        else Termination.NATURAL_END
    )
    # Told to the investigator before anything is rendered. The rendering is spent on the
    # next request; the investigator is what the caller still holds, so this is the only
    # route these two facts have to a stored record.
    investigator.conclude(closing, termination)
    return _rendered(investigator, closing, termination, bounds.detail)


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


def _rendered(
    investigator: SourceInvestigator,
    closing: str,
    termination: Termination,
    detail: str,
) -> str:
    blocks = [
        f"{item.tool}({', '.join(f'{key}={value!r}' for key, value in item.arguments.items())})"
        f"\n{item.result}"
        for item in investigator.transcript
    ]
    if closing:
        blocks.append(closing)
    if termination is not Termination.NATURAL_END:
        # Named where the findings are, not logged away from them. A caller shown two
        # results and no note would take them for the whole of what could be found.
        blocks.append(
            f"investigation stopped early: {termination.value}"
            + (f" ({detail})" if detail else "")
        )
    return "\n\n".join(blocks)


def recorded_investigation(
    investigator: SourceInvestigator | None,
    *,
    candidate_id: str,
    withheld: str = "",
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
    # `None` only where nothing ran. Anything that started records why it stopped, including
    # a run whose every lookup was refused — an unset termination must never come to mean
    # "ended naturally", because that is a claim about sufficiency this cannot make.
    termination = None if investigator is None else investigator.termination
    if not lookups and not withheld and termination is None:
        return None
    return RecordedInvestigation(
        candidate_id=CandidateId(candidate_id),
        lookups=lookups,
        closing=closing,
        withheld=withheld,
        termination=termination,
        atlas_fingerprint=atlas_fingerprint,
        prompt_identity=INVESTIGATION_PROMPT_IDENTITY,
        model_identity=model_identity,
    )
