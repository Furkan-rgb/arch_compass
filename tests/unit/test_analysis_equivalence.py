"""The atlas is the same atlas, however the analyser is rearranged inside.

A golden comparison rather than a set of assertions about parts. The analyser is being
restructured for memory and speed — work whose whole promise is that it changes nothing
observable — and the only statement of that promise which cannot drift is the entire
serialised atlas, compared byte for byte against a copy taken before the change.

Held against the bundled examples, which are the repositories this project already ships
and already reviews, so a difference here is a difference somebody would have seen.

Regenerate deliberately, never reflexively: run with `ARCHCOMPASS_REWRITE_GOLDEN=1` only
when the output is *meant* to change — a new parser version, a new signal — and read the
diff before committing it. A golden file rewritten to make a test pass is a test deleted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from archcompass.adapters.analysis import PythonAstRepositoryAnalyzer
from archcompass.domain.base import canonical_json

GOLDEN = Path(__file__).parent / "golden"

#: The bundled examples, by the directory they live in. Small enough that the comparison is
#: fast, real enough that they exercise packages, protocols, tests and configuration.
EXAMPLES = ["boundary-review", "warehouse-sync", "speech-vendor"]


def _repository(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "eval" / "cases" / name / "repository"


def _analysed(root: Path) -> dict[str, object]:
    """One atlas, less the facts about this run rather than about the code.

    Four fields, and only four: `root_path` and `repository_identity` are where the checkout
    happens to sit, `created_at` is when it ran, and `version_id` is freshly minted every
    time. Everything else is derived from the source and is identical across runs — which is
    itself worth knowing, and is what the second test in this file pins.
    """

    atlas = PythonAstRepositoryAnalyzer().analyze(root)
    document = json.loads(canonical_json(atlas))
    version = document["version"]
    version.pop("root_path", None)
    version.pop("created_at", None)
    version.pop("repository_identity", None)
    version.pop("version_id", None)
    return document


@pytest.mark.parametrize("example", EXAMPLES)
def test_the_atlas_is_unchanged(example: str) -> None:
    root = _repository(example)
    if not root.is_dir():
        pytest.skip(f"{example} is not present in this checkout")

    produced = _analysed(root)
    golden = GOLDEN / f"{example}.json"

    if os.environ.get("ARCHCOMPASS_REWRITE_GOLDEN", "").strip() == "1":
        GOLDEN.mkdir(parents=True, exist_ok=True)
        golden.write_text(json.dumps(produced, indent=2, sort_keys=True) + "\n")
        pytest.skip(f"rewrote {golden.name} — read the diff before committing it")

    if not golden.is_file():
        pytest.fail(
            f"{golden} does not exist. Run with ARCHCOMPASS_REWRITE_GOLDEN=1 to record it."
        )

    expected = json.loads(golden.read_text())
    # Compared as whole documents. A first-difference message would name one node out of
    # thousands and say nothing about how many others moved with it.
    assert produced == expected


@pytest.mark.parametrize("example", EXAMPLES)
def test_analysing_twice_gives_the_same_atlas(example: str) -> None:
    """Determinism, which the golden files above quietly depend on."""

    root = _repository(example)
    if not root.is_dir():
        pytest.skip(f"{example} is not present in this checkout")

    assert _analysed(root) == _analysed(root)
