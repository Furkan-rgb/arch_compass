"""Refuse a build whose judge prompts have moved without their identity moving with them.

A stored finding carries the identity of the prompt that produced it, and the delta asks
whether that stamp still matches what this process would produce. The identity is hand-
written, so keeping it true depends on somebody remembering. Measured over the history of
`main` at `769759a` — 400 commits, each tree executed and its judge prompts rendered, not
read: 15 moved judge prompt text, 3 moved an identity too, and 12 shipped a changed question
under an unchanged stamp. Every finding judged under one of those twelve reads as unmoved for
ever. `prompt_inventory`'s docstring says how that was counted and what it could not see.

This is what those twelve needed. It digests what each judge sends a model — assembled by
`reasoning/adapters/prompt_inventory.py`, from the real prompt builders rather than from a
list of constants — and compares it against the digest recorded beside the identity in
`reasoning/records.py`:

    uv run python scripts/judge_prompt_check.py --check

Offline, no provider, no key, nothing re-judged. The whole cost of a moved prompt is this
failing and one line being edited, which is why it belongs in `make check` and why the
alternative — making a content hash *be* the identity — was refused: that buys automatic
re-judgement, and re-judgement is the thing being paid for in model calls.

Without `--check` it prints what it computed, section by section:

    uv run python scripts/judge_prompt_check.py

That is the write half of the `--check`/write split, deliberately stopping at printing. It
does not edit `records.py`, because a command that makes this check green is a command that
gets run instead of read — and the point of the failure is that a person decides whether the
identity moves. There is nothing here a person cannot copy: one hex string, onto the line
above the one they were already editing.

The shape is `SQLiteDatabase._verify_unchanged`, which refuses to open a database whose
applied migration has been edited since. Neither replaces the key it guards with a hash;
both keep the hand-written key and raise when the checksum beside it stops being true.

Which judges it answers for is derived and not listed. `prompt_inventory.stamped_identities`
imports the package and reads `identity` off the classes, so a fourth judge fails this check
on the day it is written instead of being quietly left out of it — the inventory used to be
keyed by three identities written down here and nowhere tied to the classes carrying them,
which is the guarded bug rebuilt inside the guard.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from archcompass.analysis.analyzer import analysis_atlas
from archcompass.analysis.atlas import Atlas, AtlasQuery, AtlasQueryResult
from archcompass.analysis.investigation import AtlasInvestigator
from archcompass.domain import RepositoryAtlas, RepositoryRef
from archcompass.reasoning.adapters.prompt_inventory import (
    PromptSection,
    judge_prompt_sections,
    section_digest,
    stamped_identities,
)
from archcompass.reasoning.ports import ToolSpec
from archcompass.reasoning.records import JUDGE_PROMPT_DIGESTS

ROOT = Path(__file__).resolve().parents[1]

#: Where the recorded digests live, named for the failure message rather than read from.
RECORDED_IN = "src/archcompass/reasoning/records.py"

#: Where a judge's sections are assembled, for the same reason.
INVENTORY_IN = "src/archcompass/reasoning/adapters/prompt_inventory.py"


class _NoQueries:
    """A query service that is never asked anything.

    `AtlasInvestigator.tools` is a description of the five questions the atlas can answer,
    and answering none of them is not needed to read it. The alternative was building a real
    `DeterministicAtlasQueryService`, which needs a source reader and a freshness policy over
    a repository that does not exist here.
    """

    def execute(self, atlas: Atlas, query: AtlasQuery) -> AtlasQueryResult:
        del atlas, query
        raise AssertionError("the tool descriptions are read without any lookup being made")


def atlas_tool_specifications() -> Sequence[ToolSpec]:
    """The atlas tools as a judgement is offered them, from the class that defines them.

    This is the one place the concrete `AtlasInvestigator` is named, and it is deliberately
    here rather than in `prompt_inventory`. At run time nothing in `reasoning` names it
    either: `bootstrap` wires the `InvestigatorSource` and `ReviewToolbox` reaches it through
    the port. A build-time check is a composition root like any other, and this script is it.

    The atlas is empty of nodes and stamped with a parser configuration, because an atlas
    that does not say what built it is one this build refuses to read at all. The
    descriptions do not depend on what is in it.
    """

    repository = RepositoryRef("repository", ROOT, "branch", "content")
    stamped = RepositoryAtlas(
        "atlas_1",
        repository,
        parser_configuration=(("parser", "digest"), ("analysis", "digest")),
    )
    return AtlasInvestigator(_NoQueries(), analysis_atlas(stamped), repository).tools


def _computed() -> Mapping[str, tuple[PromptSection, ...]]:
    return judge_prompt_sections(atlas_tool_specifications())


def _report(identity: str, sections: Sequence[PromptSection]) -> str:
    """One judge's sections, named, so a reader knows what the digest above them covers.

    What this table does *not* do is say which section moved, and the docstring here used to
    claim it did. It cannot: no per-section digest is recorded anywhere, so there is nothing
    on disk for these lines to be diffed against. What a reader gets is the inventory — every
    stretch of text this judge sends, in the order it is hashed — and a stable digest per
    section, which they can compare against another revision by running the print mode twice
    with `git stash` in between. That is worth printing and it is not the same claim.

    Recording the per-section digests would make the comparison automatic and is still
    refused: it is one recording per section to keep true where a single fact is guarded, and
    that fact is the identity. `git diff` already names the section that moved, in the file
    the person just edited.
    """

    lines = [f"{identity}  {section_digest(sections)}"]
    lines.extend(
        f"    {section_digest((section,))[:12]}  {section.label}" for section in sections
    )
    if not sections:
        lines.append("    (nothing — this judge reaches no provider)")
    return "\n".join(lines)


def check() -> bool:
    """Whether every recorded digest still answers for the prompts beside it.

    Three refusals, and the third is about a judge that does not exist yet. A stale digest and
    a digest left behind by a renamed judge are both about the three judges already written
    down; a judge whose identity nothing digests is the case where writing them down was the
    mistake. It is derived rather than listed — see `prompt_inventory.stamped_identities` —
    because a fourth judge is exactly the thing a list gets forgotten for.
    """

    computed = _computed()
    recorded = JUDGE_PROMPT_DIGESTS
    stale = [
        identity
        for identity, sections in computed.items()
        if recorded.get(identity) != section_digest(sections)
    ]
    unknown = sorted(set(recorded) - set(computed))
    stamped = stamped_identities()
    undigested = sorted(
        (identity, where) for where, identity in stamped.items() if identity not in computed
    )
    if not stale and not unknown and not undigested:
        # The count of judges *found* rather than of entries digested, so the line reports
        # coverage and not only agreement. They are equal or this branch was not reached.
        print(
            f"{len(set(stamped.values()))} judge prompts match the digests"
            f" recorded in {RECORDED_IN}"
        )
        return True

    for identity in stale:
        sections = computed[identity]
        print(
            f"The prompt behind {identity} has changed, and {identity} has not.\n"
            f"\n{_report(identity, sections)}\n"
            f"\nRecorded: {recorded.get(identity) or '(nothing)'}\n"
            f"Computed: {section_digest(sections)}\n"
            "\nThe sections above are everything this judge sends a model. One of them moved,"
            "\nand a finding stored under the old prompt still claims it was judged by this"
            "\none — so the delta reads it as unmoved and the verdict never gets revisited."
            "\n"
            f"\nBump both, together, in {RECORDED_IN}: give the identity a new version and"
            "\nrecord the computed digest above against it. They are one line apart and they"
            "\nare one decision. If the edit genuinely does not change what the model is"
            "\nasked — a comment, a docstring nothing sends — record the new digest and leave"
            "\nthe identity where it is; that is a judgement to make on purpose rather than"
            "\nby forgetting, which is the whole reason this check exists."
            f"\n\nRun `uv run python {Path(__file__).relative_to(ROOT)}` to print every"
            "\njudge's sections without failing anything.",
            file=sys.stderr,
        )
    for identity in unknown:
        print(
            f"{RECORDED_IN} records a digest for {identity}, which no judge carries. A judge"
            "\nwas renamed or removed and its digest was left behind; delete the entry.",
            file=sys.stderr,
        )
    for identity, where in undigested:
        print(
            f"{where} stamps every finding it produces with {identity}, and nothing says what"
            f"\nthat identity was minted against. Until it does, a prompt behind {identity} can"
            "\nmove without anything noticing — which is the failure this check exists for,"
            "\narriving through the one door it did not watch."
            f"\n\nGive it an entry in `judge_prompt_sections` in {INVENTORY_IN}, assembled from"
            "\nthe real prompt builders rather than from copies of their text, and record its"
            f"\ndigest beside its identity in {RECORDED_IN}. A judge that reaches no provider"
            "\ngets an empty tuple and the digest of the empty string, which is a claim rather"
            "\nthan an omission — `judge:deterministic-v1` is the worked example."
            f"\n\nThis judge was found by importing it, not by reading the source for a"
            "\nparticular spelling, so there is no form of `identity` that gets past it.",
            file=sys.stderr,
        )
    return False


def main(argv: Sequence[str] | None = None) -> int:
    # `argv` is a parameter rather than read straight off `sys.argv`, so the test can drive
    # both modes of the real `main` instead of a reimplementation of it. Under pytest the
    # process arguments are pytest's own, and parsing those refused every invocation.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if a judge's prompts no longer match the digest recorded beside its identity",
    )
    arguments = parser.parse_args(argv)

    if arguments.check:
        return 0 if check() else 1

    for identity, sections in _computed().items():
        print(_report(identity, sections))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
