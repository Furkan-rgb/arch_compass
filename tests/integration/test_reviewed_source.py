"""Whatever the judge reads is the snapshot the candidate was detected in.

Two ways to be served and one rule between them. A recorded revision is immutable, so it is
answered from git and needs no check at all. A working tree is not, so every read of one
asks whether it is still what was analysed — immediately before touching disk, not once when
the source was opened, because the interval between those two moments is exactly when a
developer's tree changes under a running review.

The failure this prevents is silent. A judgement that read a newer tree against an older
atlas would be reasoning about line numbers that name different code, and nothing in the
record would say so.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from archcompass.analysis.adapters.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.analysis.atlas import Atlas
from archcompass.analysis.reviewed_source import AtlasReviewedSource
from archcompass.domain.errors import StaleAtlasError
from archcompass.reasoning.adapters.reviewed_backend import ReviewedRevisionBackend


def _git(root: Path, *arguments: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True
    )
    return done.stdout.decode().strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "app").mkdir(parents=True)
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "gateway.py").write_text(
        '"""The gateway."""\n\n\nclass Gateway:\n'
        "    def charge(self) -> str:\n"
        '        return "as it was reviewed"\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_gateway.py").write_text(
        "def test_charge() -> None:\n    assert True\n", encoding="utf-8"
    )
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "the reviewed revision")
    return root


class _Moved:
    """A freshness checker that says the tree is no longer what was analysed."""

    def __init__(self) -> None:
        self.asked = 0

    def ensure_fresh(self, atlas: Atlas) -> None:
        del atlas
        self.asked += 1
        raise StaleAtlasError("This repository has changed since the review ran.")


class _Unmoved:
    def __init__(self) -> None:
        self.asked = 0

    def ensure_fresh(self, atlas: Atlas) -> None:
        del atlas
        self.asked += 1


def _source(root: Path, *, revision: str | None, freshness: object = None):
    atlas = PythonAstRepositoryAnalyzer().analyze(root)
    return AtlasReviewedSource(
        root=root,
        revision=revision,
        atlas=atlas,
        freshness=freshness,  # type: ignore[arg-type]
    )


def test_source_comes_from_the_recorded_revision_and_not_from_the_tree(
    repository: Path,
) -> None:
    """The tree moves; every one of the four answers stays where the review was."""

    revision = _git(repository, "rev-parse", "HEAD")
    (repository / "app" / "gateway.py").write_text(
        '"""The gateway."""\n\n\nclass Gateway:\n'
        "    def settle(self) -> str:\n"
        '        return "changed since"\n',
        encoding="utf-8",
    )
    (repository / "app" / "invented.py").write_text("X = 1\n", encoding="utf-8")

    source = _source(repository, revision=revision, freshness=_Moved())

    assert "as it was reviewed" in source.read_file("app/gateway.py", offset=0, limit=50)
    assert "changed since" not in source.read_file("app/gateway.py", offset=0, limit=50)
    assert "app/invented.py" not in source.list_directory("app")
    assert "app/invented.py" not in source.find_paths("*.py", within="app", limit=50)
    assert [item.line for item in source.search_lines(
        "def charge", within=None, name_pattern="*.py", limit=5)] == [5]
    # And nothing asked about freshness, because nothing needed to: a commit cannot go stale.
    assert source._freshness.asked == 0  # type: ignore[union-attr]


def test_without_a_revision_a_moved_tree_is_refused_rather_than_read(
    repository: Path,
) -> None:
    """The other half. No commit to ask for, so the guard is all there is."""

    source = _source(repository, revision=None, freshness=_Moved())

    for read in (
        lambda: source.read_file("app/gateway.py", offset=0, limit=10),
        lambda: source.list_directory("app"),
        lambda: source.find_paths("*.py", within=None, limit=10),
        lambda: source.search_lines("charge", within=None, name_pattern=None, limit=10),
    ):
        with pytest.raises(StaleAtlasError):
            read()


def test_the_tree_is_asked_about_before_every_read_and_not_once(repository: Path) -> None:
    """A tree can move between the first read of a judgement and its fourth.

    Checking at construction would have been cheaper and would have covered exactly the
    interval in which nothing happens. 45 ms per check, measured, against a judgement that
    takes tens of seconds.
    """

    source = _source(repository, revision=None, freshness=_Unmoved())

    source.read_file("app/gateway.py", offset=0, limit=10)
    source.list_directory("app")
    source.find_paths("*.py", within=None, limit=10)
    source.search_lines("charge", within=None, name_pattern=None, limit=10)

    assert source._freshness.asked == 4  # type: ignore[union-attr]


def test_a_read_that_cannot_be_served_says_so_rather_than_answering_empty(
    repository: Path,
) -> None:
    """An empty answer would be weighed as evidence that the file holds nothing."""

    backend = ReviewedRevisionBackend(
        _source(repository, revision=_git(repository, "rev-parse", "HEAD"))
    )

    assert backend.read("app/absent.py").error
    assert backend.ls("app").entries
    assert backend.grep("charge", glob="*.py").matches


def test_a_stale_tree_reaches_the_model_as_a_sentence_rather_than_an_exception(
    repository: Path,
) -> None:
    """The model is told the source could not be read, and goes on to judge without it.

    Raising instead would lose the whole judgement over one lookup, and the same choice is
    already made for every atlas lookup in `AtlasInvestigator.call`.
    """

    backend = ReviewedRevisionBackend(
        _source(repository, revision=None, freshness=_Moved())
    )

    assert "changed since the review ran" in (backend.read("app/gateway.py").error or "")
    assert "changed since the review ran" in (backend.ls("app").error or "")
    assert "changed since the review ran" in (backend.glob("*.py").error or "")
    assert "changed since the review ran" in (backend.grep("charge").error or "")


def test_only_read_only_tools_are_offered_to_the_model(repository: Path) -> None:
    """Omitted from the toolset, not present and refused. There is nothing to deny."""

    from deepagents import FilesystemMiddleware

    middleware = FilesystemMiddleware(
        backend=ReviewedRevisionBackend(_source(repository, revision=None)),
        tools=["ls", "read_file", "glob", "grep"],
    )

    offered = {tool.name for tool in middleware.tools}
    assert offered == {"ls", "read_file", "glob", "grep"}
    assert not offered & {"write_file", "edit_file", "delete", "execute"}
