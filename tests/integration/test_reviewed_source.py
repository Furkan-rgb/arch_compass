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
from typing import Any, cast

import pytest
from deepagents import FilesystemMiddleware
from langchain.agents.middleware.types import ModelRequest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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

    middleware = FilesystemMiddleware(
        backend=ReviewedRevisionBackend(_source(repository, revision=None)),
        tools=["ls", "read_file", "glob", "grep"],
    )

    offered = {tool.name for tool in middleware.tools}
    assert offered == {"ls", "read_file", "glob", "grep"}
    assert not offered & {"write_file", "edit_file", "delete", "execute"}


def test_a_path_the_model_was_handed_reads_back_without_it_guessing(
    repository: Path,
) -> None:
    """The round trip, which is what was actually broken.

    The vendor's own tool descriptions tell the model that glob "returns absolute paths".
    Handing back a bare `app/gateway.py` left it to construct what it had been told it
    already had, and it constructed a root nobody gave it: measured against an eight-boundary
    repository, 31 of 88 lookups were spent being told `/workspace/narration/planning.py` is
    not in the revision.

    So every path out is rooted, and a path in is read whichever way it arrives — a stored
    review from before this still renders, and a model that pastes back what it was given
    reads the file.
    """

    revision = _git(repository, "rev-parse", "HEAD")
    backend = ReviewedRevisionBackend(_source(repository, revision=revision))

    found = [item["path"] for item in backend.glob("*.py").matches or []]
    assert found, "the fixture repository has Python files in it"
    assert all(path.startswith("/") for path in found)

    # Every one of them opens, using nothing but the string it was handed.
    for path in found:
        assert backend.read(path).error is None, path
    # And the form the product used to hand out still works, because a path is a path.
    assert backend.read("app/gateway.py").error is None

    listed = [item["path"] for item in backend.ls("/app").entries or []]
    assert listed and all(path.startswith("/") for path in listed)
    assert all(backend.read(path).error is None for path in listed)

    assert all(m["path"].startswith("/") for m in backend.grep("charge").matches or [])


def test_a_path_that_is_not_there_says_which_form_is(repository: Path) -> None:
    """The error is the only thing that can teach the convention, so it names it.

    It used to say only that the path was wrong, and the model answered by making the same
    wrong path again — six times on one repository and thirty-one on another. An empty
    listing was worse than useless: a revision cannot hold an empty directory, so "no files
    found" at a named path invited the reader to conclude the directory was bare.
    """

    backend = ReviewedRevisionBackend(
        _source(repository, revision=_git(repository, "rev-parse", "HEAD"))
    )

    missing = backend.read("/workspace/app/gateway.py").error or ""
    assert "not in the revision" in missing
    assert "/adapters.py" in missing

    listed = backend.ls("/workspace")
    assert not listed.entries
    assert "/adapters.py" in (listed.error or "")

    # The root still lists, and is never reported as a directory that is not there.
    assert backend.ls("/").entries
    assert backend.ls("/").error is None


def test_an_empty_file_is_empty_rather_than_absent(repository: Path) -> None:
    """Two different facts arrive as the same empty string, and only one is an absence.

    `app/__init__.py` has nothing in it, which is what an `__init__.py` usually has — and it
    is the file a judgement opens to find out whether a directory is a package. Reported as
    "not in the revision under review", it told the model the package was not there.
    """

    backend = ReviewedRevisionBackend(
        _source(repository, revision=_git(repository, "rev-parse", "HEAD"))
    )

    empty = backend.read("/app/__init__.py")

    assert empty.error is None
    assert (empty.file_data or {}).get("content") == ""
    # And a path that genuinely is not there is still an absence.
    assert backend.read("/app/never_written.py").error


def test_the_model_is_told_where_the_filesystem_is_rooted(repository: Path) -> None:
    """The one thing a rooted answer cannot fix: the guess made before the first answer.

    Rooting what the tools hand back cured the repeats — a path the model was given reads
    back — but the opening read comes before it has been given anything, and the vendor's
    tool descriptions promise "absolute paths" without saying absolute to what. Measured
    after rooting: 5 of 37 lookups on `speech-vendor` were still a first read into
    `/workspace/`, a directory nobody had mentioned.

    Asserted through the middleware rather than on the constant, because the constant being
    right is worth nothing if it is not passed — and it reaches the model through the
    vendor's own slot for tool prose, which is not the judgement contract and says nothing
    about what to decide.
    """

    from archcompass.reasoning.adapters.judge_tools import FILESYSTEM_ROOT_NOTE

    middleware = FilesystemMiddleware(
        backend=ReviewedRevisionBackend(_source(repository, revision=None)),
        tools=["ls", "read_file", "glob", "grep"],
        system_prompt=FILESYSTEM_ROOT_NOTE,
    )
    request = ModelRequest(
        model=GenericFakeChatModel(messages=iter([AIMessage("")])),
        messages=[HumanMessage("Judge this candidate.")],
        system_message=SystemMessage("Judge this candidate."),
        tool_choice=None,
        tools=list(middleware.tools),
        response_format=None,
        state={},
        runtime=cast("Any", None),
    )
    prepared = middleware._filter_unsupported_tools_and_apply_prompt(request)

    said = str(prepared.system_message.content)
    assert "root is `/`" in said
    assert "no checkout path in front of it" in said
    # Appended, not substituted: the judgement's own instruction still opens the system
    # message and is still the whole of what the model is asked to decide.
    assert said.index("Judge this candidate.") < said.index("root is `/`")


def test_a_glob_matches_zero_directories_as_well_as_many(repository: Path) -> None:
    """`**/` is documented as "any directories", and `fnmatch` cannot match none of them.

    So `tests/**/*.py` found `tests/unit/test_gateway.py` and missed `tests/test_gateway.py`
    — and a repository whose tests all sit directly in `tests/` answered a perfectly valid
    pattern with nothing at all. Measured on a real repository: four of fifty-six lookups
    spent on a pattern the model was right to write.

    The glob description the model is handed is the vendor's, so the pattern is not ours to
    narrow. This is the same defect as promising absolute paths and returning relative ones,
    one tool along.
    """

    backend = ReviewedRevisionBackend(
        _source(repository, revision=_git(repository, "rev-parse", "HEAD"))
    )

    found = [item["path"] for item in backend.glob("tests/**/*.py").matches or []]

    # The fixture keeps its test directly in `tests/`, which is where most repositories
    # keep them and the case that used to return nothing.
    assert "/tests/test_gateway.py" in found
    # And the many-directories reading still works, on the same pattern.
    nested = [item["path"] for item in backend.glob("app/**/*.py").matches or []]
    assert "/app/gateway.py" in nested
    # A bare name is still read as "anywhere", which is what somebody typing it means.
    assert "/app/gateway.py" in [
        item["path"] for item in backend.glob("*.py").matches or []
    ]
