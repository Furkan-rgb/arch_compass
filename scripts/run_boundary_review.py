"""Run the advisory path against the boundary-review fixture and score it.

The fixture exists so there is always something to try the tool against, with a known
right answer. Six boundaries, all identical to the detector; the case makes three of them
justified and three not. A run that clears all six is an abstraction generator, a run that
condemns all six is an abstraction destroyer, and the score separates those from an
advisor.

Needs a live model. Builds a throwaway workspace so nothing is left behind, and prints one
line per boundary as each verdict lands rather than after all six.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import yaml

from archcompass.application.reviews import JudgedCandidate
from archcompass.bootstrap import build_runtime
from archcompass.domain.case import ArchitectureCase

FIXTURE = Path(__file__).resolve().parent.parent / "eval" / "cases" / "boundary-review"


def _expected() -> dict[str, dict[str, str | bool]]:
    document = yaml.safe_load((FIXTURE / "expected.yaml").read_text(encoding="utf-8"))
    return {item["abstraction"]: item for item in document["boundaries"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models-config",
        type=Path,
        default=Path("config/models.yaml"),
        help="Reasoning provider configuration to run against.",
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
    sink = arguments.out.open("w", encoding="utf-8") if arguments.out else None

    expected = _expected()
    repository = (FIXTURE / "repository").resolve()

    with tempfile.TemporaryDirectory(prefix="archcompass-boundary-") as directory:
        workspace = Path(directory)
        runtime = build_runtime(workspace, models_config=arguments.models_config)
        runtime.repository_service.index(repository)
        case = ArchitectureCase.model_validate(
            yaml.safe_load((FIXTURE / "case.yaml").read_text(encoding="utf-8"))
        )
        revision = runtime.case_repository.create(case, actor="boundary-review")

        correct = 0
        unknown: list[str] = []
        started = time.monotonic()

        def report(item: JudgedCandidate, position: int, total: int) -> None:
            nonlocal correct, started
            name = item.candidate.participants[0].qualified_name
            key = expected.get(name)
            if key is None:
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
                f"  {mark} [{position}/{total}] {name:<26} "
                f"said {said:<13} expected {want:<13} {elapsed:.0f}s",
                flush=True,
            )
            if sink is not None:
                sink.write(
                    json.dumps(
                        {
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
            repository_root=repository,
            on_verdict=report,
        )

        report = review.report
        assert report is not None
        scored = len(report.reviewed) - len(unknown)
        print(
            f"\n{correct}/{scored} correct  "
            f"({len(report.policies_presented)} policies presented)  "
            f"stored as {review.review_id}"
        )
        if unknown:
            # Never silently exclude: an abstraction the key does not cover is a fixture
            # that drifted from its own scoring, and a score computed over the remainder
            # would look like a result.
            print(f"NOT SCORED (absent from expected.yaml): {', '.join(sorted(unknown))}")
        if sink is not None:
            sink.close()
        return 0 if correct == scored and not unknown else 1


if __name__ == "__main__":
    sys.exit(main())
