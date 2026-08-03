"""Run the advisory path against the example repositories, against a live model.

Each example is a repository and nothing else: no case is written before the run, which is
what a first-time user has (master plan §6C.1). The run judges every boundary from the code
alone and comes back with the questions that would settle them, and this script prints both
as they land. Nothing is scored — the examples ship no answer key, because the behaviour
worth watching is what a run asks, and there is no key for that which does not first settle
the question the example is built to leave open.

Two failures pull opposite ways and are the reason to read the output rather than a number:
condemning every boundary because an unwritten case justified none of them, and clearing
every boundary while flagging nothing, which reads as approval nobody earned.

`--all` runs every example. It stays a script rather than a workspace button: it is tens of
model calls, and the browser deliberately has no queue for work that long (master plan §18).
Run it against the local model — a metered free tier cannot serve it.

Builds a throwaway workspace so nothing is left behind, and prints one line per boundary as
each verdict lands rather than after all of them.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from archcompass.application.reviews import JudgedCandidate
from archcompass.bootstrap import Runtime, build_runtime, pinned_model

EXAMPLES = Path(__file__).resolve().parent.parent / "eval" / "cases"
DEFAULT_EXAMPLE = "boundary-review"


@dataclass(frozen=True)
class Example:
    """One example repository, as this script needs it."""

    name: str
    repository: Path


@dataclass
class Outcome:
    """What one example produced."""

    example: str
    boundaries: int
    material: int
    seconds: float
    review_id: str
    #: How many verdicts said they rest on something the case does not settle, and how many
    #: questions those merged into. The pair is the measurement: hinges with no question is
    #: a consolidation failure, and a question per hinge is noise.
    hinged: int
    questions: int


def example_repositories() -> list[Example]:
    """Every example the review path can run: a manifest with a repository beside it."""

    return [
        Example(name=directory.name, repository=(directory / "repository").resolve())
        for directory in sorted(EXAMPLES.iterdir())
        if (directory / "example.yaml").is_file() and (directory / "repository").is_dir()
    ]


def run_example(runtime: Runtime, example: Example, sink: TextIO | None) -> Outcome:
    runtime.repository_service.index(example.repository)
    revision = runtime.case_service.start_from_repository(example.repository)

    started = time.monotonic()
    total_started = started

    def report(item: JudgedCandidate, position: int, total: int) -> None:
        nonlocal started
        name = item.candidate.participants[0].qualified_name
        said = "material" if item.verdict.material else "not material"
        elapsed = time.monotonic() - started
        started = time.monotonic()
        hinge = item.verdict.hinge
        print(
            f"  [{position}/{total}] {name:<32} said {said:<13} {elapsed:.0f}s  "
            f"hinge {'yes' if hinge else '—'}",
            flush=True,
        )
        if hinge is not None:
            print(f"        turns on: {hinge.unknown}", flush=True)
        if sink is not None:
            sink.write(
                json.dumps(
                    {
                        "example": example.name,
                        "abstraction": name,
                        "verdict": item.verdict.model_dump(mode="json"),
                    }
                )
                + "\n"
            )
            sink.flush()

    # A first pass, deliberately. This harness measures what one pass reaches from a case
    # nobody has written — a run that stops to ask is the outcome under measurement, not a
    # failure to complete.
    review = runtime.review_service.review(
        revision.case_id,
        repository_root=example.repository,
        on_verdict=report,
        on_eliciting=lambda: print("  … composing what it needs to know", flush=True),
        on_summarising=lambda: print("  … reading the verdicts as a set", flush=True),
    )
    report_body = review.report
    assert report_body is not None
    if review.awaiting_answers:
        print("\n  This pass is waiting on answers; its verdicts are provisional.")

    overview = report_body.overview
    print(f"\n  {overview.situation}")
    for statement in overview.themes:
        print(f"    · {statement.text}  [{', '.join(statement.supporting_references)}]")
    for position, statement in enumerate(overview.recommended_sequence, start=1):
        print(
            f"    {position}. {statement.text}  "
            f"[{', '.join(statement.supporting_references)}]"
        )
    print(f"  {overview.limits}")

    hinged = [item for item in report_body.reviewed if item.hinge]
    if overview.open_questions:
        print(f"\n  What the case does not say ({len(hinged)} verdicts rest on something):")
        for question in overview.open_questions:
            print(f"    {question.reference}. {question.question}")
            print(
                f"        settles {', '.join(question.supporting_references)} "
                f"· an answer belongs in {question.answer_belongs_in.value}"
            )
    elif hinged:
        # Worth saying out loud: hinges were recorded and none became a question, which is
        # a consolidation failure rather than a quiet success.
        print(f"\n  {len(hinged)} verdicts rest on something, and nothing was asked.")

    return Outcome(
        example=example.name,
        boundaries=len(report_body.reviewed),
        material=len(report_body.material),
        seconds=time.monotonic() - total_started,
        review_id=review.review_id,
        hinged=len(hinged),
        questions=len(overview.open_questions),
    )


def print_table(outcomes: list[Outcome]) -> None:
    print(
        f"\n{'example':<28} {'boundaries':>10} {'material':>9} {'hinged':>7} "
        f"{'asked':>6}  time"
    )
    for outcome in outcomes:
        print(
            f"{outcome.example:<28} {outcome.boundaries:>10} {outcome.material:>9} "
            f"{outcome.hinged:>7} {outcome.questions:>6}  {outcome.seconds:.0f}s"
        )
    for outcome in outcomes:
        if outcome.boundaries and outcome.material == outcome.boundaries:
            print(f"CONDEMNED EVERYTHING in {outcome.example}")
        if outcome.hinged and not outcome.questions:
            print(f"HINGED WITHOUT ASKING in {outcome.example}")
        if not outcome.hinged:
            # An unwritten case cannot settle everything, so nothing hinging means the run
            # spent the silence without noticing it.
            print(f"NOTHING RESTED ON ANYTHING in {outcome.example}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # Pinned rather than left to whatever the workspace last chose: what this prints is only
    # readable alongside which model produced it. The workspace here is a temporary
    # directory anyway, so there is nothing to choose.
    parser.add_argument(
        "--provider",
        default="ollama",
        help="Which provider to reason with.",
    )
    parser.add_argument(
        "--model",
        default="gemma4:26b",
        help="Which model to reason with.",
    )
    parser.add_argument(
        "--thinking",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Require or forbid reasoning before answering. Omitted leaves it to the model, "
            "which is a third behaviour rather than the absence of the other two."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run every example rather than only the standing one.",
    )
    parser.add_argument(
        "--example",
        default=DEFAULT_EXAMPLE,
        help=(
            "Which example to run. Working on one example means running it and reading it "
            "repeatedly, and the others have nothing to say about that edit."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Write every verdict as JSON lines. The table says what a run did; only the "
            "reasoning says why."
        ),
    )
    arguments = parser.parse_args()

    examples = example_repositories()
    if not arguments.all:
        examples = [item for item in examples if item.name == arguments.example]
    if not examples:
        known = ", ".join(item.name for item in example_repositories()) or "none"
        print(f"No example named {arguments.example!r} under {EXAMPLES}. Found: {known}")
        return 1

    sink = arguments.out.open("w", encoding="utf-8") if arguments.out else None
    outcomes: list[Outcome] = []
    try:
        with tempfile.TemporaryDirectory(prefix="archcompass-example-") as directory:
            runtime = build_runtime(
                Path(directory),
                pin=pinned_model(arguments.provider, arguments.model, arguments.thinking),
            )
            for example in examples:
                print(f"\n{example.name}", flush=True)
                outcomes.append(run_example(runtime, example, sink))
    finally:
        if sink is not None:
            sink.close()

    print_table(outcomes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
