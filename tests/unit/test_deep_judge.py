"""One judgement, bounded, and what it is allowed to do on the way to a verdict.

The bounds here are circuit breakers rather than budgets: what they exist to catch is an
execution that has stopped making progress, not one that is taking its time. So most of these
are about the shapes that are *not* progress — the same question asked again, a malformed
answer offered twice — and about the rule that firing a breaker must never cost the review a
finding.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Participant,
    RepositoryAtlas,
    RepositoryRef,
    RetrievalProvenance,
    Termination,
)
from archcompass.ports.capabilities import ReviewedSubject
from archcompass.ports.policy_retrieval import RetrievedPolicySet
from archcompass.reasoning.adapters.deep_judge import (
    MAX_IDENTICAL_TOOL_CALLS,
    DeepArchitectureJudge,
)
from archcompass.reasoning.adapters.judge_tools import OfferedTools

_REPOSITORY = RepositoryRef(
    id="r", path=Path("/tmp/reviewed"), branch_id="b", content_id="fingerprint"
)


def _candidate() -> Candidate:
    return Candidate.identified(
        pattern="sole_implementation",
        summary="ports.Sink is implemented only by sinks.FileSink.",
        participants=(
            Participant("ports.Sink", "Declares the abstraction."),
            Participant("sinks.FileSink", "The only implementation of it."),
        ),
    )


def _policies(candidate: Candidate) -> RetrievedPolicySet:
    return RetrievedPolicySet(
        candidate_id=str(candidate.id),
        selections=(),
        provenance=RetrievalProvenance(
            candidate_id=candidate.id,
            retriever="test",
            version="1",
            corpus_fingerprint="f",
            selected_policy_ids=("delay-premature-abstraction",),
        ),
    )


def _subject() -> ReviewedSubject:
    return ReviewedSubject(
        repository=_REPOSITORY,
        atlas=RepositoryAtlas(id="a", repository=_REPOSITORY),
    )


class _Structured(GenericFakeChatModel):
    """A model that answers the structured call and never asks for a tool."""

    verdict: str = "cleared"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        del tools, kwargs
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        del schema, kwargs
        from langchain_core.runnables import RunnableLambda

        from archcompass.reasoning.adapters.langchain import FindingOutput

        def answer(_: object) -> dict[str, object]:
            return {
                "parsed": FindingOutput(
                    verdict=self.verdict,  # type: ignore[arg-type]
                    reasoning="The port is substituted in tests.",
                    policy_bearings=[
                        {  # type: ignore[list-item]
                            "policy_id": "delay-premature-abstraction",
                            "reasoning": "Its exception applies.",
                        }
                    ],
                ),
                "parsing_error": None,
                "raw": AIMessage(content=""),
            }

        return RunnableLambda(answer)


class _Scripted(GenericFakeChatModel):
    """A model answering a fixed script, so a whole judgement runs offline."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        del tools, kwargs
        return self


class _AlwaysGreps(_Structured):
    """A model that asks for the same grep for ever. Observed, not invented.

    It answers the terminal structured call like any other model, because that half is not
    what is broken about it: what is broken is that it never stops asking.
    """

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "grep",
                                "args": {"pattern": "next_revision", "path": "tests"},
                                "id": "call",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )


class _MalformedTwice(_Structured):
    """A model that twice answers in a shape the contract refuses. Observed, not invented.

    `gemini-3.5-flash-lite` recommended a response on a verdict that may not carry one, read
    the correction, and did it again. It answers the terminal structured call like any other
    model, because a schema a model cannot satisfy while it is also holding a tool loop open
    is often one it can satisfy on its own.
    """

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "FindingOutput",
                                "args": {
                                    "verdict": "cleared",
                                    "reasoning": "The port is substituted in tests.",
                                    "policy_bearings": [
                                        {
                                            "policy_id": "delay-premature-abstraction",
                                            "reasoning": "Its exception applies.",
                                        }
                                    ],
                                    # The rule no JSON schema can carry, and the one a
                                    # hosted model broke twice in a row.
                                    "recommended_response": "Fold the port into its caller.",
                                },
                                "id": "call",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )


class _Toolbox:
    """Offers one recording tool, so a test can count what was actually executed."""

    def __init__(self, *, answer: str = "one match") -> None:
        self.executed: list[dict[str, object]] = []
        self._answer = answer

    def for_subject(self, subject: ReviewedSubject) -> OfferedTools:
        del subject

        def grep(pattern: str, path: str = "") -> str:
            self.executed.append({"pattern": pattern, "path": path})
            return self._answer

        return OfferedTools(
            tools=(
                StructuredTool.from_function(
                    func=grep,
                    name="grep",
                    description="Search the reviewed source.",
                    args_schema={
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string"},
                            "path": {"type": "string"},
                        },
                        "required": ["pattern"],
                        "additionalProperties": False,
                    },
                ),
            )
        )


class _NoToolbox:
    def for_subject(self, subject: ReviewedSubject) -> OfferedTools:
        del subject
        return OfferedTools(withheld="This review holds no analysed structure.")


def test_the_same_question_asked_a_third_time_ends_the_gathering() -> None:
    """The stuck loop the counters miss, and the one that was actually observed.

    A local model asked for the same grep seventeen times. Every count-based ceiling would
    have let it run another thirty calls first, because seventeen identical questions look
    exactly like seventeen questions. The reviewed repository does not change while it is
    being judged and every tool is read-only, so the third identical answer cannot differ
    from the first two — that is a loop, not a search.
    """

    toolbox = _Toolbox()
    subject = _subject()
    finding = _judge_with(_AlwaysGreps(messages=iter([])), toolbox).judge(
        _candidate(), ArchitectureCase.create(), _policies(_candidate()), subject=subject
    )

    assert subject.termination is Termination.REPEATED_TOOL_CALL
    # Answered twice, and the third request never reached the tool at all: running it again
    # would spend a call to learn what is already in the conversation.
    assert len(toolbox.executed) == MAX_IDENTICAL_TOOL_CALLS
    assert len(subject.lookups) == MAX_IDENTICAL_TOOL_CALLS
    # And the review still gets a finding, which is the whole reason a breaker may be tight.
    assert subject.terminalised
    assert finding.verdict


def test_a_judgement_refused_twice_costs_a_candidate_and_not_the_review() -> None:
    """The one refusal that used to escape, out of the one place a breaker cannot reach.

    `_OneRepair` raises on the second malformed answer, and that raise comes from inside the
    model node — past the agent, past `judge`, and out through the graph, which fails the
    whole review after every other candidate has already been judged and paid for. Observed
    on `gemini-3.5-flash-lite`, which twice put a recommended response on a verdict that may
    not carry one. It is a malformed answer, so it ends the gathering, like every other
    ending that is not a verdict.
    """

    subject = _subject()
    candidate = _candidate()

    finding = _judge_with(_MalformedTwice(messages=iter([])), _Toolbox()).judge(
        candidate, ArchitectureCase.create(), _policies(candidate), subject=subject
    )

    assert subject.termination is Termination.MALFORMED_JUDGEMENT
    # Corrected once and refused the second time, rather than retried until something else
    # stopped it.
    assert subject.terminalised
    # And the review still gets a finding — the whole point of ending rather than raising.
    assert finding.verdict.value == "cleared"
    assert finding.recommended_response is None


def _judge_with(model: Any, toolbox: Any) -> DeepArchitectureJudge:
    return DeepArchitectureJudge(model, toolbox, model_identity="fake:scripted")


def test_a_judgement_with_nothing_to_look_at_still_reaches_a_verdict() -> None:
    """No atlas to ask means the dossier alone, not a review missing a finding."""

    subject = _subject()
    candidate = _candidate()
    model = _Structured(messages=iter([]), verdict="cleared")

    finding = _judge_with(model, _NoToolbox()).judge(
        candidate, ArchitectureCase.create(), _policies(candidate), subject=subject
    )

    assert finding.verdict.value == "cleared"
    assert subject.lookups == []
    assert subject.termination is Termination.NATURAL_END


def test_a_malformed_judgement_is_corrected_once_and_then_refused() -> None:
    """`ToolStrategy`'s own handling retries until something else stops it.

    Measured at eight model calls against a model that could not satisfy the schema — which
    is not a repair, it is a loop with a message attached. One correction naming what was
    broken is worth a call; a model that cannot honour a contract having just been shown the
    contract and its own violation of it will not honour it on the fourth attempt.
    """

    from archcompass.reasoning.adapters.deep_judge import _OneRepair

    repair = _OneRepair()

    first = repair(ValueError("a held finding must name the fact its verdict turns on"))

    assert "refused" in first
    assert "must name the fact" in first
    try:
        repair(ValueError("again"))
    except ValueError as raised:
        assert str(raised) == "again"
    else:  # pragma: no cover - the point of the test
        raise AssertionError("the second failure must not be corrected")


def test_every_tool_a_judgement_calls_is_recorded_whoever_offered_it() -> None:
    """One recorder over every model-visible tool, not one per source.

    The filesystem tools come from a vendor's middleware and the atlas tools are ours, so a
    trace assembled from our own toolbox would silently omit every file the judgement read —
    and a verdict resting on an unrecorded read is one nobody can check.
    """

    toolbox = _Toolbox(answer="src/sinks.py:12: class FileSink")
    subject = _subject()

    _judge_with(_AlwaysGreps(messages=iter([])), toolbox).judge(
        _candidate(), ArchitectureCase.create(), _policies(_candidate()), subject=subject
    )

    assert [item.tool for item in subject.lookups] == ["grep", "grep"]
    assert subject.lookups[0].arguments == (("path", "tests"), ("pattern", "next_revision"))
    assert "class FileSink" in subject.lookups[0].result


def test_a_judgement_that_searched_for_a_policy_may_cite_it_and_says_so() -> None:
    """The citable set is what was put in front of this judgement, never the whole corpus."""

    from archcompass.domain import Policy, PolicyScope, PolicyStrength

    found = Policy(
        id="contain-dependencies",
        title="Contain dependencies",
        body="Keep a vendor's vocabulary out of the domain.",
        scope=PolicyScope.GENERAL,
        strength=PolicyStrength.GUIDANCE,
        content_hash="h",
    )
    offered = OfferedTools(searched=[found, found])
    candidate = _candidate()

    widened = offered.available(_policies(candidate))

    # Deduplicated, first-seen order, and the provenance says which half is which.
    assert widened.provenance.selected_policy_ids == (
        "delay-premature-abstraction",
        "contain-dependencies",
    )
    assert ("judge_searched", "contain-dependencies") in widened.provenance.metadata
    # And the identity moved, so a finding that searched cannot claim the retrieval of one
    # that did not.
    assert widened.provenance.identity != _policies(candidate).provenance.identity
