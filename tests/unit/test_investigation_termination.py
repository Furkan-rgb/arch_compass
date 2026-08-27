"""Every investigation that runs records why it stopped. `None` means only "not recorded".

The distinction this file guards is the one a judge needs and a reader needs: "the repository
is silent" and "we stopped asking" are opposite facts about a hinge, and before terminations
were recorded they were stored identically — a run that exhausted its six model calls left
the same empty note as one that had finished looking.

`None` survives only for records written before the field existed. It must never come to mean
a natural end, and no path that actually runs may produce it.
"""

from __future__ import annotations

import ast
import itertools
from dataclasses import dataclass
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from archcompass.analysis.investigation import AtlasInvestigator
from archcompass.domain import (
    CandidateId,
    InvestigationLookup,
    RecordedInvestigation,
    Termination,
)

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "archcompass"


class _NoQueries:
    """A query service that answers every lookup the same way, so the record is the subject."""

    def execute(self, atlas: object, query: object) -> object:
        from archcompass.analysis.atlas import AtlasQueryResult

        del atlas
        return AtlasQueryResult(query=query, summary="nothing")  # type: ignore[arg-type]


class _Nothing:
    """A `SourceInvestigator` with an empty transcript, for the bounds tests."""

    @property
    def transcript(self) -> tuple[object, ...]:
        return ()

    @property
    def tools(self) -> tuple[object, ...]:
        """Nothing to offer, which is also nothing that records itself.

        The bounds read this to tell the tools it answers from the ones mounted beside it —
        the filesystem, the policy corpus — because those answer without touching the
        transcript and have to be written into it as they go.
        """

        return ()


_NOTHING = _Nothing()


@dataclass(frozen=True)
class _Judging:
    """What `SelectedLangChainJudge.selection` reports, with only what the key reads in it."""

    model_identity: str
    prompt_identity: str


def _atlas_and_repository():  # type: ignore[no-untyped-def]
    from archcompass.analysis.analyzer import analysis_atlas
    from archcompass.domain import RepositoryAtlas, RepositoryRef

    repository = RepositoryRef("repo", Path("/tmp/repo").resolve(), "branch", "content")
    # Empty of nodes but not of provenance. An atlas that does not name the parser that
    # built it is one this build refuses to read at all, because the alternative was a
    # placeholder that no live parser version can ever equal and therefore a freshness
    # check that failed for ever. These bounds are about termination, not about staleness,
    # so the fixture says what built it and gets on with the question it is asking.
    stamped = RepositoryAtlas(
        "atlas_1",
        repository,
        parser_configuration=(("parser", "test-parser"), ("analysis", "test-config")),
    )
    return analysis_atlas(stamped), repository


_EMPTY_ATLAS, _REPOSITORY = _atlas_and_repository()


def _conclude_calls() -> list[tuple[Path, ast.Call]]:
    """Every `conclude(...)` in the source, found by AST rather than by grep.

    The record's termination can only be set through this one method, so a sweep of its call
    sites is a sweep of every way a live investigation ends.
    """

    found: list[tuple[Path, ast.Call]] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "conclude"
            ):
                found.append((path, node))
    return found


def test_a_concluded_investigation_carries_its_termination_onto_the_record() -> None:
    """The whole path from the setter to the stored record, in one assertion.

    This is the test the AST sweep below cannot be. That sweep audits *callers*; deleting
    `self._termination = termination` from the one implementation, or dropping the
    derivation in `investigate_with_tools`, leaves every caller looking correct and every
    live investigation recording `None` — and both mutations pass a full suite and pyright.
    What catches them is asking the thing that stores the record what it stored.
    """

    from archcompass.reasoning.adapters.tool_loop import recorded_investigation

    investigator = AtlasInvestigator(_NoQueries(), _EMPTY_ATLAS, _REPOSITORY)
    investigator.call("flagged_signals", {})
    investigator.conclude("what I found", Termination.MODEL_CALL_LIMIT)

    record = recorded_investigation(investigator, candidate_id="candidate_1")

    assert record is not None
    assert record.termination is Termination.MODEL_CALL_LIMIT


def test_a_run_the_budget_cut_short_is_told_apart_from_one_that_finished() -> None:
    """Six calls spent on lookups and six spent reaching a conclusion are different runs.

    `ModelCallLimitMiddleware` refuses in `before_model`, so the turn it cuts off never
    reaches this middleware — the counter reads the same either way. Counting alone reported
    a model that used its last allowed call to write a conclusion as truncated, which tells
    the judge to treat a complete search as partial.
    """

    from archcompass.reasoning.adapters.tool_loop import (
        MAX_INVESTIGATION_TURNS,
        _InvestigationBounds,
    )

    bounds = _InvestigationBounds(_NOTHING, forced=None, subject="a test")
    bounds._turns = MAX_INVESTIGATION_TURNS

    bounds.asked_for_more = True
    assert bounds.was_cut_off(), "a run stopped mid-lookup is a truncation"

    bounds.asked_for_more = False
    assert not bounds.was_cut_off(), (
        "a model that spent its last call concluding reached its own end"
    )

    bounds._turns = MAX_INVESTIGATION_TURNS - 1
    bounds.asked_for_more = True
    assert not bounds.was_cut_off(), "budget left means nothing cut it off"


def test_every_way_an_investigation_ends_names_a_termination() -> None:
    """A second, cheaper net: no call site may pass a constant where a state belongs.

    Weaker than the test above and kept for what it covers that no single run can — every
    call site at once, including the ones that are hard to reach on purpose. It is not a
    substitute: a caller passing a computed name satisfies it, so the behavioural test above
    is what actually holds the path together.
    """

    calls = _conclude_calls()
    assert calls, "no `conclude` call was found; this guard now sweeps nothing"

    terminations = {member.name for member in Termination}
    for path, call in calls:
        where = f"{path.relative_to(SOURCE_ROOT)}:{call.lineno}"
        keyword = next((k.value for k in call.keywords if k.arg == "termination"), None)
        reason = keyword or (call.args[1] if len(call.args) >= 2 else None)
        assert reason is not None, f"{where} concludes without saying why it stopped"
        if isinstance(reason, ast.Constant):
            raise AssertionError(f"{where} concludes with the constant {reason.value!r}")
        if isinstance(reason, ast.Attribute):
            assert reason.attr in terminations, f"{where} names no known termination"


def test_a_run_that_looked_at_nothing_still_says_why_it_stopped() -> None:
    """Zero useful lookups is not zero information. The reason is the information."""

    record = RecordedInvestigation(
        candidate_id=CandidateId("candidate_1"),
        lookups=(InvestigationLookup("describe_code", (("qualified_name", "x"),), "no"),),
        termination=Termination.MODEL_CALL_LIMIT,
    )

    assert record.termination is Termination.MODEL_CALL_LIMIT


def test_a_withheld_investigation_cannot_also_have_terminated() -> None:
    """Two opposite accounts of one investigation: it never began, and here is how it ended."""

    with pytest.raises(ValueError, match="never ran"):
        RecordedInvestigation(
            candidate_id=CandidateId("candidate_1"),
            withheld="this review holds no analysed structure",
            termination=Termination.NATURAL_END,
        )


def test_an_unrecorded_termination_is_not_a_natural_end() -> None:
    """The legacy shape, and the one reading of it that must never be taken.

    A stored review from before this field decodes with `termination=None` and its lookups
    intact. Reading that as `NATURAL_END` would tell a judge the search had run to its own
    end, on the strength of a field that simply was not written yet.
    """

    legacy = RecordedInvestigation(
        candidate_id=CandidateId("candidate_1"),
        lookups=(InvestigationLookup("related_code", (("qualified_name", "x"),), "row"),),
    )

    assert legacy.termination is None
    assert legacy.termination is not Termination.NATURAL_END

    from archcompass.reasoning.adapters.langchain import observations_text

    rendered = observations_text(legacy)
    assert "not recorded" in rendered
    assert "of its own accord" not in rendered


def test_a_truncated_investigation_tells_the_judge_it_may_be_incomplete() -> None:
    """Silence after four of six intended lookups is unexplored, not absent."""

    from archcompass.reasoning.adapters.langchain import observations_text

    rendered = observations_text(
        RecordedInvestigation(
            candidate_id=CandidateId("candidate_1"),
            lookups=(InvestigationLookup("read_code", (("qualified_name", "x"),), "src"),),
            termination=Termination.MODEL_CALL_LIMIT,
        )
    )

    assert "cut short" in rendered
    assert "model_call_limit" in rendered
    assert "unexplored rather than as absence" in rendered


def test_the_judge_is_told_whose_choice_the_observations_were() -> None:
    """Detector evidence and model-chosen lookups are two kinds of thing in one prompt.

    They are both allowed to bear on a verdict and neither may be mistaken for the other, so
    the block that carries the lookups says out loud that a model asked for them.
    """

    from archcompass.reasoning.adapters.langchain import observations_text

    rendered = observations_text(
        RecordedInvestigation(
            candidate_id=CandidateId("candidate_1"),
            lookups=(InvestigationLookup("read_code", (("qualified_name", "x"),), "src"),),
            termination=Termination.NATURAL_END,
        )
    )

    assert "chosen by a model rather than by the detector" in rendered
    assert "not evidence" in rendered


def test_the_investigating_models_own_prose_never_reaches_the_judge() -> None:
    """The lossy layer this refactor exists to remove.

    The judge reads what the repository answered, not what a model made of it. A closing
    paragraph is kept for a human reader and has no authority over a verdict, so it must not
    appear in the prompt the verdict is reached from.
    """

    from archcompass.reasoning.adapters.langchain import observations_text

    rendered = observations_text(
        RecordedInvestigation(
            candidate_id=CandidateId("candidate_1"),
            lookups=(InvestigationLookup("read_code", (("qualified_name", "x"),), "src"),),
            closing="I conclude this boundary is deliberate and the finding is not material.",
            termination=Termination.NATURAL_END,
        )
    )

    assert "deliberate" not in rendered
    assert "not material" not in rendered


class _Scripted(GenericFakeChatModel):
    """A model that answers a fixed script, so a whole tool loop can be driven offline.

    `GenericFakeChatModel` is LangChain's own, and `bind_tools` on it is a no-op that keeps
    the agent buildable — which is all this needs. What is under test is the loop's account
    of why it stopped, not the model.
    """

    def bind_tools(self, tools, **kwargs):  # type: ignore[no-untyped-def, override]
        del tools, kwargs
        return self


def _drive(turns: list[AIMessage]) -> tuple[str, Termination]:
    """Run one real `investigate_with_tools` over a scripted model, and read the record."""

    from archcompass.reasoning.adapters.tool_loop import investigate_with_tools

    investigator = AtlasInvestigator(_NoQueries(), _EMPTY_ATLAS, _REPOSITORY)
    investigate_with_tools(
        _Scripted(messages=iter(turns)),
        investigator,
        system="look things up",
        opening="a finding",
        subject="a test",
        force_first=False,
    )
    assert investigator.termination is not None
    return investigator.closing, investigator.termination


#: Counts every scripted turn, so each carries a tool call id of its own.
#:
#: They shared one id at first, and the agent then ran the tool once for the whole script —
#: so a test that meant "ten turns each spending a lookup" was really one lookup and nine
#: turns, and any assertion about the lookup budget passed or failed for the wrong reason.
_ISSUED = itertools.count()


def _lookup_turn(calls: int = 1) -> AIMessage:
    """One scripted turn asking for `calls` lookups.

    More than one because a turn may carry several, and that is what makes the lookup budget
    and the model-call limit different bounds rather than two spellings of one.
    """

    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "flagged_signals",
                "args": {},
                "id": f"call_{next(_ISSUED)}",
                "type": "tool_call",
            }
            for _ in range(calls)
        ],
    )


def test_a_model_that_stops_asking_ends_naturally() -> None:
    """The ordinary end, and the one no counter can recognise on its own."""

    closing, termination = _drive([_lookup_turn(), AIMessage(content="I have what I need.")])

    assert termination is Termination.NATURAL_END
    assert closing == "I have what I need."


def test_a_model_still_looking_when_the_budget_runs_out_is_cut_short() -> None:
    """Every allowed call spent on a lookup: the run was stopped, it did not stop.

    The lookup ceiling is lifted for the duration, so that what ends this run is the turn cap
    and not the exploration budget — the two are separate bounds and this is the turn cap's
    test.
    """

    from archcompass.reasoning.adapters import tool_loop
    from archcompass.reasoning.adapters.tool_loop import MAX_INVESTIGATION_TURNS

    original = tool_loop.MAX_INVESTIGATION_LOOKUPS
    tool_loop.MAX_INVESTIGATION_LOOKUPS = 1_000
    try:
        closing, termination = _drive(
            [_lookup_turn() for _ in range(MAX_INVESTIGATION_TURNS + 2)]
        )
    finally:
        tool_loop.MAX_INVESTIGATION_LOOKUPS = original

    assert termination is Termination.MODEL_CALL_LIMIT
    # And the library's own "Model call limits exceeded" message is not kept as the model's
    # prose. `closing` is shown to a reader as what the pass made of its findings, and
    # `_closing_text` cannot tell a middleware's synthetic message from a conclusion.
    assert closing == "", f"a library message was stored as the model's own: {closing!r}"


def test_a_model_concluding_on_its_last_allowed_call_is_not_a_truncation() -> None:
    """The case the turn counter alone gets wrong, and the reason it is not the counter.

    Six calls where the last is a conclusion, and six where the last is a lookup, leave the
    counter reading exactly the same. Reporting the first as truncated tells the judge to
    treat a search that finished as partial.
    """

    from archcompass.reasoning.adapters.tool_loop import MAX_INVESTIGATION_TURNS

    turns = [_lookup_turn() for _ in range(MAX_INVESTIGATION_TURNS - 1)]
    closing, termination = _drive([*turns, AIMessage(content="Enough.")])

    assert termination is Termination.NATURAL_END
    assert closing == "Enough."


def test_the_second_judgement_is_not_a_cache_hit_on_the_first() -> None:
    """The one way this whole refactor could have been a silent no-op.

    A candidate is judged twice: once on its evidence, and again on what its hinge
    investigation established. Both calls carry the same candidate, the same case and the
    same retrieval — so a key built from those three is identical, the second call is a hit
    on the first, and the judge that was supposed to weigh the observations is never asked.
    The verdict returned would be the one reached before anything was looked up.

    Two different investigations must part too, or one candidate's second judgement is
    served another's.
    """

    from archcompass.domain import ArchitectureCase, Candidate, Participant
    from archcompass.ports.policy_retrieval import RetrievalProvenance, RetrievedPolicySet
    from archcompass.reasoning.cache import CachingArchitectureJudge

    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    case = ArchitectureCase.create()
    policies = RetrievedPolicySet(
        candidate_id=str(candidate.id),
        selections=(),
        provenance=RetrievalProvenance(
            candidate_id=candidate.id,
            retriever="r",
            version="1",
            corpus_fingerprint="f",
            selected_policy_ids=(),
            query_fingerprint="q",
        ),
    )
    judge = CachingArchitectureJudge(
        _NOTHING,  # type: ignore[arg-type]
        _NOTHING,  # type: ignore[arg-type]
        selection=lambda: _Judging("m", "p"),
    )

    def record(result: str) -> RecordedInvestigation:
        return RecordedInvestigation(
            candidate_id=CandidateId(str(candidate.id)),
            lookups=(InvestigationLookup("read_code", (("qualified_name", "x"),), result),),
            termination=Termination.NATURAL_END,
        )

    first = judge.key(candidate, case, policies)
    second = judge.key(candidate, case, policies, record("AAA"))
    other = judge.key(candidate, case, policies, record("BBB"))

    assert first != second, "the post-investigation judgement collides with the first"
    assert second != other, "two different investigations share one cache entry"


def test_the_judgement_prompt_carries_the_observations_it_was_given() -> None:
    """Without this the second judgement is the first one again, at the price of a call.

    The whole of what makes it a *second* judgement is the observations block. A prompt that
    dropped it would still typecheck, still cost a model call, and still return a verdict —
    reached from exactly the inputs that produced the hinge.
    """

    from archcompass.domain import ArchitectureCase, Candidate, Participant
    from archcompass.ports.policy_retrieval import RetrievalProvenance, RetrievedPolicySet
    from archcompass.reasoning.adapters.langchain import judgement_prompt

    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    case = ArchitectureCase.create()
    policies = RetrievedPolicySet(
        candidate_id=str(candidate.id),
        selections=(),
        provenance=RetrievalProvenance(
            candidate_id=candidate.id, retriever="r", version="1",
            corpus_fingerprint="f", selected_policy_ids=(), query_fingerprint="q",
        ),
    )
    record = RecordedInvestigation(
        candidate_id=CandidateId(str(candidate.id)),
        lookups=(
            InvestigationLookup(
                "related_code",
                (("qualified_name", "Port"), ("relation", "implementations")),
                "1 implementation  adapters.SqlPort",
            ),
        ),
        termination=Termination.NATURAL_END,
    )

    without = judgement_prompt(candidate, case, policies)
    with_observations = judgement_prompt(candidate, case, policies, record)

    assert "OBSERVATIONS" not in without, "a first judgement was shown lookups"
    assert "OBSERVATIONS" in with_observations
    # The exact answer, not a summary of it.
    assert "adapters.SqlPort" in with_observations
    assert "related_code" in with_observations


def test_the_exploration_budget_ends_a_run_and_says_so() -> None:
    """The lookup ceiling, which is what bounds how much of a repository was read.

    Distinct from the turn cap because one model turn may carry several tool calls: the two
    bound different things, and only this one bounds exploration. Checked between turns, so a
    turn issuing several calls at once may finish above the ceiling rather than exactly at it
    — the assertion allows for that rather than pretending otherwise.
    """

    from archcompass.reasoning.adapters import tool_loop

    ceiling = 3
    original = tool_loop.MAX_INVESTIGATION_LOOKUPS
    tool_loop.MAX_INVESTIGATION_LOOKUPS = ceiling
    try:
        investigator = AtlasInvestigator(_NoQueries(), _EMPTY_ATLAS, _REPOSITORY)
        tool_loop.investigate_with_tools(
            _Scripted(messages=iter([_lookup_turn() for _ in range(10)])),
            investigator,
            system="look things up",
            opening="a finding",
            subject="a test",
            force_first=False,
        )
    finally:
        tool_loop.MAX_INVESTIGATION_LOOKUPS = original

    assert investigator.termination is Termination.LOOKUP_LIMIT
    assert len(investigator.transcript) >= ceiling
    # And not the runaway guard: with one call per turn the budget is reached first, which is
    # the whole point of it being the primary bound.
    assert len(investigator.transcript) < tool_loop.MAX_INVESTIGATION_TURNS


class _Verbose:
    """A query service whose answers are long, for reaching the size guard on purpose."""

    def __init__(self, characters: int) -> None:
        self._characters = characters

    def execute(self, atlas: object, query: object) -> object:
        from archcompass.analysis.atlas import AtlasQueryResult

        del atlas
        return AtlasQueryResult(query=query, summary="y" * self._characters)  # type: ignore[arg-type]


def _drive_against(
    queries: object, turns: list[AIMessage]
) -> tuple[AtlasInvestigator, Termination]:
    from archcompass.reasoning.adapters.tool_loop import investigate_with_tools

    investigator = AtlasInvestigator(queries, _EMPTY_ATLAS, _REPOSITORY)  # type: ignore[arg-type]
    investigate_with_tools(
        _Scripted(messages=iter(turns)),
        investigator,
        system="look things up",
        opening="a finding",
        subject="a test",
        force_first=False,
    )
    assert investigator.termination is not None
    return investigator, investigator.termination


def test_which_bound_wins_is_decided_and_not_incidental() -> None:
    """Four guards, one job each, and an order between them that must not drift.

        lookup budget          what an investigation is allowed to explore
        model-call limit       a loop that will not terminate
        investigation size     an abnormal run, not a long one
        wall clock             the outer operational guard, outside this loop

    Each is asserted by making it the one that can fire, because a constant that quietly
    changes role is the failure here — the turn cap was the exploration budget for a while,
    and nothing said so. The size guard is checked last on purpose: it must not fire in the
    ordinary range, and the value that makes that true is the one measured against a real
    investigation that reached 9,508 characters.
    """

    from archcompass.reasoning.adapters import tool_loop

    was = (
        tool_loop.MAX_INVESTIGATION_LOOKUPS,
        tool_loop.MAX_INVESTIGATION_TURNS,
        tool_loop.MAX_INVESTIGATION_CHARACTERS,
    )
    try:
        # The lookup budget binds first when every guard is otherwise out of reach.
        tool_loop.MAX_INVESTIGATION_LOOKUPS = 3
        tool_loop.MAX_INVESTIGATION_TURNS = 50
        tool_loop.MAX_INVESTIGATION_CHARACTERS = 1_000_000
        _, termination = _drive_against(_NoQueries(), [_lookup_turn() for _ in range(30)])
        assert termination is Termination.LOOKUP_LIMIT

        # The runaway guard binds only when the exploration budget cannot.
        tool_loop.MAX_INVESTIGATION_LOOKUPS = 1_000
        tool_loop.MAX_INVESTIGATION_TURNS = 4
        _, termination = _drive_against(_NoQueries(), [_lookup_turn() for _ in range(30)])
        assert termination is Termination.MODEL_CALL_LIMIT

        # The size guard binds on volume rather than on count: three short lookups are within
        # every other bound, and one long one is not.
        tool_loop.MAX_INVESTIGATION_LOOKUPS = 1_000
        tool_loop.MAX_INVESTIGATION_TURNS = 50
        tool_loop.MAX_INVESTIGATION_CHARACTERS = 500
        _, termination = _drive_against(_Verbose(400), [_lookup_turn() for _ in range(30)])
        assert termination is Termination.INVESTIGATION_SIZE_LIMIT
    finally:
        (
            tool_loop.MAX_INVESTIGATION_LOOKUPS,
            tool_loop.MAX_INVESTIGATION_TURNS,
            tool_loop.MAX_INVESTIGATION_CHARACTERS,
        ) = was


def test_the_shipped_guards_let_the_whole_lookup_budget_be_reached() -> None:
    """Behaviour, not arithmetic: can a realistic investigation spend what it was given?

    An earlier version of this asserted `MAX_INVESTIGATION_TURNS >= MAX_INVESTIGATION_LOOKUPS`,
    which compares different units. A turn may carry several tool calls, so a turn cap below
    the lookup budget is not automatically wrong — and a turn cap above it is not automatically
    safe either, since a model that asks one thing at a time needs a call per lookup.

    So this runs the loop at the shipped values across three calling shapes — one lookup per
    turn, two and three. One per turn is the worst case for the model-call guard; a local model
    measured on a real repository averaged closer to one and a half. What must hold in every
    shape is that the whole budget is spendable and that the run says so. Any of these numbers
    may be retuned on later evidence; what may not change silently is which guard normally
    stops an investigation.
    """

    from archcompass.reasoning.adapters import tool_loop

    budget = tool_loop.MAX_INVESTIGATION_LOOKUPS
    for per_turn in (1, 2, 3):
        investigator, termination = _drive_against(
            _NoQueries(),
            [_lookup_turn(per_turn) for _ in range(budget * 3)],
        )
        assert len(investigator.transcript) >= budget, (
            f"at {per_turn} lookup(s) a turn, something stopped the run before its budget"
        )
        assert termination is Termination.LOOKUP_LIMIT, (
            f"at {per_turn} lookup(s) a turn, a spent budget was reported as "
            f"{termination.value}"
        )
