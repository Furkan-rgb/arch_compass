"""Reviewing part of a repository, over HTTP: choosing the scope, and living with the choice.

The endpoints are two halves of one thing. The listing exists so the choice can be made with
the sizes in front of the reader, and the index applies it — but the part that is easy to get
wrong is neither: it is everything afterwards, where something asks the repository whether the
stored atlas is still true and has to ask the same question the analysis answered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.presentation.web import create_app
from archcompass.reasoning.adapters.providers import DETERMINISTIC_MODEL

#: A repository with an obvious thing to leave out and an obvious thing to keep. `tests` is
#: bigger than `src`, which is the situation that makes a scope worth having.
_REPOSITORY = {
    "src/service.py": "class Service:\n    def serve(self) -> int:\n        return 1\n",
    "src/__init__.py": "",
    "src/vendor/copied.py": "def copied() -> int:\n    return 2\n",
    "tests/test_service.py": (
        "def test_serve() -> None:\n    assert True\n\n\n"
        "def test_again() -> None:\n    assert True\n"
    ),
    "tests/__init__.py": "",
    "docs/conf.py": "project = 'thing'\n",
    "README.md": "# Not Python\n",
    "__pycache__/stale.py": "unreadable = (\n",
}


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    for name, content in _REPOSITORY.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


@pytest.fixture
def workspace(tmp_path: Path) -> Runtime:
    """A workspace beside the repository rather than inside it.

    An analysis leaves out whatever the workspace owns, so a repository containing the
    workspace analysing it would come back empty and every assertion here would pass for
    the wrong reason.
    """

    return build_runtime(
        tmp_path / "workspace", pin=pinned_model("fake", DETERMINISTIC_MODEL)
    )


def _paths(runtime: Runtime, version_id: str) -> set[str]:
    return {node.path for node in runtime.atlas_repository.get(version_id).nodes}


def test_the_folder_listing_says_what_is_there_and_what_it_would_cost(
    workspace: Runtime, repository: Path
) -> None:
    with TestClient(create_app(workspace)) as client:
        listed = client.post(
            "/api/repositories/tree", json={"root_path": str(repository)}
        )

        assert listed.status_code == 200, listed.text
        body = listed.json()
        folders = {item["path"]: item for item in body["folders"]}
        # Two levels deep, directories with Python under them only, and nothing the analysis
        # would refuse to look at: `__pycache__` is not offered as a choice because it is
        # never analysed in the first place.
        assert set(folders) == {"docs", "src", "src/vendor", "tests"}
        assert folders["tests"]["python_files"] == 2
        # A child's Python counts in its parent's total, because the number answers "what
        # would excluding this save" and excluding `src` would save `src/vendor` too.
        assert folders["src"]["python_files"] == 3
        assert folders["src"]["python_bytes"] > folders["src/vendor"]["python_bytes"] > 0
        assert body["total_python_files"] == 6
        # Advisory and nothing more: `docs` and `tests` look skippable by their names, and
        # `src/vendor` does not, however much of it there is.
        assert folders["tests"]["suggested"] is True
        assert folders["docs"]["suggested"] is True
        assert folders["src/vendor"]["suggested"] is False


def test_an_indexed_repository_leaves_out_the_folders_the_request_named(
    workspace: Runtime, repository: Path
) -> None:
    with TestClient(create_app(workspace)) as client:
        indexed = client.post(
            "/api/repositories/index",
            json={"root_path": str(repository), "excluded_paths": ["tests"]},
        )

        assert indexed.status_code == 201, indexed.text
        paths = _paths(workspace, indexed.json()["version_id"])
        assert "src/service.py" in paths
        assert not any(path.startswith("tests") for path in paths)


def test_indexing_again_without_saying_so_keeps_the_scope_that_was_chosen(
    workspace: Runtime, repository: Path
) -> None:
    """The old payload still works, and it does not silently widen a narrowed review.

    Same fingerprint across the two, which is the whole claim: the second analysis read the
    same files as the first, so it left `tests` out without being told to a second time.
    """

    with TestClient(create_app(workspace)) as client:
        scoped = client.post(
            "/api/repositories/index",
            json={"root_path": str(repository), "excluded_paths": ["tests"]},
        )
        assert scoped.status_code == 201, scoped.text

        again = client.post(
            "/api/repositories/index", json={"root_path": str(repository)}
        )

        assert again.status_code == 201, again.text
        assert (
            again.json()["content_fingerprint"] == scoped.json()["content_fingerprint"]
        )
        assert not any(
            path.startswith("tests") for path in _paths(workspace, again.json()["version_id"])
        )


def test_a_scoped_atlas_is_not_reported_stale_the_moment_it_is_read(
    workspace: Runtime, repository: Path
) -> None:
    """The reason the choice is stored at all.

    Reading a stored atlas recomputes the repository's fingerprint first. Recomputed without
    the exclusions, it reads the folders the analysis skipped, disagrees with itself, and
    reports the atlas stale — permanently, since re-indexing lands in the same place.
    """

    with TestClient(create_app(workspace)) as client:
        indexed = client.post(
            "/api/repositories/index",
            json={"root_path": str(repository), "excluded_paths": ["tests", "docs"]},
        )
        assert indexed.status_code == 201, indexed.text

        summary = client.get(
            "/api/repositories/summary", params={"root_path": str(repository)}
        )

        assert summary.status_code == 200, summary.text


def test_a_folder_that_could_name_somewhere_else_is_refused_as_a_scope(
    workspace: Runtime, repository: Path
) -> None:
    with TestClient(create_app(workspace)) as client:
        refused = client.post(
            "/api/repositories/index",
            json={"root_path": str(repository), "excluded_paths": ["../x"]},
        )

        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "validation_error"
