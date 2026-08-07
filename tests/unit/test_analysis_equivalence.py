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
#: fast, real enough that they exercise packages, protocols and tests.
EXAMPLES = ["boundary-review", "warehouse-sync", "speech-vendor"]

#: Everything the bundled examples happen not to contain. They are all pure Python, so a
#: change that only affected configuration files, unparseable source or a file that is not
#: UTF-8 passed the comparison untouched — which is exactly how a bug that zeroed the size
#: of every configuration node reached a review of this test's own safety argument.
#:
#: Kept here rather than added to `eval/cases`, because those are the repositories the
#: evaluation reasons about and a deliberately broken file would be a claim about them.
MIXED = "mixed"


def _repository(name: str) -> Path:
    if name == MIXED:
        return Path(__file__).parent / "fixtures" / MIXED
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


@pytest.mark.parametrize("example", [*EXAMPLES, MIXED])
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


@pytest.mark.parametrize("example", [*EXAMPLES, MIXED])
def test_analysing_twice_gives_the_same_atlas(example: str) -> None:
    """Determinism, which the golden files above quietly depend on."""

    root = _repository(example)
    if not root.is_dir():
        pytest.skip(f"{example} is not present in this checkout")

    assert _analysed(root) == _analysed(root)


def test_the_mixed_fixture_actually_contains_what_it_is_for() -> None:
    """The fixture is only a safety net while it still holds the things it was built for.

    Asserted rather than assumed: a fixture quietly reduced to plain Python would leave the
    comparison above passing and covering nothing, which is the failure it exists to prevent.
    """

    atlas = PythonAstRepositoryAnalyzer().analyze(_repository(MIXED))
    paths = {node.path for node in atlas.nodes}

    assert "pyproject.toml" in paths
    assert ".env" in paths
    assert any(signal.code == "parse-error" for signal in atlas.signals)
    assert "legacy.py" in paths
    # And the configuration node has a size, which is the specific thing that was lost.
    sized = {profile.node_id: profile.local.physical_lines for profile in atlas.metrics}
    configuration = next(node for node in atlas.nodes if node.path == "pyproject.toml")
    assert sized[configuration.atlas_id] > 0
