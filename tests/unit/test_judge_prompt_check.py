"""The build-time refusal that keeps a prompt identity true.

`DEEP_JUDGE_PROMPT_IDENTITY` is hand-written and a stored finding carries it, so a prompt
that moves under an unchanged stamp is a verdict that never gets revisited. Measured on this
repository's own history, that is not a hypothetical: over the 400 commits of `main` at
`769759a`, 15 moved judge prompt text and 3 moved an identity with it, leaving 12 changed
questions shipped under a stamp that says nothing changed. `prompt_inventory`'s docstring
says how those were counted.

`scripts/judge_prompt_check.py --check` is the refusal. Most of these tests are about whether
it can fail, which is the first question about a guard: they break a prompt on purpose and
ask the check what it says. Two of them are about the opposite — a re-flow and a relocation
that leave the rendered prompt identical have to stay green, because a guard that cries on a
rename is a guard somebody deletes.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import ClassVar, Final

import pytest

from archcompass.reasoning.adapters import deep_judge, prompt_inventory
from archcompass.reasoning.adapters.prompt_inventory import (
    PromptSection,
    identities_stamped_by,
    judge_prompt_sections,
    section_digest,
    stamped_identities,
)
from archcompass.reasoning.records import (
    DEEP_JUDGE_PROMPT_IDENTITY,
    JUDGE_PROMPT_DIGESTS,
    JUDGE_PROMPT_IDENTITY,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "src" / "archcompass"
SCRIPT = ROOT / "scripts" / "judge_prompt_check.py"


def _script() -> ModuleType:
    """The check, loaded from the path `make check` runs it by.

    By path rather than by import, because `scripts/` is not a package and making it one to
    suit a test would be the test changing the thing it is testing. Loading the same file the
    Makefile names is what keeps this honest — a check rewritten in the test would pass while
    the one CI runs was broken.
    """

    specification = importlib.util.spec_from_file_location("judge_prompt_check", SCRIPT)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture(name="script")
def script_fixture() -> ModuleType:
    return _script()


def test_every_recorded_digest_still_answers_for_the_prompt_beside_it(
    script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """The working tree's own state: green, or somebody moved a prompt and did not say so."""

    assert script.check() is True
    assert "match the digests recorded" in capsys.readouterr().out


def test_the_check_covers_every_judge_that_stamps_an_identity() -> None:
    """A fourth judge is a fourth prompt, and it must arrive with a digest.

    The judges come from `stamped_identities`, which imports them, so this is a claim about
    every judge that exists rather than about the three anybody remembered. It replaced an
    AST sweep for `identity: ClassVar[str] = NAME`, which was a claim about one spelling of
    one statement and let a fourth judge through — see the two tests below.
    """

    sections = judge_prompt_sections(_script().atlas_tool_specifications())
    assert set(stamped_identities().values()) == set(sections) == set(JUDGE_PROMPT_DIGESTS)


def _synthetic_judges(directory: Path, source: str) -> ModuleType:
    """A judge module written to disk and imported, so the real derivations can be run on it.

    On disk rather than `exec`'d, because both derivations under test read a judge two ways —
    `stamped_identities` imports the class and the send sweep reads the class's own source
    through `inspect.getsource` — and only a module with a file behind it answers both. It is
    written under pytest's `tmp_path`, never into the repository.
    """

    path = directory / "synthetic_judges.py"
    path.write_text(source, encoding="utf-8")
    specification = importlib.util.spec_from_file_location(path.stem, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    # Registered because `inspect.getsource` and the sweep both reach the module through
    # `sys.modules[cls.__module__]`, exactly as they do for a real judge.
    sys.modules[path.stem] = module
    try:
        specification.loader.exec_module(module)
    except BaseException:
        del sys.modules[path.stem]
        raise
    return module


#: A fourth and fifth judge, written the two ways the sweep this replaced could not see.
#:
#: `LiteralIdentityJudge` writes its identity as a string — an `ast.Constant`, where the old
#: sweep required an `ast.Name`. `AssignedIdentityJudge` writes it without an annotation — an
#: `ast.Assign`, where the old sweep required an `ast.AnnAssign`. Neither is exotic; the
#: second is what a person writes when they are not thinking about `ClassVar`.
#:
#: They also send, which is what the second derivation is shown against: one adds a system
#: prompt under a name of its own, and one writes the prose straight into the call.
_A_FOURTH_JUDGE = '''
from typing import ClassVar

from archcompass.reasoning.adapters.langchain import (
    FindingOutput,
    judgement_prompt,
    structured_output,
)

_AN_IDENTITY = "judge:assigned-v1"
A_SYSTEM_PROMPT = "Answer as a staff engineer would."


class LiteralIdentityJudge:
    identity: ClassVar[str] = "judge:literal-v1"

    def judge(self, model, candidate, case, policies):
        opening = A_SYSTEM_PROMPT + judgement_prompt(candidate, case, policies)
        return structured_output(
            model, FindingOutput, opening, subject="a review finding"
        )


class AssignedIdentityJudge:
    identity = _AN_IDENTITY

    def judge(self, model, candidate, case, policies):
        return structured_output(
            model,
            FindingOutput,
            "Be terse. " + judgement_prompt(candidate, case, policies),
            subject="a review finding",
        )
'''


def test_no_spelling_of_an_identity_hides_a_judge_from_the_check(tmp_path: Path) -> None:
    """The hole that was demonstrated, closed and demonstrated closed.

    A fourth judge used to be able to exist un-digested: the check reported three judges and
    exited 0 with a fourth in the tree, because the sweep matched one statement shape and the
    fourth judge was written in another. `stamped_identities` reads the imported class, which
    has no spelling left, and this proves it on the two shapes that got past the old one.
    """

    module = _synthetic_judges(tmp_path, _A_FOURTH_JUDGE)
    try:
        stamped = identities_stamped_by([module])
    finally:
        del sys.modules[module.__name__]

    assert set(stamped.values()) == {"judge:literal-v1", "judge:assigned-v1"}


def test_a_judge_whose_identity_nothing_digests_stops_the_build(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Finding the fourth judge is only worth something if the build then refuses.

    Patched at the script rather than run against a judge really added to `src/`, because a
    test that writes a judge into the package it is testing leaves one behind when it fails.
    That the derivation finds such a judge is the test above; that the check refuses one is
    this.
    """

    script = _script()
    monkeypatch.setattr(
        script,
        "stamped_identities",
        lambda: {"reasoning.adapters.fourth.FourthJudge": "judge:fourth-v1"},
    )

    assert script.check() is False
    reported = capsys.readouterr().err
    assert "judge:fourth-v1" in reported
    assert "FourthJudge" in reported
    assert "prompt_inventory.py" in reported


def test_the_stand_in_judge_reaches_no_provider_so_its_empty_digest_is_true() -> None:
    """The other half of recording `sha256("")` for `judge:deterministic-v1`.

    The inventory asserts that this judge sends nothing by having nothing to assemble, and an
    assertion made by absence cannot fail on its own. This is what makes it fail: the stand-in
    calls neither of the two functions in this package that reach a model.
    """

    source = (SOURCE_ROOT / "reasoning" / "adapters" / "deterministic.py").read_text(
        encoding="utf-8"
    )
    reaches_a_model = [
        node.func.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"structured_output", "create_agent"}
    ]
    assert not reaches_a_model


#: One way of moving model-facing text, per thing the deep judge sends.
#:
#: Each entry patches the name `prompt_inventory` looks up when it assembles that section, so
#: it exercises the real path from "somebody edited this" to "the digest moved". Together they
#: are the answer to `f6b3a07`, the commit that changed `OneRepair` and the closing turn
#: without touching any of the four constants an earlier design watched: two of the rows below
#: are those two, and they fail if either stops being digested.
_MOVED_PROMPTS: tuple[tuple[str, str, object], ...] = (
    (
        "judgement-prompt/unanswered-case",
        "judgement_prompt",
        lambda *arguments, **keywords: "a different question entirely",
    ),
    ("tool-contract", "JUDGEMENT_TOOL_CONTRACT", "a different contract"),
    ("filesystem-root-note", "FILESYSTEM_ROOT_NOTE", "a different note"),
    ("one-repair", "OneRepair", lambda: (lambda error: "a different correction")),
    ("stuck-loop", "already_asked", lambda name: "a different refusal"),
    ("closings", "closing_turn", lambda why: "a different closing"),
    (
        "structured-output-repair",
        "repair_prompt",
        lambda *arguments: "a different repair",
    ),
)


@pytest.mark.parametrize(
    ("label", "attribute", "replacement"),
    _MOVED_PROMPTS,
    ids=[label for label, _, _ in _MOVED_PROMPTS],
)
def test_moving_any_of_what_the_judge_sends_fails_the_check(
    label: str,
    attribute: str,
    replacement: object,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _script()
    tools = script.atlas_tool_specifications()
    before = judge_prompt_sections(tools)[DEEP_JUDGE_PROMPT_IDENTITY]

    monkeypatch.setattr(prompt_inventory, attribute, replacement)
    after = judge_prompt_sections(tools)[DEEP_JUDGE_PROMPT_IDENTITY]

    assert _labelled(after, label) != _labelled(before, label), (
        f"patching {attribute} did not move the {label} section; it is not being digested"
    )
    assert section_digest(after) != section_digest(before)
    assert script.check() is False
    assert DEEP_JUDGE_PROMPT_IDENTITY in capsys.readouterr().err


def _labelled(sections: Sequence[PromptSection], label: str) -> str:
    found = [section.text for section in sections if section.label == label]
    assert found, f"the {label} section is no longer assembled, so nothing digests it"
    return found[0]


def test_the_atlas_tool_offer_is_digested() -> None:
    """The tool descriptions, which arrive through a port rather than from a constant.

    Separated from the sweep above because there is no name in `prompt_inventory` to patch:
    the specifications are handed in by the script, so this moves one of them instead.
    """

    script = _script()
    tools = list(script.atlas_tool_specifications())
    assert tools, "the atlas offered no tools; the digest would cover nothing"
    before = section_digest(judge_prompt_sections(tools)[DEEP_JUDGE_PROMPT_IDENTITY])

    moved = [replace(tools[0], description="a different description"), *tools[1:]]
    after = section_digest(judge_prompt_sections(moved)[DEEP_JUDGE_PROMPT_IDENTITY])

    assert after != before


def test_the_policy_search_tool_is_digested(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script()
    tools = script.atlas_tool_specifications()
    before = section_digest(judge_prompt_sections(tools)[DEEP_JUDGE_PROMPT_IDENTITY])

    monkeypatch.setattr(
        prompt_inventory, "policy_tool", lambda corpus, searched: _FlatTool()
    )
    after = section_digest(judge_prompt_sections(tools)[DEEP_JUDGE_PROMPT_IDENTITY])

    assert after != before


class _FlatTool:
    """The shape `_policy_search_offer` reads off a built tool, and nothing else."""

    name = "search_policies"
    description = "a different description"
    args_schema: ClassVar[dict[str, object]] = {}


def test_the_finding_schema_the_model_is_handed_is_digested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A field description is prompt, even though it lives on a Pydantic model.

    `structured_output` binds `FindingOutput` with `method="json_schema"`, so this text is
    sent with every judgement. It has been edited without an identity moving before.
    """

    script = _script()
    tools = script.atlas_tool_specifications()
    before = section_digest(judge_prompt_sections(tools)[DEEP_JUDGE_PROMPT_IDENTITY])

    monkeypatch.setattr(
        prompt_inventory.FindingOutput,
        "model_json_schema",
        classmethod(lambda cls, **keywords: {"description": "a different schema"}),
    )
    after = section_digest(judge_prompt_sections(tools)[DEEP_JUDGE_PROMPT_IDENTITY])

    assert after != before



def test_the_failure_says_which_judge_moved_and_what_to_do_about_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A guard that fires with "digest mismatch" costs the reader the whole investigation."""

    script = _script()
    monkeypatch.setattr(prompt_inventory, "JUDGEMENT_TOOL_CONTRACT", "a different contract")

    assert script.main(["--check"]) == 1
    reported = capsys.readouterr().err

    assert DEEP_JUDGE_PROMPT_IDENTITY in reported
    # The section that moved, named, so the reader is not diffing eleven of them by hand.
    assert "tool-contract" in reported
    assert "src/archcompass/reasoning/records.py" in reported
    assert "Bump both, together" in reported


def test_a_digest_recorded_for_a_judge_that_no_longer_exists_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other direction: a renamed judge leaving its old digest behind.

    Left alone, that entry is a recording nothing computes — it would sit in `records.py`
    reading like a guarantee and guarding nothing at all.
    """

    script = _script()
    monkeypatch.setattr(
        script, "JUDGE_PROMPT_DIGESTS", {**JUDGE_PROMPT_DIGESTS, "judge:retired-v1": "0" * 64}
    )

    assert script.check() is False
    assert "judge:retired-v1" in capsys.readouterr().err


def test_the_print_mode_changes_nothing(script: ModuleType) -> None:
    """The write half of the split stops at printing, on purpose.

    A mode that edited `records.py` would be a command somebody runs to make the build green
    without reading why it went red, and reading why is the entire product of this check.
    """

    before = (SOURCE_ROOT / "reasoning" / "records.py").read_bytes()

    assert script.main([]) == 0

    assert (SOURCE_ROOT / "reasoning" / "records.py").read_bytes() == before


def _makefile_targets() -> Iterator[str]:
    for line in (ROOT / "Makefile").read_text(encoding="utf-8").splitlines():
        if line.startswith("check:"):
            yield from line.removeprefix("check:").split()


def test_make_check_runs_it() -> None:
    """A check outside `make check` is a check nobody runs.

    Named here rather than trusted, because the gated targets in this Makefile are exactly
    the ones `AGENTS.md` warns will not tell you they are broken.
    """

    assert "judge-prompt-check" in set(_makefile_targets())


def test_the_target_invokes_the_script_this_file_tests() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "scripts/judge_prompt_check.py --check" in makefile


# ---------------------------------------------------------------------------------------
# WHAT A JUDGE SENDS, DERIVED FROM THE JUDGE
#
# Everything above asks whether the inventory's digests are still true. This asks the prior
# question: whether the inventory is still digesting the right *set*. `judge_prompt_sections`
# writes out which sections each identity sends, and until this sweep existed nothing tied
# that mapping to the judge classes — give `LangChainArchitectureJudge` a system prompt
# tomorrow and the inventory would go on digesting the old set, silently, which is the exact
# defect this whole guard is about rebuilt inside the guard.
#
# So the subject is derived rather than listed, the same way `test_boundaries.py` finds
# readers by their shape instead of naming them. The judges come from `stamped_identities`,
# and for each of them this reads that class's own source for what it hands the two functions
# in this package that reach a provider.


#: The two functions that reach a provider, and which of their arguments the model reads.
#:
#: The pair is not chosen here. The test above named for the stand-in judge's empty digest
#: already treats "calls neither `structured_output` nor `create_agent`" as the whole
#: meaning of "sends nothing to a model", and this is the same claim used in the other
#: direction — if that definition is ever wrong, both tests are wrong together rather than
#: one of them quietly being narrower than the other.
#:
#: Which arguments, and why not all of them. `structured_output(model, schema, prompt, *,
#: subject, model_identity)` puts the schema in front of the model as a JSON schema and the
#: prompt as the request; `subject` and `model_identity` are for log lines and never leave
#: the process. `create_agent` sends its tools' descriptions, its system prompt, the response
#: format's schema and repair, and whatever its middleware injects — `middleware` is in this
#: set on purpose, because injecting text is what `FilesystemMiddleware` is *for*, and a
#: system prompt smuggled through a middleware would otherwise be the same silence again.
_SENDS: Final[Mapping[str, tuple[frozenset[int], frozenset[str]]]] = {
    "structured_output": (frozenset({1, 2}), frozenset({"schema", "prompt"})),
    "create_agent": (
        frozenset({1}),
        frozenset({"tools", "system_prompt", "response_format", "middleware"}),
    ),
}

#: What a judge hands a send that the inventory does not import, and what digests it instead.
#:
#: One entry, and it has to name a section the inventory really holds — the assertion below
#: checks the value as well as the key, so this cannot be used to wave anything away. It is
#: also checked for staleness: an entry naming something no judge sends any more fails, so
#: this list cannot quietly outlive the code it excuses.
#:
#: `_Gathering` is the deep judge's circuit breaker, handed to `create_agent` as middleware.
#: The only thing it ever says to a model is `already_asked`, over a tool call it declined to
#: run, and `prompt_inventory` digests `already_asked` directly. The alternative was following
#: the sweep one hop into our own callables, which collects every name in the followed class —
#: `InvestigationLookup`, four budget constants, `Termination` — and buys noise rather than
#: coverage.
_COVERED_ELSEWHERE: Final[Mapping[str, str]] = {
    "_Gathering": "already_asked",
}


def _class_node(module: ModuleType, name: str) -> ast.ClassDef:
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is not written in {module.__name__}")


def _bindings(node: ast.ClassDef) -> dict[str, list[ast.expr]]:
    """Every name the class binds, so a send handed a local is followed to what built it.

    `opening = judgement_prompt(...)` and then `structured_output(model, schema, opening)` is
    how the deep judge is actually written, and a sweep that stopped at `opening` would see a
    local variable and nothing else.

    The whole class rather than one function at a time, and that is what carries the closing
    turn: `_terminalise` sends `messages`, built from `held`, built from `final` — and `final`
    is its parameter, bound by `judge` two lines before it hands it over. Say what that is
    honestly. It is name matching over one class, not dataflow: the chase works because a
    caller and a callee in this class spell the same value the same way, and it would not
    follow a value renamed on the way in. The same limit `test_boundaries.py` writes down
    about its own chase, and it is enough here for the same reason — the alternative is a
    dataflow analysis in a test file, which is worth more than it costs to nobody.

    Every binding of a name is kept and not the last one, because the question is which names
    can reach a send rather than which value arrives. A name assigned a prompt on one branch
    and something harmless on another would otherwise be answered for by whichever line the
    walk reached second, which is not an answer at all.
    """

    bound: dict[str, list[ast.expr]] = {}
    for statement in ast.walk(node):
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(statement, ast.Assign):
            targets, value = list(statement.targets), statement.value
        elif isinstance(statement, ast.AnnAssign | ast.NamedExpr):
            targets, value = [statement.target], statement.value
        if value is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                bound.setdefault(target.id, []).append(value)
    return bound


def _send_positions(node: ast.ClassDef) -> list[ast.expr]:
    positions: list[ast.expr] = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            continue
        sent = _SENDS.get(call.func.id)
        if sent is None:
            continue
        indices, keywords = sent
        positions.extend(
            argument for index, argument in enumerate(call.args) if index in indices
        )
        positions.extend(
            keyword.value for keyword in call.keywords if keyword.arg in keywords
        )
    return positions


def _written_in_place(expression: ast.expr) -> set[str]:
    """String literals a send reaches without passing through some other call's arguments.

    A prompt typed at the call site — `structured_output(model, schema, "Be terse. " +
    judgement_prompt(...))` — has no name for `prompt_inventory` to import, so nothing could
    ever digest it. It has to be caught, and it is caught here rather than by looking at every
    string in the expression, because the expression also contains strings that are plainly
    not prompts: `cast("Sequence[BaseMessage]", ...)` is a type written as text, and
    `ModelCallLimitMiddleware(exit_behavior="end")` is a vendor enum value.

    The line between them is whether the string is passed to something. A string handed to a
    callee is that callee's argument and the callee answers for it — if the callee is ours its
    own prose lives at module level and its name is checked below, and if it is the vendor's
    it is the exclusion `prompt_inventory` argues for. A string that is not handed to anything
    is going to the model as it stands.
    """

    if isinstance(expression, ast.Constant):
        return {ast.unparse(expression)} if isinstance(expression.value, str) else set()
    if isinstance(expression, ast.Call):
        return set()
    found: set[str] = set()
    for child in ast.iter_child_nodes(expression):
        if isinstance(child, ast.expr):
            found |= _written_in_place(child)
    return found


_MISSING: Final = object()


def _could_carry_text(module: ModuleType, name: str) -> bool:
    """Whether a name a send reached is one of ours and could put text in front of a model.

    Three exclusions, each of them a rule rather than an entry on a list.

    A name the module does not bind is a parameter or a local — `self`, `candidate`, `why` —
    and holds a value this repository's source cannot show anyone.

    A name whose value came from another distribution is the vendor's: `HumanMessage`,
    `ToolStrategy`, `ModelCallLimitMiddleware`, `cast`. This is the principle `prompt_inventory`
    argues for when it declines to digest `deepagents`' four filesystem tool descriptions —
    hashing prose a floating patch range can move would fail a check about *our* prompts — and
    not the same rule: that exclusion names four descriptions, and this one is every name from
    outside the package. Neither is derived from the other, so a reader widening one should
    read the other. What keeps them from drifting into a real disagreement is that both are
    narrower than what the identity claims, which `prompt_inventory` says out loud.

    A name holding a number is a budget and not a sentence — `MAX_JUDGEMENT_GATHERING_MODEL_CALLS`
    reaches `create_agent`'s middleware and says nothing to anybody.
    """

    value = getattr(module, name, _MISSING)
    if value is _MISSING:
        return False
    origin = getattr(value, "__module__", "")
    if origin and not origin.startswith("archcompass"):
        return False
    return isinstance(value, str) or callable(value)


def what_a_judge_sends(cls: type) -> set[str]:
    """Every name and in-place string that reaches a model from one judge class."""

    module = sys.modules[cls.__module__]
    node = _class_node(module, cls.__name__)
    bound = _bindings(node)
    pending = _send_positions(node)
    followed: set[str] = set()
    sent: set[str] = set()
    while pending:
        expression = pending.pop()
        sent |= _written_in_place(expression)
        for name in {
            node.id for node in ast.walk(expression) if isinstance(node, ast.Name)
        }:
            if name in followed:
                continue
            followed.add(name)
            if name in bound:
                pending.extend(bound[name])
            elif _could_carry_text(module, name):
                sent.add(name)
    return sent


def what_the_inventory_digests() -> set[str]:
    """The names `prompt_inventory` imports from the modules that hold prompt text.

    Its imports rather than a list, so a section added to the inventory is covered by this
    test without anything here being edited — the same reason `_atlas_tool_offer` reads
    `ATLAS_TOOLS` instead of restating it.

    Narrowed to `reasoning.adapters` because the rest of what the inventory imports is the
    fixture a prompt is rendered against — `Candidate`, `Policy`, `Termination` — and counting
    those as "digested" would let a judge send a domain type's prose unnoticed. A judge that
    starts sending prose from another feature fails here, which is the right noise: the cure
    is a section in the inventory and a deliberate widening of this line, not a silent pass.
    """

    prompts = "archcompass.reasoning.adapters"
    return {
        alias.asname or alias.name
        for node in ast.walk(ast.parse(inspect.getsource(prompt_inventory)))
        if isinstance(node, ast.ImportFrom)
        if node.module and node.module.startswith(prompts)
        for alias in node.names
    }


def _judge_classes() -> list[type]:
    """The judges, resolved from the same derivation the check refuses on."""

    classes: list[type] = []
    for where in stamped_identities():
        module_name, _, class_name = where.rpartition(".")
        classes.append(getattr(sys.modules[module_name], class_name))
    return classes


def test_no_judge_sends_anything_the_inventory_does_not_digest() -> None:
    """The mapping in `judge_prompt_sections` answers for what the judge classes really do.

    This is the half that a hand-written inventory cannot have. `judge_prompt_sections` says
    the deep judge sends a tool contract, a root note, two tool offers, a repair, a stuck-loop
    refusal and the closings — and said so because somebody wrote it down. Nothing made that
    true. A `system_prompt=` added to either judge, a second prompt constant concatenated onto
    the opening, or a prompt typed straight into the call, all moved what the model reads and
    left the inventory digesting the set it was told about.

    Derived in the direction that matters and only that direction. A name the inventory
    digests but no judge sends is not asserted here, because that is a digest which is merely
    wider than it needs to be — `already_asked` and `FILESYSTEM_ROOT_NOTE` are both genuinely
    in it and reach a model through a middleware and a toolbox rather than through a send.
    Sending something nothing digests is the measured failure; digesting something nothing
    sends is a conservative digest.
    """

    digested = what_the_inventory_digests()
    undigested = {
        f"{cls.__module__}.{cls.__name__} sends {name}"
        for cls in _judge_classes()
        for name in what_a_judge_sends(cls) - digested - set(_COVERED_ELSEWHERE)
    }

    assert not undigested, (
        "these reach a model from a judge and nothing in prompt_inventory digests them; "
        "add a section for each, or record why it is covered in _COVERED_ELSEWHERE: "
        f"{sorted(undigested)}"
    )


def test_the_sweep_sees_what_the_judges_actually_send_today() -> None:
    """The sweep passing is worth nothing if it is finding nothing.

    A derivation that silently resolved to the empty set would satisfy the test above for ever
    while covering no judge at all — which is the failure mode of every guard in this series.
    So the two judges that do send are named here with what they send, and the stand-in is
    named with the empty set that is its whole claim.
    """

    sent = {cls.__name__: what_a_judge_sends(cls) for cls in _judge_classes()}

    assert sent["LangChainArchitectureJudge"] == {"FindingOutput", "judgement_prompt"}
    assert sent["DeepArchitectureJudge"] == {
        "FindingOutput",
        "JUDGEMENT_TOOL_CONTRACT",
        "OneRepair",
        "_Gathering",
        "closing_turn",
        "judgement_prompt",
    }
    assert sent["DeterministicJudge"] == set()


def test_nothing_is_excused_that_is_not_digested_under_another_name() -> None:
    """`_COVERED_ELSEWHERE` cannot be a place to put things to make the sweep quiet.

    Both directions. An entry has to point at a section the inventory really holds, and it has
    to still be something a judge really sends — otherwise the list outlives the code it
    excuses and reads as a guarantee about a middleware nobody uses any more.
    """

    digested = what_the_inventory_digests()
    still_sent = {name for cls in _judge_classes() for name in what_a_judge_sends(cls)}

    assert set(_COVERED_ELSEWHERE) <= still_sent
    assert set(_COVERED_ELSEWHERE.values()) <= digested


def test_a_judge_that_sends_something_undigested_is_caught(tmp_path: Path) -> None:
    """The sweep, run against judges written to send prose nothing could digest.

    Two shapes, because they fail through two different parts of it. `LiteralIdentityJudge`
    concatenates a module-level `A_SYSTEM_PROMPT` onto the opening, which is what "give this
    judge a system prompt tomorrow" actually looks like in a diff. `AssignedIdentityJudge`
    types the prose into the call, where there is no name to find at all — caught by
    `_written_in_place` rather than by the name sweep.
    """

    module = _synthetic_judges(tmp_path, _A_FOURTH_JUDGE)
    try:
        named = what_a_judge_sends(module.LiteralIdentityJudge)
        in_place = what_a_judge_sends(module.AssignedIdentityJudge)
    finally:
        del sys.modules[module.__name__]

    digested = what_the_inventory_digests()
    assert named - digested == {"A_SYSTEM_PROMPT"}
    assert in_place - digested == {"'Be terse. '"}
    # And what they send that *is* digested is still recognised, so the sweep is discriminating
    # rather than simply suspicious of everything.
    assert {"FindingOutput", "judgement_prompt"} <= named & digested


def test_the_filesystem_tools_the_model_is_offered_are_digested(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Which of the vendor's tools the model gets is our decision, so the check watches it.

    The vendor's *prose* is excluded and stays excluded; `READ_ONLY_FILESYSTEM` is the
    allowlist `FilesystemMiddleware` is built from, and it is the line between a judgement
    that can only read and one that can write. Before this was digested, appending
    `"write_file"` to it offered the model a write tool and `judge-prompt-check` returned 0 —
    run by hand, on the real target, which is why the row below is that exact edit.
    """

    script = _script()
    tools = script.atlas_tool_specifications()
    before = judge_prompt_sections(tools)[DEEP_JUDGE_PROMPT_IDENTITY]

    monkeypatch.setattr(
        prompt_inventory, "READ_ONLY_FILESYSTEM", ("ls", "read_file", "glob", "grep", "write_file")
    )
    after = judge_prompt_sections(tools)[DEEP_JUDGE_PROMPT_IDENTITY]

    assert _labelled(after, "filesystem-tool-offer") != _labelled(before, "filesystem-tool-offer")
    assert script.check() is False
    assert DEEP_JUDGE_PROMPT_IDENTITY in capsys.readouterr().err


def _judge_method(cls: type) -> ast.FunctionDef:
    for node in ast.walk(_class_node(sys.modules[cls.__module__], cls.__name__)):
        if isinstance(node, ast.FunctionDef) and node.name == "judge":
            return node
    raise AssertionError(f"{cls.__name__} has no judge method to read")


def _forwards_an_investigation(cls: type) -> bool:
    """Whether this judge hands its `investigation` argument on rather than dropping it.

    Read off the method rather than declared beside it, so a judge nobody has written yet is
    covered: `del investigation` is how the two judges that ignore it say so, and passing the
    name into any call is how the one that honours it says so. A judge doing both would be
    reported as forwarding, which is the safe direction — the digest would then be wider than
    the prompt rather than narrower.
    """

    node = _judge_method(cls)
    dropped = any(
        isinstance(target, ast.Name) and target.id == "investigation"
        for statement in ast.walk(node)
        if isinstance(statement, ast.Delete)
        for target in statement.targets
    )
    forwarded = any(
        isinstance(argument, ast.Name) and argument.id == "investigation"
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        for argument in [*call.args, *(keyword.value for keyword in call.keywords)]
    )
    return forwarded and not dropped


def test_a_judge_that_forwards_an_investigation_digests_one() -> None:
    """The observations block is only dead prose for the judges that drop the argument.

    `prompt_inventory` used to exclude `OBSERVATIONS_INSTRUCTION` on the ground that no
    judgement is ever handed a `RecordedInvestigation`. True today, and true only because
    `workflow/nodes.judge_candidate` passes none — while `LangChainArchitectureJudge` forwards
    whatever it is given into `judgement_prompt` and `ports/capabilities.ArchitectureJudge`
    documents that argument as passed on the second judgement of the same candidate. The day
    a caller uses it, an excluded block is undigested prose under an unchanged `judge:v3`.

    Derived from each judge's own `judge` method rather than from the three we have, because
    the hazard is a fourth judge written the same way. A judge that forwards must have the
    section; the two that `del` it are free of it, and that asymmetry is what keeps
    `judge:deep-v2` from claiming text the deep judge cannot send.
    """

    sections = judge_prompt_sections(_script().atlas_tool_specifications())
    forwarding = {
        cls.identity for cls in _judge_classes() if _forwards_an_investigation(cls)
    }

    # Not vacuous: exactly one judge forwards today, and it is the plain one.
    assert forwarding == {"judge:v3"}
    for identity in forwarding:
        assert any(section.label == "observations" for section in sections[identity]), (
            f"{identity} renders an investigation into its prompt and nothing digests it"
        )


def test_moving_the_observations_prose_fails_the_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """And the section has to be able to fail, not merely to exist.

    The section is asserted to move, not only the check to go red: with the section deleted
    the check is red anyway, from the digest that no longer matches, and a test that asked
    only for red would pass while nothing digested the observations at all.
    """

    script = _script()
    tools = script.atlas_tool_specifications()
    before = judge_prompt_sections(tools)[JUDGE_PROMPT_IDENTITY]

    monkeypatch.setattr(
        prompt_inventory, "observations_text", lambda investigation: "a different heading"
    )
    after = judge_prompt_sections(tools)[JUDGE_PROMPT_IDENTITY]

    assert _labelled(after, "observations") != _labelled(before, "observations")
    assert script.check() is False
    assert JUDGE_PROMPT_IDENTITY in capsys.readouterr().err


def _assignment_source(source: str, name: str) -> str:
    """The exact text of one module-level assignment, as it is written in the file today."""

    for node in ast.parse(source).body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            return segment
    raise AssertionError(f"{name} is not a module-level assignment any more")


def _reflowed(name: str, text: str) -> str:
    """The same string, spelled as one implicitly concatenated literal per line.

    A real re-flow, of the kind a person does when a paragraph is rewrapped or a triple-quoted
    block is turned into a parenthesised one: every byte the model reads is unchanged and
    every line of the file is different.
    """

    lines = "\n".join(f"    {line!r}" for line in text.splitlines(keepends=True))
    return f"{name} = (\n{lines}\n)"


@pytest.fixture(name="reflowed_deep_judge")
def reflowed_deep_judge_fixture(tmp_path: Path) -> Iterator[ModuleType]:
    """`deep_judge.py`, re-flowed and imported as a module of its own, under `tmp_path`.

    A copy on disk rather than an `exec` of one statement, because the two properties below
    are about a file being edited and about text living somewhere else — and a module object
    with its own name and its own source is what makes either claim real rather than a
    tautology about `sha256`.
    """

    source = inspect.getsource(deep_judge)
    original = _assignment_source(source, "JUDGEMENT_TOOL_CONTRACT")
    replacement = _reflowed("JUDGEMENT_TOOL_CONTRACT", deep_judge.JUDGEMENT_TOOL_CONTRACT)
    assert replacement != original, "the re-flow left the source unchanged; it proves nothing"

    path = tmp_path / "reflowed_deep_judge.py"
    path.write_text(source.replace(original, replacement), encoding="utf-8")
    specification = importlib.util.spec_from_file_location(path.stem, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[path.stem] = module
    try:
        specification.loader.exec_module(module)
        yield module
    finally:
        del sys.modules[path.stem]


def test_a_source_reflow_that_renders_the_same_text_stays_green(
    reflowed_deep_judge: ModuleType, monkeypatch: pytest.MonkeyPatch, script: ModuleType
) -> None:
    """Rewriting how a prompt is spelled, without changing what it says, must not fire.

    This is the half of the guard that keeps it alive. A check that went red when somebody
    rewrapped a string would be a check that gets a `# noqa` comment and then gets deleted,
    and it would teach the wrong lesson besides: the identity is a claim about what the model
    was asked, not about how the file was laid out.

    Two assertions, because a re-flow demonstration on its own could not fail. Any digest
    taken over the value is blind to layout by construction, so the demonstration below shows
    the property and proves nothing about the implementation. The one thing that could take
    it away is the inventory reading source instead of calling code, so that is asserted
    directly and derived from the module: no `inspect.getsource`, no `__file__`, no reading a
    file. An implementation that hashed a file would fail here and pass everything else.
    """

    reads_source = {"getsource", "getsourcelines", "getsourcefile", "getfile", "read_text"}
    named = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(ast.parse(inspect.getsource(prompt_inventory)))
        if isinstance(node, (ast.Attribute, ast.Name))
    }
    assert not named & (reads_source | {"__file__"}), (
        "the inventory is reading source text; the digest has stopped being over what the "
        "model is sent and a re-flow will now fail the build"
    )

    assert reflowed_deep_judge.JUDGEMENT_TOOL_CONTRACT == deep_judge.JUDGEMENT_TOOL_CONTRACT
    assert inspect.getsource(reflowed_deep_judge) != inspect.getsource(deep_judge)

    tools = script.atlas_tool_specifications()
    before = section_digest(judge_prompt_sections(tools)[DEEP_JUDGE_PROMPT_IDENTITY])
    monkeypatch.setattr(
        prompt_inventory,
        "JUDGEMENT_TOOL_CONTRACT",
        reflowed_deep_judge.JUDGEMENT_TOOL_CONTRACT,
    )

    assert section_digest(judge_prompt_sections(tools)[DEEP_JUDGE_PROMPT_IDENTITY]) == before
    assert script.check() is True


def test_a_cross_module_relocation_with_the_same_text_stays_green(
    reflowed_deep_judge: ModuleType, monkeypatch: pytest.MonkeyPatch, script: ModuleType
) -> None:
    """Moving prompt text to another module, unchanged, must not fire either.

    The four things the deep judge's own module holds are taken from a module of a different
    name and pointed at the inventory. Every one of them is a distinct object defined in a
    different file, and the model reads exactly the same words — which is the whole test of
    whether this digest is over the prompt or over where the prompt happens to live.
    """

    tools = script.atlas_tool_specifications()
    before = section_digest(judge_prompt_sections(tools)[DEEP_JUDGE_PROMPT_IDENTITY])

    for name in ("JUDGEMENT_TOOL_CONTRACT", "OneRepair", "already_asked", "closing_turn"):
        relocated = getattr(reflowed_deep_judge, name)
        assert relocated is not getattr(deep_judge, name), f"{name} was not really relocated"
        monkeypatch.setattr(prompt_inventory, name, relocated)

    assert section_digest(judge_prompt_sections(tools)[DEEP_JUDGE_PROMPT_IDENTITY]) == before
    assert script.check() is True
