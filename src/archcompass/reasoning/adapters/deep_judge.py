"""One bounded, read-only, tool-enabled judgement per candidate.

Investigation used to be three nodes of the review graph: every candidate was looked at
before anything was judged, hinged findings were looked at again, and whatever survived was
judged a second time. Three model calls for a hinged candidate, a record serialised between
each, and a judgement that could only ever weigh what a previous pass had thought to ask.

This is the same work in one conversation. The judge is handed the dossier, the case and the
policies retrieved for it; it may look at the reviewed repository while it decides; and it
returns the same `FindingOutput` the judge has always returned. Investigation is no longer a
phase — it is what a judgement does when it needs a fact it was not handed.

Three things bound it, and none of them is a quota:

`_Gathering` is a circuit breaker. Its numbers come from measuring what a judgement actually
takes when nothing is pushing it: across 48 natural completions on two providers the most any
one of them spent was 15 model calls, 24 tool calls, 28 seconds and 27,000 characters. The
ceilings sit well above all four. What they exist to catch is the other shape entirely — a
local model that asked for the same grep seventeen times.

Terminalisation is what makes those ceilings safe to set. A breaker that fired used to mean
no verdict at all; here it means the tools are taken away and the same conversation is asked
to finish. Measured on a local model, that turned 2 judgements in 10 into 10 in 10, and on
every run where it fired the verdict matched what a hosted model reached unaided.

`_OneRepair` is the one correction a malformed answer gets. `ToolStrategy`'s own error
handling retries until something else stops it — measured at eight calls against a model
that could not satisfy the schema — so the bound has to be held here.
"""

# `create_agent` is three overloads generic in the response format, and pyright cannot
# narrow the call into any of them. It executes fine — the compiled agent is used through one
# shape only, and the e2e suites drive it against live models. Suppressed the same way in
# `tool_loop.py` and `workflow/graph.py`, for the same reason.
# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.agents.middleware.types import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Finding,
    InvestigationLookup,
    RecordedInvestigation,
    Termination,
)
from archcompass.domain.errors import ProviderError
from archcompass.ports.capabilities import ReviewedSubject
from archcompass.ports.policy_retrieval import RetrievedPolicySet
from archcompass.reasoning.adapters.judge_tools import JudgeToolbox
from archcompass.reasoning.adapters.langchain import (
    FindingOutput,
    finding_from_output,
    judgement_prompt,
    structured_output,
)
from archcompass.retrying import call_with_retry

_log = logging.getLogger(__name__)

#: How many times the model may be asked while it is still gathering. The reserved final
#: call and its one repair sit outside this, so a judgement may reach the provider at most
#: `MAX_JUDGEMENT_GATHERING_MODEL_CALLS + 2` times.
#:
#: Twenty-four against a measured maximum of fifteen. Not the old investigation figure under
#: another name: that one was twelve, and applied here it would have cut short 15% of the
#: judgements that finished on their own.
MAX_JUDGEMENT_GATHERING_MODEL_CALLS = 24

#: How many tools one judgement may call. Forty against a measured maximum of twenty-four.
#: The old lookup budget was twelve and would have cut short 21% of natural completions.
MAX_JUDGEMENT_TOOL_CALLS = 40

#: The ceiling on everything the tools returned, together. Eighty thousand against a measured
#: maximum of twenty-seven thousand. The old ceiling was twelve thousand — calibrated when a
#: tool answer was a short atlas row rather than a file — and would have cut short 31%.
MAX_JUDGEMENT_RECORDED_CHARACTERS = 80_000

#: The outer bound on the whole execution, gathering and terminalisation and repair together.
#: Two minutes against a measured maximum of twenty-eight seconds.
MAX_JUDGEMENT_SECONDS = 120.0

#: How many byte-identical calls of one tool are answered before the run is treated as stuck.
#:
#: The reviewed repository does not change during a judgement and every tool is read-only, so
#: a third identical question cannot have a different answer. Measured: a local model asked
#: for the same grep seventeen times in a row, which none of the count-based breakers above
#: would have caught for another thirty calls.
MAX_IDENTICAL_TOOL_CALLS = 2

JUDGEMENT_PROMPT_IDENTITY = "judge:deep-v1"


class _Gathering(AgentMiddleware[Any, Any]):
    """The circuit breakers, and the record of every tool call the judgement made.

    One middleware for both because they are the same accounting read two ways: what has
    been spent, and what was learned by spending it. `wrap_tool_call` sees every
    model-visible tool whichever middleware injected it, so the filesystem, the atlas and the
    policy corpus are all recorded the same way and none of them can be added later without
    being recorded.
    """

    def __init__(self, subject: ReviewedSubject, *, clock: Callable[[], float] = time.monotonic):
        super().__init__()
        self._subject = subject
        self._clock = clock
        self._started = clock()
        self._asked: dict[str, int] = {}
        self.model_calls = 0
        self.recorded = 0
        self.termination: Termination | None = None
        self.detail = ""

    def _expired(self) -> Termination | None:
        # Already decided, by the tool wrapper below: the run ends on the next turn rather
        # than from inside a tool, because an exception raised there escapes the tools node
        # and takes the whole judgement with it.
        if self.termination is not None:
            return self.termination
        if self.model_calls >= MAX_JUDGEMENT_GATHERING_MODEL_CALLS:
            return Termination.MODEL_CALL_LIMIT
        if len(self._subject.lookups) >= MAX_JUDGEMENT_TOOL_CALLS:
            return Termination.LOOKUP_LIMIT
        if self.recorded >= MAX_JUDGEMENT_RECORDED_CHARACTERS:
            return Termination.INVESTIGATION_SIZE_LIMIT
        if self._clock() - self._started > MAX_JUDGEMENT_SECONDS:
            return Termination.WALL_CLOCK_LIMIT
        return None

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        expired = self._expired()
        if expired is not None:
            self.termination = expired
            # An empty answer carries no tool calls, which is how the agent is told there is
            # nothing left to do. The verdict is not lost: the caller terminalises.
            return AIMessage("")
        self.model_calls += 1
        try:
            # The turn is wrapped, not the run. `lookups` is written as the tools answer, so
            # retrying the run would record every call twice — and a rate limit on the third
            # turn should cost a wait rather than the two turns already spent.
            return call_with_retry(lambda: handler(request), subject="Judging a candidate")
        except ProviderError as error:
            self.termination = Termination.PROVIDER_ERROR
            self.detail = str(error)
            return AIMessage("")

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        call = getattr(request, "tool_call", {}) or {}
        name = str(call.get("name", "?"))
        arguments = cast("Mapping[str, object]", call.get("args", {}) or {})
        signature = _signature(name, arguments)
        self._asked[signature] = self._asked.get(signature, 0) + 1
        if self._asked[signature] > MAX_IDENTICAL_TOOL_CALLS:
            # Not executed a third time, and not recorded: the answer it would return is
            # already in the conversation twice, so running it again would spend a call to
            # learn nothing. Answered rather than raised, because an exception here escapes
            # the tools node and would take the whole judgement with it — the run ends on the
            # next turn instead, where `_expired` sees the termination this just set.
            self.termination = Termination.REPEATED_TOOL_CALL
            return ToolMessage(
                content=(
                    f"You have already asked {name} exactly this, twice, and the repository "
                    "has not changed since. Decide from what you have."
                ),
                tool_call_id=str(call.get("id", "")),
                name=name,
            )
        result = handler(request)
        text = getattr(result, "content", "")
        answer = text if isinstance(text, str) else str(text)
        self.recorded += len(answer)
        self._subject.lookups.append(
            InvestigationLookup(
                name,
                tuple((key, str(value)) for key, value in sorted(arguments.items())),
                answer,
            )
        )
        return result


def _signature(name: str, arguments: Mapping[str, object]) -> str:
    """One tool call as a string that is equal exactly when the question is the same.

    Exact identity and nothing cleverer. Two greps for different patterns are two questions
    however similar they look, and a breaker that guessed at similarity would refuse work
    somebody meant to do.
    """

    return f"{name}\0{json.dumps(arguments, sort_keys=True, default=str)}"


class _OneRepair:
    """A correction for the first malformed judgement, and nothing for the second.

    Stateful because it has to be. `ToolStrategy(handle_errors=...)` calls this on every
    failure and retries whatever it returns, so a plain function is an unbounded loop wearing
    a callback's clothes — measured at eight model calls against a model that could not
    satisfy the schema. Raising the second time is what ends it.

    One per invocation. Sharing one across candidates would spend the repair on whichever
    judgement failed first and refuse every other.
    """

    def __init__(self) -> None:
        self.used = False

    def __call__(self, error: Exception) -> str:
        if self.used:
            raise error
        self.used = True
        return (
            f"That judgement was refused: {error}\n"
            "State the verdict, the reasoning and at least one policy citation once more, "
            "honouring the rule that was broken."
        )


#: What the judgement is told about the dossier it was handed, and about looking further.
#:
#: The three kinds of thing on a candidate are not equally settled and the contract says so.
#: A resolved edge is a resolution; a structural proxy is a deterministic measurement of an
#: imperfect signal and carries its own account of what it cannot see; a derived relation is
#: this or that detector's inference over surfaces. Telling a model they are all "facts not
#: in doubt" would buy fewer lookups by making a weaker claim than the record supports.
JUDGEMENT_TOOL_CONTRACT = """You may look at the repository this candidate was found in
before you decide. It is open to you read-only, at the exact revision the analysis was made
from, through the tools you have been given.

WHAT THE DOSSIER ALREADY SETTLES, AND WHAT IT DOES NOT
Read the candidate before reaching for anything. Three kinds of thing are on it and they are
not equally settled.

Its participants and its relationships are resolutions: the parser found this name, in this
file, bound to that node. Do not spend a lookup rediscovering one unless something you have
seen contradicts it, and say what the contradiction was.

A measurement marked `objective_measurement` counts exactly what its definition says it
counts. A measurement marked `structural_proxy` is a deterministic count of an imperfect
signal, and it carries its own statement of what it cannot see — that statement is not
boilerplate, and where your verdict would turn on what the proxy misses, looking is the right
thing to do.

Looking is the only thing that statement licenses. A proxy reading zero means the thing was
not found by that method; it does not mean the thing is there in a form the method cannot
see. If you go looking for what the proxy might have missed and do not find it, you have
made the zero stronger, not weaker — and if your verdict needs that thing to exist, you have
not established it and must not write as though you had. Evidence about a neighbouring
symbol is evidence about that symbol: another port being substituted in tests says nothing
about whether this one is.

A relationship established by something other than a pass — matching declared method names,
for instance — is a detector's inference over surfaces rather than an edge anyone resolved.
Weigh it as the weaker claim it says it is.

WHEN TO LOOK
Only to settle a concrete uncertainty that bears on THIS candidate's verdict — a premise you
would otherwise have to assume. Using no tools at all is a valid and common outcome: where
the dossier and the policies settle the question, say so and finish. Do not survey the
repository, do not confirm what you already believe, and do not keep looking once the answer
you needed has arrived.

WHAT AN EXCEPTION NEEDS
Every policy here carries exceptions, and an exception is a claim about this candidate like
any other. That a policy's exception *could* apply is not evidence that it does. If your
verdict rests on one, you need positive evidence that its deciding condition holds here —
observed in this repository, about this candidate.

Three things that are context and are not that evidence: how a neighbouring abstraction is
treated, a convention the repository follows generally, and the observation that something
would be substitutable in principle. Each may be worth saying in your reasoning. None of
them settles whether the exception applies to the thing in front of you.

WHEN TO ASK INSTEAD
Reach `held` when the fact your verdict turns on is not in this repository or the recorded
case at all — someone's intent, a commitment to a second case, a contract an external
consumer already depends on. Having tools does not make those answerable. Do not reach
`held` because you have not looked; do not keep looking to avoid it.

The test worth applying to yourself before you finish: name the fact your verdict rests on,
and say where you saw it. If the answer is that you inferred it from what a measurement
cannot see, or from how something else in this repository is done, then you did not see it —
and a verdict resting on it is a guess wearing the clothes of a finding. Ask instead."""


class DeepArchitectureJudge:
    """`ArchitectureJudge` that may read the reviewed repository while it decides.

    Same contract as the judge it replaces: a candidate, a case, the policies retrieved for
    it, and a `Finding` back. What is different is that the model is given tools and a
    conversation rather than one structured call, so a verdict that turns on a fact the
    dossier does not carry can go and get it instead of becoming a question for a person.
    """

    def __init__(
        self,
        model: BaseChatModel,
        toolbox: JudgeToolbox,
        *,
        model_identity: str,
        prompt_identity: str = JUDGEMENT_PROMPT_IDENTITY,
    ) -> None:
        self._model = model
        self._toolbox = toolbox
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
        """One judgement, with or without the repository open.

        `subject` is what carries the repository and the atlas in, and what carries the tool
        trace back out. Without one there is nothing to look at, and this falls back to the
        single structured call the judge has always made — which is what a deterministic
        provider, a review of an atlas that could not be read, and every unit test get.
        """

        del investigation  # the pass that produced it no longer exists
        opening = judgement_prompt(candidate, case, policies)
        if subject is None:
            return self._finding(
                structured_output(
                    self._model,
                    FindingOutput,
                    opening,
                    subject="a review finding",
                    model_identity=self._model_identity,
                ),
                candidate,
                policies,
            )
        subject.model_identity = self._model_identity
        subject.prompt_identity = self._prompt_identity
        offered = self._toolbox.for_subject(subject)
        if not offered.tools:
            # Nothing could be looked at — no atlas to ask, or one an older parser wrote.
            # The judgement still happens, on the dossier alone, and the reason is recorded.
            subject.termination = Termination.NATURAL_END
            subject.retrieval = policies
            return self._finding(
                structured_output(
                    self._model,
                    FindingOutput,
                    opening,
                    subject="a review finding",
                    model_identity=self._model_identity,
                ),
                candidate,
                policies,
            )
        gathering = _Gathering(subject)
        agent = create_agent(
            self._model,
            list(offered.tools),
            # `judgement_prompt` already opens with `JUDGEMENT_INSTRUCTION`, so only the
            # part about having tools belongs here. Stating the whole contract twice made
            # the two copies compete for weight rather than reinforcing each other.
            system_prompt=JUDGEMENT_TOOL_CONTRACT,
            response_format=ToolStrategy(FindingOutput, handle_errors=_OneRepair()),
            middleware=[
                *offered.middleware,
                gathering,
                # A second guard on the same axis, one above the breaker, so a run that gets
                # past `_Gathering` for any reason still cannot go round for ever.
                ModelCallLimitMiddleware(
                    run_limit=MAX_JUDGEMENT_GATHERING_MODEL_CALLS + 1, exit_behavior="end"
                ),
            ],
        )
        final = cast(
            "Mapping[str, object]",
            agent.invoke({"messages": [HumanMessage(opening)]}),
        )
        output = final.get("structured_response")
        if not isinstance(output, FindingOutput):
            output = self._terminalise(final, subject)
        subject.termination = gathering.termination or Termination.NATURAL_END
        # The set the citation check runs against, and the one the review will store: the
        # deterministic retrieval widened by whatever this judgement searched out for itself.
        subject.retrieval = offered.available(policies)
        return self._finding(output, candidate, subject.retrieval)

    def _terminalise(
        self, final: Mapping[str, object], subject: ReviewedSubject
    ) -> FindingOutput:
        """The reserved final call: same conversation, no tools, one answer.

        Not a second judgement. Nothing new is looked at and nothing is re-decided — the
        model is asked to state the verdict it has been working towards, from a conversation
        it has already had. It exists because a circuit breaker that fires must not cost the
        review a finding: measured on a local model, gathering alone reached a verdict twice
        in ten runs and this reached one ten times in ten, agreeing every time with what a
        hosted model reached unaided.
        """

        subject.terminalised = True
        held = cast("Sequence[BaseMessage]", final.get("messages") or ())
        messages: list[BaseMessage] = [
            *held,
            HumanMessage(
                "You have no lookups left. Using only what is already above, state your "
                "judgement now in the required structured form."
            ),
        ]
        return structured_output(
            self._model,
            FindingOutput,
            messages,
            subject="a review finding",
            model_identity=self._model_identity,
        )

    def _finding(
        self, output: FindingOutput, candidate: Candidate, policies: RetrievedPolicySet
    ) -> Finding:
        return finding_from_output(
            output,
            candidate,
            policies,
            model_identity=self._model_identity,
            prompt_identity=self._prompt_identity,
        )
