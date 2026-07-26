"""Run the advisory path against the bundled examples and score what has answers.

The `boundary-review` fixture exists so there is always something to try the tool against
with a known right answer. Six boundaries, all identical to the detector; the case makes
three of them justified and three not. A run that clears all six is an abstraction
generator, a run that condemns all six is an abstraction destroyer, and the score separates
those from an advisor.

`--all` adds `speech-vendor`, which is the same shape asking a harder question. There
every boundary stands in front of a change the case says is coming, so clearing all six is
the plausible mistake rather than the lazy one; what separates them is whether each seam is
at the edge the change arrives at. Read the two scores separately — a total across both
hides which failure mode is live.

Running both is the closest thing to a regression suite for judgement quality. It stays a
script rather than a workspace button: it is tens of model calls, and the browser
deliberately has no queue for work that long (master plan §18). Run it against the local
model — a metered free tier cannot serve it.

Needs a live model. Builds a throwaway workspace so nothing is left behind, and prints one
line per boundary as each verdict lands rather than after all of them.
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

import yaml

from archcompass.application.reviews import JudgedCandidate
from archcompass.bootstrap import Runtime, build_runtime
from archcompass.domain.case import ArchitectureCase

CASES = Path(__file__).resolve().parent.parent / "eval" / "cases"
DEFAULT_EXAMPLE = "boundary-review"


@dataclass(frozen=True)
class Example:
    """One bundled case with a repository to run it against."""

    name: str
    case: Path
    repository: Path
    #: Present only where the example ships an answer key. Without one a run can be read
    #: but not graded, which is reported as unscored rather than counted as a pass.
    expected: Path | None

    @property
    def answers(self) -> dict[str, dict[str, str | bool]]:
        if self.expected is None:
            return {}
        document = yaml.safe_load(self.expected.read_text(encoding="utf-8"))
        return {item["abstraction"]: item for item in document["boundaries"]}


@dataclass
class Outcome:
    """What one example produced, and how much of it could be graded."""

    example: str
    boundaries: int
    material: int
    scored: int
    correct: int
    unknown: list[str]
    seconds: float
    review_id: str

    @property
    def graded(self) -> bool:
        return self.scored > 0

    @property
    def passed(self) -> bool:
        return not self.unknown and (not self.graded or self.correct == self.scored)


def brownfield_examples() -> list[Example]:
    """Every example the review path can run: a case with a repository beside it.

    A case without a repository is skipped rather than failed. Candidates stated in a case
    instead of parsed from code are master plan §4.1, and until that exists there is nothing
    there for the detector to sweep.
    """

    found: list[Example] = []
    for directory in sorted(CASES.iterdir()):
        case = directory / "case.yaml"
        repository = directory / "repository"
        if not case.is_file() or not repository.is_dir():
            continue
        expected = directory / "expected.yaml"
        found.append(
            Example(
                name=directory.name,
                case=case,
                repository=repository.resolve(),
                expected=expected if expected.is_file() else None,
            )
        )
    return found


def run_example(runtime: Runtime, example: Example, sink: TextIO | None) -> Outcome:
    answers = example.answers
    runtime.repository_service.index(example.repository)
    case = ArchitectureCase.model_validate(
        yaml.safe_load(example.case.read_text(encoding="utf-8"))
    )
    revision = runtime.case_repository.create(case, actor="evaluation")

    correct = 0
    unknown: list[str] = []
    started = time.monotonic()
    total_started = started

    def report(item: JudgedCandidate, position: int, total: int) -> None:
        nonlocal correct, started
        name = item.candidate.participants[0].qualified_name
        key = answers.get(name)
        if not answers:
            mark = "·"
        elif key is None:
            unknown.append(name)
            mark = "?"
        elif key["material"] == item.verdict.material:
            correct += 1
            mark = "✓"
        else:
            mark = "✗"
        said = "material" if item.verdict.material else "not material"
        want = "—" if key is None else ("material" if key["material"] else "not material")
        elapsed = time.monotonic() - started
        started = time.monotonic()
        print(
            f"  {mark} [{position}/{total}] {name:<32} "
            f"said {said:<13} expected {want:<13} {elapsed:.0f}s",
            flush=True,
        )
        if sink is not None:
            sink.write(
                json.dumps(
                    {
                        "example": example.name,
                        "abstraction": name,
                        "correct": mark == "✓",
                        "expected": None if key is None else key["material"],
                        "expected_because": None if key is None else key["because"],
                        "verdict": item.verdict.model_dump(mode="json"),
                    }
                )
                + "\n"
            )
            sink.flush()

    review = runtime.review_service.review(
        revision.case_id,
        repository_root=example.repository,
        on_verdict=report,
        on_summarising=lambda: print("  … reading the verdicts as a set", flush=True),
    )
    report_body = review.report
    assert report_body is not None

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

    return Outcome(
        example=example.name,
        boundaries=len(report_body.reviewed),
        material=len(report_body.material),
        scored=0 if not answers else len(report_body.reviewed) - len(unknown),
        correct=correct,
        unknown=unknown,
        seconds=time.monotonic() - total_started,
        review_id=review.review_id,
    )


def print_table(outcomes: list[Outcome]) -> None:
    print(f"\n{'example':<28} {'boundaries':>10} {'material':>9} {'score':>9}  time")
    for outcome in outcomes:
        score = f"{outcome.correct}/{outcome.scored}" if outcome.graded else "unscored"
        print(
            f"{outcome.example:<28} {outcome.boundaries:>10} {outcome.material:>9} "
            f"{score:>9}  {outcome.seconds:.0f}s"
        )
    graded = [outcome for outcome in outcomes if outcome.graded]
    if graded:
        correct = sum(outcome.correct for outcome in graded)
        scored = sum(outcome.scored for outcome in graded)
        print(f"\n{correct}/{scored} correct across {len(graded)} scored example(s)")
    for outcome in outcomes:
        if outcome.unknown:
            # Never silently exclude: an abstraction the key does not cover is a fixture
            # that drifted from its own scoring, and a score over the remainder would look
            # like a result while measuring less than it claims.
            print(
                f"NOT SCORED in {outcome.example} (absent from expected.yaml): "
                f"{', '.join(sorted(outcome.unknown))}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models-config",
        type=Path,
        default=Path("config/models.ollama.yaml"),
        help="Reasoning provider configuration to run against.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run every brownfield example rather than only the scored fixture.",
    )
    parser.add_argument(
        "--case",
        default=DEFAULT_EXAMPLE,
        help=(
            "Which example to run. Working on one example's wording means running it and "
            "reading it repeatedly, and the other one has nothing to say about that edit."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Write every verdict as JSON lines. A score says how often the advisor was "
            "right; only the reasoning says why it was wrong."
        ),
    )
    arguments = parser.parse_args()

    examples = brownfield_examples()
    if not arguments.all:
        examples = [item for item in examples if item.name == arguments.case]
    if not examples:
        known = ", ".join(item.name for item in brownfield_examples()) or "none"
        print(f"No example named {arguments.case!r} under {CASES}. Found: {known}")
        return 1

    sink = arguments.out.open("w", encoding="utf-8") if arguments.out else None
    outcomes: list[Outcome] = []
    try:
        with tempfile.TemporaryDirectory(prefix="archcompass-evaluation-") as directory:
            runtime = build_runtime(Path(directory), models_config=arguments.models_config)
            for example in examples:
                marker = "" if example.expected else "  (no answer key)"
                print(f"\n{example.name}{marker}", flush=True)
                outcomes.append(run_example(runtime, example, sink))
    finally:
        if sink is not None:
            sink.close()

    print_table(outcomes)
    return 0 if all(outcome.passed for outcome in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
