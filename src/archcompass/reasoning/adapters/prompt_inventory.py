"""Everything a judge sends a model, assembled once so a build-time check can digest it.

A stored finding carries the identity of the prompt that produced it, and
`DeterministicRevisionCalculator` asks whether that stamp still matches what this process
would produce. So the identity has to move whenever the question moves. It is hand-written
— `DEEP_JUDGE_PROMPT_IDENTITY = "judge:deep-v2"` — and hand-written means somebody has to
remember, which measurably does not happen.

Measured by execution rather than by grep, because the two answer differently. Every commit
of `main` up to `769759a` — 400 of them — was loaded out of its own tree with third-party
imports stubbed, so what was compared is the *rendered* prompt: f-strings, `"".join(...)`,
implicit concatenation and constants built from other constants all come out as the model
would read them. The subject was derived, not listed: start at every class whose name ends in
`Judge`, walk each code object's names into the globals it was compiled against, and take
every stretch of prose and every `Field(description=...)` reached, minus docstrings and minus
anything a code object builds an exception out of. That sweep flags 14 commits; a fifteenth,
`63bf4e6`, moved `FILESYSTEM_ROOT_NOTE`, which a judge reaches through its injected toolbox
rather than by name and which no name-walk can see. So: 15 commits moved judge prompt text, 3
moved an identity too, and 12 shipped a changed question under an unchanged stamp. Fifteen is
a floor for the same reason the fifteenth had to be added by hand.

`c8b673a` is the clearest of the twelve — eleven added lines of `WHAT AN EXCEPTION NEEDS`
inside `JUDGEMENT_TOOL_CONTRACT`, under a commit titled "the facts three detectors share,
derived once", with `records.py` untouched. `f6b3a07` is the one that decides the design
below: it rewrote `OneRepair`'s correction and gave the closing turn a `MALFORMED_JUDGEMENT`
branch — model-facing text, inside no constant at all — so a sweep that reads named constants
misses it and a sweep that runs the code does not.

This module is the fact those twelve commits needed and did not have.
`scripts/judge_prompt_check.py` digests what is assembled here and compares it against the
digest recorded beside the identity in `reasoning/records.py`; a mismatch fails `make check`
with a message saying to bump the two together. Nothing here re-judges anything, changes a
stored value, or reaches a provider — the failure is a refusal at zero cost, the same shape as
`SQLiteDatabase._verify_unchanged`, which refuses to open a database whose applied migration
has been edited rather than silently re-running it.

WHAT IS DIGESTED, AND WHY EACH THING IS

Runtime values, not source constants. An earlier design watched four named constants, and
`f6b3a07` is the proof that watching constants is not enough: it replaced `OneRepair`'s
correction wholesale and gave the closing turn a `MALFORMED_JUDGEMENT` branch — model-facing
text, none of it inside any of the four, identity untouched. So the prompts here are *called*
rather than read: `judgement_prompt` builds the opening, `closing_turn` is asked for its answer to
every `Termination`, `OneRepair` is asked for its correction. Editing any of that text moves
the digest with no list to keep in step.

The line drawn is: what the judge assembles and says, plus the offer of tools it puts in front
of the model. A tool's *answer* is on the other side of that line — the atlas's refusals and
`search_policies`'s "No policy in the corpus is about that" are what the repository and the
corpus reply, not what the judge asks. `already_asked` is on this side despite arriving as a
`ToolMessage`, because it is the judge's own circuit breaker speaking over a tool it declined
to run.

TWO DELIBERATE EXCLUSIONS, AND BOTH ARE VENDOR PROSE

The four `deepagents` filesystem tool descriptions — the prose attached to `ls`, `read_file`,
`glob` and `grep` — are not digested. They are the vendor's words, offered to the model by
`FilesystemMiddleware`, and `deepagents>=0.7.8,<0.8` is a floating patch range: hashing them
would mean a lock refresh that reworded a description fails a check about *our* prompts.
`make sync` is `uv sync --locked`, so that drift still surfaces, as a `uv.lock` diff a person
reads.

Which four of them are offered is a different fact and it is digested — see
`_filesystem_tool_offer`. `READ_ONLY_FILESYSTEM` is ArchCompass's own decision that
`write_file`, `edit_file` and `execute` are never built, and leaving the tuple of names out
meant appending `"write_file"` to it put a write tool in front of the model with the check
still green. Measured, before that section existed. The names are ours; the descriptions are
the vendor's; the line runs between them.

The second exclusion is `langchain`'s. `ModelCallLimitMiddleware` is configured
`exit_behavior="end"`, and on the run it ends it appends an `AIMessage` carrying
`_build_limit_exceeded_message(...)` — "Model call limits exceeded: run limit (n/m)" — to the
conversation. `DeepArchitectureJudge._terminalise` then sends the whole message list back for
the reserved final call, so that sentence does reach a model. It is rare: the middleware sits
one above `_Gathering`'s own breaker and only fires on a run that got past it. It is excluded
on the same ground as the tool descriptions and not on the ground that it never happens —
this paragraph exists because the docstring used to say there were two exclusions while
quietly having three.

Say plainly what excluding vendor prose costs, because the two things are not the same. This
is a *check*, and a check may be narrower than the thing it guards — it catches the failure
it was built for, which is forgetting. An *identity* that excluded them would be a different
claim: `judge:deep-v2` would be asserting that two judgements sent the same question when a
vendor upgrade had changed it. The identity does not exclude them; it names the whole prompt,
vendor prose included. The check simply does not watch that part, and this paragraph is where
that is written down.

WHAT IS NOT EXCLUDED, THOUGH IT LOOKS DEAD

`OBSERVATIONS_INSTRUCTION` was excluded here, with an argument that enumerated the judges and
omitted the one that does not drop it. `deep_judge.judge` and `DeterministicJudge.judge` both
`del investigation`, and `workflow/nodes.judge_candidate` passes none — but
`LangChainArchitectureJudge.judge` forwards its argument straight into `judgement_prompt`,
and `ports/capabilities.ArchitectureJudge` documents `investigation` as passed on the second
judgement of the same candidate. The conclusion was true and the reasoning was not, which is
the worst shape a comment can have: a caller reinstating a supported use would have sent
undigested prose under an unchanged `judge:v3`. It is digested now, under `judge:v3` alone —
see `_observations` — and
`tests/unit/test_judge_prompt_check.py::test_a_judge_that_forwards_an_investigation_digests_one`
derives which judges forward it, so a fourth judge that forwards one is caught the day it is
written rather than the day somebody re-reads this paragraph.

WHY THE SET OF JUDGES IS NOT WRITTEN DOWN HERE

`judge_prompt_sections` maps an identity to what that identity sends, and the identities it is
keyed by were once three literals in this file. That is the shape of the bug this module
exists to refuse, rebuilt inside the cure: a fourth judge would have been a fourth prompt that
this file did not know about, and every finding it stamped would have carried an identity no
digest answered for. `stamped_identities` below is the fix — it asks the classes instead,
`scripts/judge_prompt_check.py` refuses a build where a judge stamps an identity this file
does not key, and there is no list to add a judge to.

WHAT THIS CANNOT CATCH

Three things, and none of them is the measured failure. A digest bumped without the identity
beside it passes — the check refuses forgetting, not lying, and buying more than that costs
the content-hash-as-identity design that was rejected for re-judging every stored finding at
the user's expense. A wholly new model-facing branch that nothing here calls is invisible
until it is added below; `closing_turn` is written against the `Termination` enum precisely so
that the most likely such branch is covered on the day it appears rather than the day
somebody remembers.

The third is the one that used to be silent and now is not. Nothing *here* ties a judge's
entry above to what that judge's code actually puts in front of a model, so a system prompt
added to `LangChainArchitectureJudge` tomorrow would leave this file digesting the old set.
That gap is closed one level up, in
`tests/unit/test_judge_prompt_check.py::test_no_judge_sends_anything_the_inventory_does_not_digest`,
which reads each judge class's own source for the arguments it hands `structured_output` and
`create_agent` and fails when one of them names prose this module does not import. It is a
source sweep rather than a value here because the subject has to be *derived* — a declaration
beside the judge would be a second recording of the same fact, which is what this whole line
of work refuses.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from types import ModuleType
from typing import Final, cast

from archcompass.domain import (
    Answer,
    AnswerStatus,
    ArchitectureCase,
    Candidate,
    CandidateId,
    CaseFacet,
    Evidence,
    InvestigationLookup,
    Measurement,
    MetricNature,
    Participant,
    Policy,
    PolicyScope,
    PolicyStrength,
    Question,
    RecordedInvestigation,
    Relationship,
    RetrievalProvenance,
    SourceLocation,
    Termination,
)
from archcompass.ports.policy_retrieval import PolicySelection, RetrievedPolicySet
from archcompass.reasoning.adapters.deep_judge import (
    JUDGEMENT_TOOL_CONTRACT,
    OneRepair,
    already_asked,
    closing_turn,
)
from archcompass.reasoning.adapters.langchain import (
    FindingOutput,
    judgement_prompt,
    observations_text,
    repair_prompt,
)
from archcompass.reasoning.adapters.review_tools import (
    ATLAS_TOOLS,
    FILESYSTEM_ROOT_NOTE,
    READ_ONLY_FILESYSTEM,
    policy_tool,
)
from archcompass.reasoning.ports import ToolSpec
from archcompass.reasoning.records import (
    DEEP_JUDGE_PROMPT_IDENTITY,
    DETERMINISTIC_JUDGE_PROMPT_IDENTITY,
    JUDGE_PROMPT_IDENTITY,
)


@dataclass(frozen=True)
class PromptSection:
    """One stretch of model-facing text, and what to call it in a failure message."""

    label: str
    text: str


def judge_prompt_sections(
    atlas_tools: Sequence[ToolSpec],
) -> Mapping[str, tuple[PromptSection, ...]]:
    """What each judge that carries an identity would send, keyed by that identity.

    `atlas_tools` is passed in rather than built here because `AtlasInvestigator` belongs to
    `analysis`, and nothing in `reasoning` names it at run time either — `bootstrap` wires
    the `InvestigatorSource` and the toolbox reaches it through the port. The build-time
    equivalent of `bootstrap` is `scripts/judge_prompt_check.py`, and that is the one place
    the concrete class is named.
    """

    shared = (*_judgement_openings(), _finding_schema(), _structured_output_repair())
    return {
        # One structured call, no tools, nothing to look at — and the only judge that still
        # renders an investigation into its opening, which is why the observations block is
        # here and not in `shared`. The other two `del` the argument before they build.
        JUDGE_PROMPT_IDENTITY: (*shared, _observations()),
        # The same opening, plus the contract, the offer, and everything the judge says back
        # to a model that is gathering.
        DEEP_JUDGE_PROMPT_IDENTITY: (
            *shared,
            PromptSection("tool-contract", JUDGEMENT_TOOL_CONTRACT),
            _filesystem_tool_offer(),
            PromptSection("filesystem-root-note", FILESYSTEM_ROOT_NOTE),
            _atlas_tool_offer(atlas_tools),
            _policy_search_offer(),
            _one_repair(),
            _stuck_loop(),
            _closings(),
        ),
        # Empty on purpose, and it is an assertion rather than an omission: the stand-in
        # reaches no provider, so the digest of nothing is the correct answer and stops being
        # correct the moment it sends anything. `test_judge_prompt_check` holds the other
        # half — that `deterministic.py` calls neither `structured_output` nor `create_agent`.
        DETERMINISTIC_JUDGE_PROMPT_IDENTITY: (),
    }


def judge_prompt_digests(atlas_tools: Sequence[ToolSpec]) -> Mapping[str, str]:
    """One digest per identity, over that identity's sections in the order above."""

    return {
        identity: section_digest(sections)
        for identity, sections in judge_prompt_sections(atlas_tools).items()
    }


def stamped_identities() -> Mapping[str, str]:
    """Every identity a class in this package stamps a finding with, keyed by where it is written.

    Derived by asking the classes, and that is the whole point. The set used to be read off
    the source with an AST sweep for `identity: ClassVar[str] = NAME`, which matched one
    spelling of one statement: a judge written `identity: ClassVar[str] = "judge:x-v1"` is an
    `ast.Constant` and a judge written `identity = SOME_NAME` is an `ast.Assign`, and that
    sweep saw neither. Demonstrated rather than reasoned about — a fourth judge was added with
    a literal identity and the check reported three judges and exited 0, which is the same
    silence, in the same file, as the one being guarded against.

    An imported class object has no spelling left to evade. Whatever produced the value —
    a literal, a name, an inherited attribute, a computed string — `getattr` reads the string
    the finding will actually carry.

    Class attributes only, and `str` only, which is exactly the set of judges that stamp
    themselves. `SelectedLangChainJudge` and `CachingArchitectureJudge` forward another
    judge's identity through a `prompt_identity` property and are correctly absent; so is
    every `identity` in `domain` that is a property, because a property read off the class is
    a `property` object rather than a string.
    """

    import archcompass

    package = archcompass.__name__
    # Every module, not only `reasoning.adapters`, because "where a judge is allowed to live"
    # is a rule nothing enforces, and a check that assumed one would be a list of directories
    # to forget to extend. An import that fails takes the check down with it, deliberately: a
    # judge inside a module this build cannot import is a judge nothing can verify.
    modules = [
        importlib.import_module(found.name)
        for found in pkgutil.walk_packages(archcompass.__path__, f"{package}.")
    ]
    return identities_stamped_by([archcompass, *modules])


def identities_stamped_by(modules: Iterable[ModuleType]) -> Mapping[str, str]:
    """The same derivation over a given set of modules, so a test can hand it a fourth judge.

    Split out because the sweep above walks the installed package and a test cannot add a
    judge to it. The interesting property — that no way of writing `identity` hides a judge —
    is a property of this function, and this is the seam that lets it be shown rather than
    asserted.
    """

    stamped: dict[str, str] = {}
    for module in modules:
        for name, value in vars(module).items():
            # Defined here rather than imported here, so a judge is reported once, at the
            # place a reader has to go to change it.
            if not isinstance(value, type) or value.__module__ != module.__name__:
                continue
            identity = getattr(value, "identity", None)
            if isinstance(identity, str):
                stamped[f"{module.__name__}.{name}"] = identity
    return stamped


def section_digest(sections: Sequence[PromptSection]) -> str:
    """The digest of one labelled document.

    Labels are hashed with the text so that moving a paragraph between two sections is a
    change, and so that a section removed entirely cannot be cancelled out by one added.
    """

    document = "".join(f"== {section.label} ==\n{section.text}\n" for section in sections)
    return sha256(document.encode("utf-8")).hexdigest()


# The background a judgement is sent against, held still so that only the fixtures the judge
# supplies can move the digest.
#
# Every optional block of `candidate_text` is filled and both natures of `Measurement` are
# present, because the labels, the em-dashes and the `established by` phrasing are all prose
# the model reads and none of it is reachable from a candidate that leaves those blocks out.
# `resolved_by` appears twice for the same reason: `_established_by` renders a resolving pass
# and anything else differently, and a fixture with only one of them would digest half of it.
_CANDIDATE: Final = Candidate(
    CandidateId("candidate_1"),
    pattern="a pattern",
    summary="a summary",
    participants=(
        Participant("ports.Store", "abstraction"),
        Participant("adapters.SqliteStore", "implementation"),
    ),
    evidence=(
        Evidence(
            "with everything on it",
            SourceLocation("ports.py", 1, 2),
            excerpt="class Store:\n    ...",
            note="a caption",
        ),
        Evidence("with nothing on it"),
    ),
    measurements=(
        Measurement("counted", 1, "references", MetricNature.MEASUREMENT, "what it counts"),
        Measurement(
            "proxied",
            0,
            "references",
            MetricNature.STRUCTURAL_PROXY,
            "what it counts",
            "what it cannot see",
        ),
    ),
    relationships=(
        Relationship("adapters.SqliteStore", "ports.Store", "implements", "parse"),
        Relationship("adapters.SqliteStore", "ports.Store", "implements", "name matching"),
    ),
    limitations="what this detection method cannot see",
)

_QUESTION: Final = Question(
    id="question_1",
    text="a question",
    facet=CaseFacet.ASSUMPTION,
    candidate_ids=("candidate_1",),
    round=1,
    equivalence_key="key",
)

# Two cases because `case_text` has two shapes and only one of them is prose. An unanswered
# case is a sentence this repository wrote and a judgement reads; an answered one is JSON,
# whose keys are equally fixture. A single fixture would digest one of the two.
_UNANSWERED_CASE: Final = ArchitectureCase("case_1", 1)
_ANSWERED_CASE: Final = ArchitectureCase(
    "case_1",
    1,
    answers=(
        Answer(
            _QUESTION,
            AnswerStatus.ANSWERED,
            "an answer",
            actor="somebody",
            answered_at=datetime(2026, 1, 1, tzinfo=UTC),
            drafted_by="an agent",
        ),
    )
)

_POLICIES: Final = RetrievedPolicySet(
    candidate_id="candidate_1",
    selections=(
        PolicySelection(
            policy=Policy(
                id="a-policy",
                title="A policy",
                body="The body of a policy.",
                scope=PolicyScope.GENERAL,
                strength=PolicyStrength.GUIDANCE,
                content_hash="hash",
            )
        ),
    ),
    provenance=RetrievalProvenance(
        candidate_id=CandidateId("candidate_1"),
        retriever="fixture",
        version="1",
        corpus_fingerprint="fingerprint",
        selected_policy_ids=("a-policy",),
    ),
)


def _judgement_openings() -> tuple[PromptSection, ...]:
    """The opening every judge sends, built by the function that builds the real one."""

    return (
        PromptSection(
            "judgement-prompt/unanswered-case",
            judgement_prompt(_CANDIDATE, _UNANSWERED_CASE, _POLICIES),
        ),
        PromptSection(
            "judgement-prompt/answered-case",
            judgement_prompt(_CANDIDATE, _ANSWERED_CASE, _POLICIES),
        ),
    )


def _finding_schema() -> PromptSection:
    """The whole JSON schema, not only the field descriptions.

    `structured_output` binds `FindingOutput` with `method="json_schema"`, so the titles, the
    class docstring, the enum members and the `minLength` constraints all reach the model
    alongside the descriptions. Digesting the schema Pydantic actually produces is both
    wider than a walk over `Field(description=...)` and impossible to fall behind.
    """

    return PromptSection(
        "finding-schema",
        json.dumps(FindingOutput.model_json_schema(), indent=1, sort_keys=True),
    )


class _RefusedAnswer:
    """Stands in for the model message a repair quotes back. Only `content` is read."""

    content = "the answer that was refused"


def _structured_output_repair() -> PromptSection:
    """The correction every judge sends after an answer that did not fit the schema.

    Only the single-prompt shape. `repair_prompt` renders the identical correction for a
    conversation and differs only in appending it as a further turn instead of concatenating
    it, so digesting both would digest the same words twice.
    """

    repaired = repair_prompt("", ValueError("a parser complaint"), _RefusedAnswer())
    return PromptSection("structured-output-repair", cast("str", repaired))


#: An investigation shaped so that every branch of `observations_text` renders.
#:
#: One lookup with arguments and one without, because the arguments are joined into the
#: prose; and a withheld record beside a ran-and-stopped one, because those are the two
#: opposite states the paragraph exists to keep apart.
_LOOKUPS: Final = (
    InvestigationLookup("search_code", (("pattern", "Store"),), "one answer"),
    InvestigationLookup("describe_code", (), "another answer"),
)


def _observations() -> PromptSection:
    """What a judgement that is handed an investigation puts in front of the model.

    Digested rather than excluded, and the argument for excluding it is worth writing down
    because it was made and it was wrong. `OBSERVATIONS_INSTRUCTION` looks dead: the deep
    judge and the stand-in both `del investigation`, and `workflow/nodes.judge_candidate`
    passes none. But `LangChainArchitectureJudge.judge` forwards its argument straight into
    `judgement_prompt`, and `ports/capabilities.ArchitectureJudge` documents `investigation`
    as passed on the second judgement of the same candidate — so a caller reinstating it is a
    supported use, not a bug. On that day an excluded block would be undigested prose going
    out under an unchanged `judge:v3`. The cost of digesting it is that editing prose no
    caller currently reaches fails the build, which is the cheap half of the trade: the
    failure says to record the new digest and leave the identity alone, and that is a
    judgement made on purpose rather than by forgetting.

    Every branch, because `observations_text` says four different things about how the
    looking ended and each of them is a sentence the model weighs the lookups by.
    """

    withheld = RecordedInvestigation(CandidateId("candidate_1"), withheld="nothing to ask")
    endings: tuple[Termination | None, ...] = (None, *Termination)
    return PromptSection(
        "observations",
        "\n".join(
            (
                observations_text(withheld),
                *(
                    f"{ending}: "
                    + observations_text(
                        RecordedInvestigation(
                            CandidateId("candidate_1"), _LOOKUPS, termination=ending
                        )
                    )
                    for ending in endings
                ),
            )
        ),
    )


def _filesystem_tool_offer() -> PromptSection:
    """Which of the vendor's filesystem tools the model is offered, by name.

    The names, not the descriptions, and the split is the point. `FilesystemMiddleware` takes
    an allowlist, so `READ_ONLY_FILESYSTEM` is the decision that `write_file`, `edit_file`
    and `execute` are never built — that decision is ArchCompass's own and it belongs in the
    digest. The prose attached to each name is the vendor's, and it stays excluded for the
    reason argued in this module's docstring.

    Without this the check was blind to the one edit here that matters most. Appending
    `"write_file"` to the tuple offers the model a write tool, with fresh vendor prose the
    judgement has never sent, and `make judge-prompt-check` returned 0 — measured, before
    this section existed.
    """

    return PromptSection("filesystem-tool-offer", "\n".join(READ_ONLY_FILESYSTEM))


def _atlas_tool_offer(atlas_tools: Sequence[ToolSpec]) -> PromptSection:
    """The atlas tools a judgement is offered, chosen by the rule the toolbox chooses by.

    `ATLAS_TOOLS` is read from `review_tools` rather than restated, so a tool added to the
    judgement's offer is digested without anything here being edited — which is the same
    reason `closing_turn` is driven off the `Termination` enum.
    """

    offered = {specification.name: specification for specification in atlas_tools}
    return PromptSection(
        "atlas-tools",
        "\n".join(
            _tool_text(
                offered[name].name, offered[name].description, dict(offered[name].parameters)
            )
            for name in ATLAS_TOOLS
            if name in offered
        ),
    )


def _policy_search_offer() -> PromptSection:
    """`search_policies` as the toolbox builds it, read off the built tool.

    Built rather than quoted: the description and the argument schema are written inside
    `policy_tool`, and a copy of them here would be the second recording this whole check
    exists to refuse.
    """

    tool = policy_tool((), [])
    return PromptSection(
        "policy-search-tool",
        _tool_text(tool.name, tool.description, cast("dict[str, object]", tool.args_schema)),
    )


def _tool_text(name: str, description: str, parameters: dict[str, object]) -> str:
    return f"{name}\n{description}\n{json.dumps(parameters, indent=1, sort_keys=True)}"


def _one_repair() -> PromptSection:
    """The one correction a malformed judgement gets from inside the tool loop."""

    return PromptSection("one-repair", OneRepair()(ValueError("a parser complaint")))


def _stuck_loop() -> PromptSection:
    return PromptSection("stuck-loop", already_asked("a_tool"))


def _closings() -> PromptSection:
    """The reserved final call's turn, for every reason a gathering can have ended.

    Driven off `Termination` and `None` rather than off the two branches `closing_turn` happens
    to have today. A termination that arrives with prose of its own is digested the moment it
    exists, which is the property this section is shaped for.
    """

    reasons: tuple[Termination | None, ...] = (None, *Termination)
    return PromptSection(
        "closings",
        "\n".join(f"{reason}: {closing_turn(reason)}" for reason in reasons),
    )
