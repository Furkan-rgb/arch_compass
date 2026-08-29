"""What the three detectors do on shapes that real repositories are full of.

Written as probes rather than as guarantees. Each one builds the smallest repository
that produces one behaviour, runs the real analyzer and the real catalogue, and asserts
what came back — so the behaviour can be read off a test run instead of inferred from
the source.

The `xfail(strict=True)` ones are the defects. They state the behaviour the detector's
own docstring promises, they fail today, and they turn the suite red the moment someone
fixes one — which is the point: a fixed defect should force its probe to be rewritten as
an ordinary assertion rather than quietly keep passing as a known failure.

Every case here was found by running the catalogue over installed libraries — httpx,
starlette, anyio, rich, pydantic, langchain_core, anthropic — and then reduced to the
smallest repository that still shows it. The library that produced each one is named.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.analysis.adapters import PythonAstRepositoryAnalyzer
from archcompass.analysis.atlas import Atlas, EdgeType, FindingPattern
from archcompass.analysis.detectors import detect_finding_candidates


def _atlas(root: Path, files: dict[str, str], *, excluded: tuple[str, ...] = ()) -> Atlas:
    for name, source in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return PythonAstRepositoryAnalyzer().analyze(root, excluded_paths=excluded)


def _of(atlas: Atlas, pattern: FindingPattern):
    return [item for item in detect_finding_candidates(atlas) if item.pattern is pattern]


def _measured(candidate) -> dict[str, float]:
    return {item.name: item.value for item in candidate.measurements}


def _ports(count: int, *, shared_surface: bool) -> dict[str, str]:
    """`count` protocols, one conforming class each, by intent."""

    files: dict[str, str] = {}
    for ordinal in range(count):
        suffix = "" if shared_surface else f"_{ordinal}"
        files[f"ports/port_{ordinal}.py"] = (
            "from typing import Protocol\n\n\n"
            f"class Store{ordinal}(Protocol):\n"
            f"    def load{suffix}(self, key: str) -> bytes: ...\n"
            f"    def save{suffix}(self, key: str, value: bytes) -> None: ...\n"
        )
        files[f"adapters/adapter_{ordinal}.py"] = (
            f"class SqlStore{ordinal}:\n"
            f"    def load{suffix}(self, key: str) -> bytes:\n        return b''\n"
            f"    def save{suffix}(self, key: str, value: bytes) -> None:\n        return None\n"
        )
    return files


# ------------------------------------------------------------------ sole implementation


def test_a_port_with_a_double_and_a_test_reference_still_reaches_the_judge(
    tmp_path: Path,
) -> None:
    """The shape the corpus calls correct arrives with no discount applied.

    Nothing between the detector and the model reads the two measurements that exist to
    defend a port. On ArchCompass's own source 34 of 41 candidates are this shape.
    """

    atlas = _atlas(
        tmp_path / "repo",
        {
            "ports.py": (
                "from typing import Protocol\n\n\n"
                "class SpeechProvider(Protocol):\n"
                "    def speak(self, text: str, voice: str) -> bytes: ...\n"
                "    def close(self) -> None: ...\n"
            ),
            "adapters.py": (
                "class QwenSpeech:\n"
                "    def speak(self, text: str, voice: str) -> bytes:\n        return b''\n"
                "    def close(self) -> None:\n        return None\n"
            ),
            "tests/test_speech.py": (
                "from ports import SpeechProvider\n\n\n"
                "class FakeSpeech:\n"
                "    def speak(self, text: str, voice: str) -> bytes:\n        return b'f'\n"
                "    def close(self) -> None:\n        return None\n\n\n"
                "def test_it_speaks() -> None:\n"
                "    provider: SpeechProvider = FakeSpeech()\n"
                "    assert provider.speak('hi', 'a') == b'f'\n"
            ),
        },
    )

    candidates = _of(atlas, FindingPattern.SOLE_IMPLEMENTATION)

    assert len(candidates) == 1
    measured = _measured(candidates[0])
    # Both mitigations are present and measured, and the candidate is emitted anyway.
    assert measured["test_doubles_offering_its_methods"] == 1
    assert measured["test_references_to_abstraction"] == 1


def test_two_protocols_with_one_surface_are_not_attributed_to_a_class(
    tmp_path: Path,
) -> None:
    """Fixed in parser v10. The match is real and it is not evidence about either one.

    A class carrying the surface satisfies both protocols — correct as typing, useless as
    architecture. No conformance edge is recorded, and each abstraction carries an
    `indistinguishable-abstraction-surface` signal so the absence is stated rather than
    read as "nothing implements this".
    """

    atlas = _atlas(
        tmp_path / "repo",
        {
            "ports.py": (
                "from typing import Protocol\n\n\n"
                "class Reader(Protocol):\n"
                "    def read(self, key: str) -> bytes: ...\n"
                "    def close(self) -> None: ...\n\n\n"
                "class Loader(Protocol):\n"
                "    def read(self, key: str) -> bytes: ...\n"
                "    def close(self) -> None: ...\n"
            ),
            "disk.py": (
                "class DiskReader:\n"
                "    def read(self, key: str) -> bytes:\n        return b''\n"
                "    def close(self) -> None:\n        return None\n"
            ),
        },
    )

    assert _of(atlas, FindingPattern.SOLE_IMPLEMENTATION) == []
    assert [edge for edge in atlas.edges if edge.edge_type is EdgeType.IMPLEMENTS] == []
    assert sorted(
        signal.node_id.split(":")[-1] and signal.message.split(" declares")[0]
        for signal in atlas.signals
        if signal.code == "indistinguishable-abstraction-surface"
    ) == ["ports.Loader", "ports.Reader"]


def test_ports_that_share_a_method_surface_report_the_ambiguity(tmp_path: Path) -> None:
    """Same architecture as the test below. Only the method names differ.

    Three ports with one adapter each still produce no candidate, because nothing in the
    source says which adapter belongs to which port — every one of them conforms to every
    one of them. What changed in v10 is that the atlas no longer asserts the cross product
    it cannot support, and says why it is quiet: three signals instead of nine edges and
    three ports each claiming three implementations.
    """

    atlas = _atlas(tmp_path / "shared", _ports(3, shared_surface=True))

    assert _of(atlas, FindingPattern.SOLE_IMPLEMENTATION) == []
    assert [edge for edge in atlas.edges if edge.edge_type is EdgeType.IMPLEMENTS] == []
    assert (
        len([s for s in atlas.signals if s.code == "indistinguishable-abstraction-surface"])
        == 3
    )


def test_ports_with_distinct_surfaces_are_each_sole(tmp_path: Path) -> None:
    """The control for the probe above: rename the operations and all three appear."""

    atlas = _atlas(tmp_path / "distinct", _ports(3, shared_surface=False))

    assert len(_of(atlas, FindingPattern.SOLE_IMPLEMENTATION)) == 3


def test_excluding_the_test_suite_removes_the_evidence_that_clears_a_port(
    tmp_path: Path,
) -> None:
    """`tests` is a suggested exclusion, and excluding it zeroes both mitigations.

    A user who trims the scope to make a review cheaper strips the only two measurements
    that argue for keeping the boundary, and the candidate that reaches the model is the
    one with nothing in its defence.
    """

    files = {
        "ports.py": (
            "from typing import Protocol\n\n\n"
            "class Clock(Protocol):\n"
            "    def now(self) -> int: ...\n"
            "    def sleep(self, seconds: int) -> None: ...\n"
        ),
        "adapters.py": (
            "class SystemClock:\n"
            "    def now(self) -> int:\n        return 0\n"
            "    def sleep(self, seconds: int) -> None:\n        return None\n"
        ),
        "tests/test_clock.py": (
            "from ports import Clock\n\n\n"
            "class FrozenClock:\n"
            "    def now(self) -> int:\n        return 7\n"
            "    def sleep(self, seconds: int) -> None:\n        return None\n\n\n"
            "def test_frozen() -> None:\n"
            "    clock: Clock = FrozenClock()\n"
            "    assert clock.now() == 7\n"
        ),
    }

    whole = _measured(_of(_atlas(tmp_path / "whole", files), FindingPattern.SOLE_IMPLEMENTATION)[0])
    trimmed = _measured(
        _of(
            _atlas(tmp_path / "trimmed", files, excluded=("tests",)),
            FindingPattern.SOLE_IMPLEMENTATION,
        )[0]
    )

    assert whole["test_doubles_offering_its_methods"] == 1
    assert whole["test_references_to_abstraction"] == 1
    assert trimmed["test_doubles_offering_its_methods"] == 0
    assert trimmed["test_references_to_abstraction"] == 0


# ----------------------------------------------------------------- duplicated knowledge


def test_a_typevar_is_not_repeated_knowledge(tmp_path: Path) -> None:
    """Fixed in parser v9, and pinned here because it was the most expensive defect.

    A TypeVar is upper-case, so `_declared_constants` used to record it, and every module
    that declares `T` was reported as repeating knowledge with every other one. It was the
    largest candidate in seven of the nine libraries this suite was built against.
    """

    files = {
        f"pkg/m{ordinal}.py": (
            "from typing import ParamSpec, TypeVar\n\n"
            "T = TypeVar('T')\n"
            "P = ParamSpec('P')\n\n\n"
            f"def work_{ordinal}() -> None:\n    return None\n"
        )
        for ordinal in range(4)
    }

    atlas = _atlas(tmp_path / "repo", files)

    assert _of(atlas, FindingPattern.DUPLICATED_KNOWLEDGE) == []


def test_the_same_name_in_unrelated_packages_is_reported_without_a_relatedness_test(
    tmp_path: Path,
) -> None:
    """Two modules that share a name and share no path in the graph still pair up.

    `scattered_concept` builds a `reach` map for exactly this question and consults it.
    This detector does not, so a coincidence of naming is indistinguishable downstream
    from knowledge that genuinely has two homes.
    """

    atlas = _atlas(
        tmp_path / "repo",
        {
            "billing/client.py": "TIMEOUT = 30\n\n\ndef charge() -> None:\n    return None\n",
            "search/index.py": "TIMEOUT = 30\n\n\ndef reindex() -> None:\n    return None\n",
        },
    )

    candidates = _of(atlas, FindingPattern.DUPLICATED_KNOWLEDGE)

    assert len(candidates) == 1
    assert candidates[0].relationships == []


def test_a_vendored_copy_is_one_finding_about_the_copy(tmp_path: Path) -> None:
    """Fixed by grouping on the module set. pydantic went from 26 candidates to 7.

    It ships `v1/mypy.py` beside `mypy.py`, and the two share fifteen constants. That was
    fifteen findings saying one thing, at about 15,000 input tokens each.
    """

    body = "MAX_LENGTH = 2048\nERROR_CODE = 'x'\nBASE_NAME = 'y'\n"

    candidates = _of(
        _atlas(tmp_path / "repo", {"pkg/settings.py": body, "pkg/v1/settings.py": body}),
        FindingPattern.DUPLICATED_KNOWLEDGE,
    )

    assert len(candidates) == 1
    measured = _measured(candidates[0])
    assert measured["modules_stating_it"] == 2
    assert measured["constants_they_share"] == 3
    assert measured["constants_whose_copies_disagree"] == 0


def test_one_constant_in_two_modules_keeps_the_wording_it_always_had(
    tmp_path: Path,
) -> None:
    """The grouping must not reshape the ordinary finding, or every stored id moves."""

    candidates = _of(
        _atlas(
            tmp_path / "repo",
            {"alpha.py": "VOICES = ('a', 'b')\n", "beta.py": "VOICES = ('a', 'b')\n"},
        ),
        FindingPattern.DUPLICATED_KNOWLEDGE,
    )

    assert len(candidates) == 1
    assert candidates[0].summary == "VOICES is stated in 2 modules with the same value."


# -------------------------------------------------------------------- scattered concept


@pytest.mark.xfail(
    strict=True,
    reason=(
        "`_names_things_after_itself` asks whether the module's word leads an identifier "
        "it declares, to tell a proper noun (`QwenSpeechProvider`) from a category word. "
        "`BaseMessage` leads with `base` and passes, so `base` counts as a concept and "
        "the whole repository is full of the word. The shared-stem guard removes the cases "
        "where several modules answer to the name — `base` (13 owners), `fake`, `image`, "
        "`string` — which is 8 of langchain_core's 15. This is the remainder: a category "
        "word owned by exactly one module. Four separating rules were measured against the "
        "corpus and the bundled examples and none of them works; see the entry in "
        "docs/known-defects.md. Strict, so a rule that does work turns the suite red."
    ),
)
def test_a_module_named_for_a_category_word_is_not_a_scattered_concept(
    tmp_path: Path,
) -> None:
    """Reduced from langchain_core's `messages/base.py`.

    The guard compares the module's name against the *abstraction it implements*, so a
    class named `BaseMessage` behind a `Serializable` protocol never gets caught: nothing
    in `Serializable` shares a stem with `base`.
    """

    files = {
        "load/serializable.py": (
            "from typing import Protocol\n\n\n"
            "class Serializable(Protocol):\n"
            "    def to_json(self) -> str: ...\n"
            "    def from_json(self, raw: str) -> None: ...\n"
        ),
        "messages/base.py": (
            "class BaseMessage:\n"
            "    def to_json(self) -> str:\n        return '{}'\n"
            "    def from_json(self, raw: str) -> None:\n        return None\n"
        ),
    }
    for ordinal in range(5):
        files[f"chains/chain_{ordinal}.py"] = (
            f"BASE_PATH = '/tmp/{ordinal}'\n\n\n"
            f"class Chain{ordinal}:\n"
            "    def base(self) -> str:\n        return BASE_PATH\n"
        )

    atlas = _atlas(tmp_path / "repo", files)

    assert _of(atlas, FindingPattern.SCATTERED_CONCEPT) == []


def test_a_name_several_modules_answer_to_owns_nothing(tmp_path: Path) -> None:
    """The shared-stem guard, reduced from langchain_core's thirteen `base.py` files.

    Every concept the bundled examples are designed around — `qwen`, `ollama`,
    `northwind` — is the only module of its name, so the guard costs them nothing.
    """

    files = {
        "load/serializable.py": (
            "from typing import Protocol\n\n\n"
            "class Serializable(Protocol):\n"
            "    def to_json(self) -> str: ...\n"
            "    def from_json(self, raw: str) -> None: ...\n"
        ),
        "messages/base.py": (
            "class BaseMessage:\n"
            "    def to_json(self) -> str:\n        return '{}'\n"
            "    def from_json(self, raw: str) -> None:\n        return None\n"
        ),
        # A second module of the same name, which is what makes `base` a kind of file.
        "tracers/base.py": "class BaseTracer:\n    def start(self) -> None:\n        return None\n",
    }
    for ordinal in range(5):
        files[f"chains/chain_{ordinal}.py"] = (
            f"BASE_PATH = '/tmp/{ordinal}'\n\n\n"
            f"class Chain{ordinal}:\n"
            "    def base(self) -> str:\n        return BASE_PATH\n"
        )

    atlas = _atlas(tmp_path / "repo", files)

    assert _of(atlas, FindingPattern.SCATTERED_CONCEPT) == []
