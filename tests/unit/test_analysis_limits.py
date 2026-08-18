"""What an analysis will take on, and what it survives.

The repository being analysed is not always the analyst's own. Where it is not, every one of
these is the difference between a bad file and a failed run — and a failed run somebody else
can cause on purpose by committing one file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.adapters.analysis.ast_analyzer import (
    UNLIMITED_ANALYSIS,
    AnalysisLimits,
    PythonAstRepositoryAnalyzer,
)
from archcompass.boundary.atlas import NodeType
from archcompass.domain.errors import PathValidationError


def _repository(root: Path, files: dict[str, bytes]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return root


def _paths(atlas) -> set[str]:
    return {node.path for node in atlas.nodes}


def test_a_file_that_is_not_utf8_is_read_rather_than_ending_the_run(tmp_path: Path) -> None:
    """One undecodable file used to fail the analysis of everything around it."""

    root = _repository(
        tmp_path,
        {
            "good.py": b"value = 1\n",
            # Valid latin-1, not valid UTF-8.
            "legacy.py": "caf\xe9 = 1\n".encode("latin-1"),
        },
    )

    atlas = PythonAstRepositoryAnalyzer().analyze(root)

    assert "good.py" in _paths(atlas)
    assert "legacy.py" in _paths(atlas)


def test_source_nested_past_the_parser_is_a_signal_rather_than_a_crash(
    tmp_path: Path,
) -> None:
    """Syntactically valid, and CPython's parser still cannot get through it."""

    root = _repository(
        tmp_path,
        {
            "fine.py": b"value = 1\n",
            "deep.py": ("x = " + "[" * 20_000 + "]" * 20_000 + "\n").encode("utf-8"),
        },
    )

    atlas = PythonAstRepositoryAnalyzer().analyze(root)

    assert "fine.py" in _paths(atlas)
    assert any(signal.code == "parse-error" for signal in atlas.signals)


def test_a_file_over_the_cap_is_left_out_without_being_read(tmp_path: Path) -> None:
    root = _repository(
        tmp_path,
        {"small.py": b"value = 1\n", "huge.py": b"# padding\n" * 5_000},
    )

    atlas = PythonAstRepositoryAnalyzer(limits=AnalysisLimits(max_file_bytes=1024)).analyze(
        root
    )

    assert "small.py" in _paths(atlas)
    assert "huge.py" not in _paths(atlas)


def test_a_repository_of_many_files_stops_at_the_cap(tmp_path: Path) -> None:
    root = _repository(tmp_path, {f"module_{index}.py": b"x = 1\n" for index in range(40)})

    atlas = PythonAstRepositoryAnalyzer(limits=AnalysisLimits(max_files=10)).analyze(root)

    modules = [node for node in atlas.nodes if node.node_type is NodeType.MODULE]
    assert len(modules) == 10


def test_an_environment_file_is_kept_or_left_out_as_the_deployment_says(
    tmp_path: Path,
) -> None:
    """An excerpt reaches the model provider, so a stranger's `.env` is not ours to send."""

    root = _repository(tmp_path, {"app.py": b"x = 1\n", ".env": b"SECRET=hunter2\n"})

    kept = PythonAstRepositoryAnalyzer().analyze(root)
    withheld = PythonAstRepositoryAnalyzer(
        limits=AnalysisLimits(include_environment_files=False)
    ).analyze(root)

    assert ".env" in _paths(kept)
    assert ".env" not in _paths(withheld)
    assert "app.py" in _paths(withheld)


def test_an_unlimited_analysis_hashes_as_it_always_did(tmp_path: Path) -> None:
    """A cap makes a different atlas; the absence of one must not make a different hash.

    Otherwise adding this feature would have marked every stored atlas in every workspace
    stale, and charged every existing user a full re-analysis to record that nothing had
    changed about theirs.
    """

    root = _repository(tmp_path, {"app.py": b"x = 1\n"})
    unlimited = PythonAstRepositoryAnalyzer().analyze(root).version.analysis_config_hash
    explicit = (
        PythonAstRepositoryAnalyzer(limits=UNLIMITED_ANALYSIS)
        .analyze(root)
        .version.analysis_config_hash
    )
    capped = (
        PythonAstRepositoryAnalyzer(limits=AnalysisLimits(max_files=10))
        .analyze(root)
        .version.analysis_config_hash
    )

    assert unlimited == explicit
    assert capped != unlimited


def test_mypy_is_never_given_the_analysed_repositorys_own_configuration() -> None:
    """The load-bearing fact behind "a fetched repository is parsed, never executed".

    mypy loads plugins — arbitrary Python, imported and run — only from a config file, and
    only `mypy.main` goes looking for one. This resolver builds `Options()` itself and calls
    `build.build` directly, so a `mypy.ini` or a `[tool.mypy] plugins = ...` in somebody's
    repository is never read.

    Pinned as a test rather than left as a comment because it is invisible: nothing in the
    resolver mentions plugins, and a future change that started discovering config would look
    like a small improvement right up until it ran a stranger's code.
    """

    pytest.importorskip("mypy")
    from mypy.options import Options

    options = Options()

    assert options.config_file is None
    assert options.plugins == []


def test_a_repository_larger_than_this_workspace_analyses_is_refused(tmp_path: Path) -> None:
    """Refused, not trimmed. An atlas with holes is a review confidently wrong about them."""

    root = _repository(
        tmp_path, {f"module_{index}.py": b"x = 1\n" * 200 for index in range(40)}
    )

    with pytest.raises(PathValidationError, match="MB of Python"):
        PythonAstRepositoryAnalyzer(
            limits=AnalysisLimits(max_python_bytes=8_000)
        ).analyze(root)


def test_a_repository_within_the_cap_is_analysed_as_usual(tmp_path: Path) -> None:
    root = _repository(tmp_path, {"app.py": b"value = 1\n"})

    atlas = PythonAstRepositoryAnalyzer(
        limits=AnalysisLimits(max_python_bytes=1 << 20)
    ).analyze(root)

    assert "app.py" in _paths(atlas)


def test_a_repository_with_more_in_it_than_the_cap_is_refused(tmp_path: Path) -> None:
    """Density, not size: the byte cap cannot see a small repository full of definitions."""

    root = _repository(
        tmp_path,
        {
            f"module_{index}.py": b"\n".join(
                f"def function_{item}(): pass".encode() for item in range(20)
            )
            for index in range(20)
        },
    )

    with pytest.raises(PathValidationError, match="more in it than"):
        PythonAstRepositoryAnalyzer(limits=AnalysisLimits(max_nodes=50)).analyze(root)


def test_the_node_cap_stops_before_the_whole_repository_is_parsed(tmp_path: Path) -> None:
    """Checked between files, so the memory the cap protects is never spent."""

    parsed: list[str] = []
    root = _repository(
        tmp_path, {f"module_{index}.py": b"class Thing: pass\n" for index in range(50)}
    )
    analyzer = PythonAstRepositoryAnalyzer(limits=AnalysisLimits(max_nodes=10))
    original = analyzer._parse_module

    def counting(*args, **kwargs):
        result = original(*args, **kwargs)
        parsed.append(result.relative_path)
        return result

    analyzer._parse_module = counting  # type: ignore[method-assign]
    with pytest.raises(PathValidationError):
        analyzer.analyze(root)

    assert len(parsed) < 50, "every file was parsed before the cap was noticed"


def test_a_repository_inside_the_node_cap_is_analysed(tmp_path: Path) -> None:
    root = _repository(tmp_path, {"app.py": b"class Thing:\n    def run(self): pass\n"})

    atlas = PythonAstRepositoryAnalyzer(limits=AnalysisLimits(max_nodes=1_000)).analyze(root)

    assert "app.py" in _paths(atlas)
