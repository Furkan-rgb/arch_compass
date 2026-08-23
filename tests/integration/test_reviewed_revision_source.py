"""Source lookups answer from the revision the review judged, not from the tree today.

The distinction is the whole of a reproducible review. An atlas's line spans belong to one
revision; pointed at any other they name different code, so reading the working tree is
right only while the tree still is what was judged. That is why reading source was guarded
by a freshness check — and why the guard could only refuse, because there was nothing else
to read.

A review records the commit it judged, so there is something else to read. These tests pin
both halves: the reviewed revision is what comes back, and where git cannot serve it the old
refusal still stands rather than the tree being read as though it were the same code.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from archcompass.analysis.adapters.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.analysis.adapters.query_service import DeterministicAtlasQueryService
from archcompass.analysis.adapters.source_reader import SafeSourceReader
from archcompass.analysis.atlas import Atlas, SourceExcerptQuery
from archcompass.domain.errors import StaleAtlasError


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """A committed repository whose one file then changes on disk."""

    root = tmp_path / "project"
    (root / "app").mkdir(parents=True)
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "gateway.py").write_text(
        '"""The payment gateway."""\n\n\nclass Gateway:\n'
        "    def charge(self) -> str:\n"
        '        return "as it was reviewed"\n',
        encoding="utf-8",
    )
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "the reviewed revision")
    return root


def _atlas(root: Path) -> Atlas:
    return PythonAstRepositoryAnalyzer().analyze(root)


def _node_id(atlas: Atlas, qualified_name: str) -> str:
    return next(
        node.atlas_id for node in atlas.nodes if node.qualified_name == qualified_name
    )


class _AlwaysStale:
    def ensure_fresh(self, atlas: Atlas) -> None:
        raise StaleAtlasError("the repository has moved since this atlas was built")


def _read(atlas: Atlas, root: Path, *, stale: bool) -> str:
    service = DeterministicAtlasQueryService(
        SafeSourceReader(), _AlwaysStale() if stale else None
    )
    result = service.execute(
        atlas,
        SourceExcerptQuery(kind="source_excerpt", node_id=_node_id(atlas, "app.gateway.Gateway")),
    )
    return result.excerpts[0].text


def test_the_reviewed_revision_is_read_even_after_the_file_changes(
    repository: Path,
) -> None:
    """The review's own commit, asked for by name, however far the checkout has moved.

    Before this, the freshness check refused the read outright: correct, in that the tree
    was no longer what was judged, and useless, in that the reviewed source was sitting in
    git the whole time. A model investigating a hinge on a repository somebody had since
    edited was told it could not look rather than being shown what it had judged.
    """

    atlas = _atlas(repository)
    (repository / "app" / "gateway.py").write_text(
        '"""The payment gateway."""\n\n\nclass Gateway:\n'
        "    def charge(self) -> str:\n"
        '        return "rewritten since the review"\n',
        encoding="utf-8",
    )

    # Stale by construction: if the tree were being read, this would refuse.
    text = _read(atlas, repository, stale=True)

    assert "as it was reviewed" in text, text
    assert "rewritten since the review" not in text, text


def test_an_unversioned_repository_still_refuses_a_tree_that_has_moved(
    tmp_path: Path,
) -> None:
    """The fallback, and it has to stay a refusal.

    With no git there is no reviewed revision to ask for, so the working tree is the only
    source there is — and reading it once it has moved would answer with lines the atlas's
    spans no longer name. Refusing is the honest outcome and the one that was always there.
    """

    root = tmp_path / "loose"
    (root / "app").mkdir(parents=True)
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "gateway.py").write_text(
        "class Gateway:\n    def charge(self) -> str:\n        return 'x'\n",
        encoding="utf-8",
    )
    atlas = _atlas(root)

    assert not atlas.version.git_commit_sha
    with pytest.raises(StaleAtlasError):
        _read(atlas, root, stale=True)


def test_a_current_checkout_reads_the_same_source_either_way(repository: Path) -> None:
    """The ordinary case, where both routes exist and must not disagree."""

    atlas = _atlas(repository)

    assert "as it was reviewed" in _read(atlas, repository, stale=False)
