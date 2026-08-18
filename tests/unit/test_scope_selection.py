"""Choosing what a review is not about: the validation, the analysis, and the remembering.

Three things have to agree for a scoped review to work at all. The list has to mean one thing
however it was typed, the analysis has to leave out what it was told to and nothing else, and
the choice has to still be there when something later asks the repository whether the stored
atlas is still true. Each of those is a way this can be quietly wrong rather than broken.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.adapters.analysis.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.adapters.persistence import (
    SQLiteDatabase,
    SQLiteScopeSelectionRepository,
)
from archcompass.boundary.atlas import Atlas
from archcompass.boundary.scope import validate_excluded_paths
from archcompass.domain.errors import ScopeValidationError

_REPOSITORY = {
    "src/service.py": "def serve():\n    return 1\n",
    "src/__init__.py": "",
    "tests/test_service.py": "def test_serve():\n    assert True\n",
    "tests/__init__.py": "",
}


def _repository(root: Path) -> Path:
    for name, content in _REPOSITORY.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _paths(atlas: Atlas) -> set[str]:
    return {node.path for node in atlas.nodes}


@pytest.mark.parametrize(
    "excluded",
    [
        "../elsewhere",
        "src/../../elsewhere",
        "/etc",
        "C:\\Windows",
        "src\\vendor",
        "",
        "   ",
        "src//vendor",
        ".",
        "/",
    ],
)
def test_a_folder_that_could_name_somewhere_else_is_refused(excluded: str) -> None:
    """Every one of these would silently exclude nothing, which is the dangerous failure.

    Exclusions are applied by comparing path parts, so a value naming somewhere outside the
    repository never matches anything: the caller who asked for a smaller review would get
    the whole repository analysed and no indication that their choice was ignored.
    """

    with pytest.raises(ScopeValidationError):
        validate_excluded_paths([excluded])


def test_a_folder_already_inside_an_excluded_one_is_dropped() -> None:
    """Excluding `src` already excludes `src/vendor`, so keeping both is two spellings."""

    assert validate_excluded_paths(["src", "src/vendor", "src/vendor/deep"]) == ("src",)
    # A sibling with a shared name prefix is not nested: `src/apps` is not inside `src/app`.
    assert validate_excluded_paths(["src/app", "src/apps"]) == ("src/app", "src/apps")


def test_the_same_choice_typed_two_ways_is_the_same_choice() -> None:
    """Order, duplication and a trailing slash cannot be allowed to move the fingerprint.

    They would, if they survived: the analysis reads a different list, and the caller who
    re-indexed with their folders typed in a different order would be told the code changed.
    """

    assert validate_excluded_paths(["tests/", "docs", "tests"]) == ("docs", "tests")
    assert validate_excluded_paths(["docs", "tests"]) == validate_excluded_paths(
        ["tests", "docs/"]
    )


def test_an_excluded_folder_is_absent_from_the_atlas_it_produces(tmp_path: Path) -> None:
    root = _repository(tmp_path)

    scoped = PythonAstRepositoryAnalyzer().analyze(root, excluded_paths=("tests",))

    assert "src/service.py" in _paths(scoped)
    assert not any(path.startswith("tests") for path in _paths(scoped))


def test_a_scoped_analysis_fingerprints_differently_and_configures_identically(
    tmp_path: Path,
) -> None:
    """The scope belongs in the fingerprint and nowhere near the configuration hash.

    The fingerprint is a digest of the files that were read, so leaving a folder out moves it
    by itself — nothing has to be told to say so. The configuration hash says what kind of
    analysis this was, and a scoped one is the same kind: hashing the scope into it would
    make an unscoped analysis hash differently than it always has, marking every stored atlas
    in every workspace stale to record something the fingerprint already said.
    """

    root = _repository(tmp_path)
    analyzer = PythonAstRepositoryAnalyzer()

    whole = analyzer.analyze(root)
    scoped = analyzer.analyze(root, excluded_paths=("tests",))

    assert scoped.version.content_fingerprint != whole.version.content_fingerprint
    assert scoped.version.analysis_config_hash == whole.version.analysis_config_hash


def test_the_identity_read_under_the_same_scope_matches_the_atlas(tmp_path: Path) -> None:
    """What freshness rests on: the recomputation has to agree with the analysis.

    Asked without the exclusions, it reads the folders the analysis skipped and produces a
    different digest — which would report a scoped atlas stale from the moment it was
    written, with re-indexing landing in the same place.
    """

    root = _repository(tmp_path)
    analyzer = PythonAstRepositoryAnalyzer()
    scoped = analyzer.analyze(root, excluded_paths=("tests",))

    matching = analyzer.current_identity(root, excluded_paths=("tests",))
    unscoped = analyzer.current_identity(root)

    assert matching.content_fingerprint == scoped.version.content_fingerprint
    assert unscoped.content_fingerprint != scoped.version.content_fingerprint


def _database(root: Path) -> SQLiteDatabase:
    database = SQLiteDatabase(root / "archcompass.db", workspace=root)
    database.initialize()
    return database


def test_a_recorded_scope_is_read_back_and_replaced_rather_than_added_to(
    tmp_path: Path,
) -> None:
    selections = SQLiteScopeSelectionRepository(_database(tmp_path))

    assert selections.get("/repositories/one") is None

    selections.record("/repositories/one", ("docs", "tests"))
    assert selections.get("/repositories/one") == ("docs", "tests")

    # Removing a folder from the list means it is reviewed again, not that the removal was
    # ignored — so the second recording is the whole answer rather than an addition.
    selections.record("/repositories/one", ("tests",))
    assert selections.get("/repositories/one") == ("tests",)


def test_choosing_to_review_everything_is_not_the_same_as_choosing_nothing(
    tmp_path: Path,
) -> None:
    """`[]` is somebody looking at the folder list and clearing it; absence is nobody asked.

    They analyse identically today and diverge the moment a caller re-indexes without naming
    a scope: the first keeps reviewing everything, and the second would inherit whatever was
    chosen before.
    """

    selections = SQLiteScopeSelectionRepository(_database(tmp_path))

    selections.record("/repositories/whole", ())

    assert selections.get("/repositories/whole") == ()
    assert selections.get("/repositories/untouched") is None


def test_a_recorded_scope_survives_the_connection_that_wrote_it(tmp_path: Path) -> None:
    """`connect()` does not commit on its own, and an uncommitted scope is no scope at all.

    It would read back correctly for the length of the process and be gone on the next one —
    which is precisely when it is needed, since the freshness check that reads it runs long
    after the index that wrote it.
    """

    SQLiteScopeSelectionRepository(_database(tmp_path)).record(
        "/repositories/one", ("tests",)
    )

    reopened = SQLiteScopeSelectionRepository(_database(tmp_path))

    assert reopened.get("/repositories/one") == ("tests",)
