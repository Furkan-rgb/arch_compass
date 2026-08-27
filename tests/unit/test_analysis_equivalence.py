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

And the rewrite refuses to record a changed atlas under an unchanged `PARSER_VERSION`.
That constant is the product's only statement that a stored atlas was built by a parser that
no longer exists: `AtlasFreshnessService` compares it against the stamp on the atlas, and
where the two agree the atlas is served as current. Nothing forced it to move. Twice it did
not — `6d27325` gave every configuration and package node its real size and left the version
at v5, so a stored atlas went on reporting them as nothing; `9f2a461` restored every
`IMPLEMENTS` edge a failed type-checker sweep had silently dropped and left it at v6, which
on this repository is thirty-six candidates out of fifty-four. Both changed what the analyzer
produces from the same bytes, which is the whole of what the constant claims.

There was already a detector for exactly that — this file — and the developer's answer to it
was `ARCHCOMPASS_REWRITE_GOLDEN=1`, which asked nothing. So the refusal lives at the rewrite
rather than in a rule somebody has to remember, and it is the argument
`SQLiteDatabase._verify_unchanged` already makes about an applied migration: a golden is the
history of one parser version, rewriting it in place changes nothing and announces nothing,
and the only way past the refusal is to bump the constant and say why beside it. Hand-editing
a golden gets around it, exactly as hand-editing the migration row does; both are a person
deciding to, rather than a person forgetting to.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from archcompass.analysis.adapters import PythonAstRepositoryAnalyzer
from archcompass.records import canonical_json

GOLDEN = Path(__file__).parent / "golden"

#: The bundled examples, by the directory they live in. Small enough that the comparison is
#: fast, real enough that they exercise packages, protocols and tests.
EXAMPLES = ["boundary-review", "warehouse-sync", "speech-vendor"]

#: Everything the bundled examples happen not to contain. They are all pure Python, so a
#: change that only affected configuration files, unparseable source or a file that is not
#: UTF-8 passed the comparison untouched — which is exactly how a bug that zeroed the size
#: of every configuration node reached a review of this test's own safety argument.
#:
#: Kept here rather than added to `examples/cases`, because those are the repositories the
#: evaluation reasons about and a deliberately broken file would be a claim about them.
MIXED = "mixed"


def _repository(name: str) -> Path:
    if name == MIXED:
        return Path(__file__).parent / "fixtures" / MIXED
    return Path(__file__).resolve().parents[2] / "examples" / "cases" / name / "repository"


def _analysed(root: Path) -> dict[str, object]:
    """One atlas, less the facts about this run rather than about the code.

    Dropped: where the checkout sits (`root_path`, `repository_identity`), when it ran
    (`created_at`), the identifier minted for it (`version_id`), and what git says about it
    (`git_commit_sha`, `root_commit_sha`, `branch_name`).

    The git facts matter for a reason worth writing down: these fixtures live inside this
    repository, so git answers about *this* repository's history, and the answer changes
    every time a commit touches the fixture's path. A golden that recorded it would fail on
    the commit that introduced it and pass afterwards, which is a test measuring the
    repository rather than the analyser. Everything left is derived from the source alone.
    """

    atlas = PythonAstRepositoryAnalyzer().analyze(root)
    document = json.loads(canonical_json(atlas))
    version = document["version"]
    version.pop("root_path", None)
    version.pop("created_at", None)
    version.pop("repository_identity", None)
    version.pop("version_id", None)
    for git_fact in ("git_commit_sha", "root_commit_sha", "branch_name"):
        version.pop(git_fact, None)
    return document


def _unbumped(
    recorded: dict[str, object] | None, produced: dict[str, object]
) -> str | None:
    """Why this atlas may not be recorded, or `None` because it may.

    The one condition: the atlas moved and the parser version did not. A first recording has
    nothing to disagree with, and an atlas that did not move is the golden it is replacing.

    Separated from the rewrite so it can be given the two documents directly and asserted on,
    because the rewrite itself only runs under an environment variable nobody sets in CI — a
    refusal that is never exercised is a refusal nobody can trust.
    """

    if recorded is None or recorded == produced:
        return None
    was = recorded.get("version", {})
    now = produced.get("version", {})
    if not isinstance(was, dict) or not isinstance(now, dict):  # pragma: no cover
        return None
    if was.get("parser_version") != now.get("parser_version"):
        return None
    return (
        f"This atlas differs from the one recorded under parser version "
        f"{was.get('parser_version')!r}, and that version has not moved. Every stored atlas "
        "carrying that stamp is now an atlas this analyzer would not produce, and "
        "`AtlasFreshnessService` will go on serving all of them as current, because the only "
        "thing it compares is the stamp. Bump `PARSER_VERSION` in "
        "`analysis/adapters/ast_analyzer.py`, and add the paragraph above it saying what the "
        "new version emits that the old one cannot — then run this again."
    )


@pytest.mark.parametrize("example", [*EXAMPLES, MIXED])
def test_the_atlas_is_unchanged(example: str) -> None:
    root = _repository(example)
    if not root.is_dir():
        pytest.skip(f"{example} is not present in this checkout")

    produced = _analysed(root)
    golden = GOLDEN / f"{example}.json"

    if os.environ.get("ARCHCOMPASS_REWRITE_GOLDEN", "").strip() == "1":
        recorded = json.loads(golden.read_text()) if golden.is_file() else None
        refusal = _unbumped(recorded, produced)
        if refusal is not None:
            pytest.fail(f"Refusing to rewrite {golden.name}. {refusal}")
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


def _atlas(parser_version: str, node_count: int) -> dict[str, object]:
    """The two things the refusal reads, and nothing else it does not."""

    return {
        "version": {"parser_version": parser_version, "analysis_config_hash": "hash"},
        "nodes": [{"atlas_id": f"node_{index}"} for index in range(node_count)],
    }


def test_a_changed_atlas_may_not_be_recorded_under_an_unchanged_parser_version() -> None:
    """The refusal the rewrite is built on, exercised where the rewrite cannot be.

    This is the check that would have stopped both of the misses named at the top of this
    file. Asserted on the sentence as well as on the fact, because a refusal that does not
    say which constant to move is a refusal somebody works around.
    """

    refusal = _unbumped(_atlas("python-ast-3.12-v8", 3), _atlas("python-ast-3.12-v8", 4))

    assert refusal is not None
    assert "PARSER_VERSION" in refusal
    assert "python-ast-3.12-v8" in refusal


def test_a_changed_atlas_under_a_new_parser_version_is_exactly_what_a_rewrite_is_for() -> None:
    assert _unbumped(_atlas("python-ast-3.12-v8", 3), _atlas("python-ast-3.12-v9", 4)) is None


def test_an_unchanged_atlas_and_a_first_recording_are_both_allowed() -> None:
    """Neither is a claim about a parser version that stored atlases still carry.

    An atlas that did not move is the golden it would overwrite. A golden that does not exist
    yet has no history to contradict — which is how `mixed.json` came to be recorded at all.
    """

    same = _atlas("python-ast-3.12-v8", 3)

    assert _unbumped(same, _atlas("python-ast-3.12-v8", 3)) is None
    assert _unbumped(None, same) is None
