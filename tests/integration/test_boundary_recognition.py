"""Which shapes the parser recognises as a boundary, written out one at a time.

Every case here was a real miss found by running the detector over a working repository
rather than over a fixture. That matters for how they are written: the point is not that
some code parses, it is that a boundary a person would obviously name gets a verdict
instead of silently not existing.

A missed boundary is the worst failure this system has. It is not reported as an error and
it is not reported as cleared — the review simply says nothing about it, and a reader is
told "no boundary of a detectable shape was found", which reads as approval.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from archcompass.analysis.adapters import PythonAstRepositoryAnalyzer
from archcompass.analysis.atlas import NodeType
from archcompass.analysis.detectors import detect_finding_candidates


def _atlas(tmp_path: Path, source: str):
    module = tmp_path / "probe"
    module.mkdir()
    (module / "shapes.py").write_text(source, encoding="utf-8")
    return PythonAstRepositoryAnalyzer().analyze(module)


def _kinds(atlas) -> dict[str, str]:
    return {
        node.qualified_name.split(".")[-1]: node.node_type.value
        for node in atlas.nodes
        if node.node_type in (NodeType.INTERFACE, NodeType.CLASS)
    }


def _candidates(atlas) -> set[str]:
    """Each candidate as `abstraction->implementation`.

    Direction is part of the assertion, not decoration: a live run reported an adapter as
    the abstraction and its port as the implementation, which a set of names alone would
    have called a pass.
    """

    return {
        f"{found.participants[0].qualified_name.split('.')[-1]}"
        f"->{found.participants[1].qualified_name.split('.')[-1]}"
        for found in detect_finding_candidates(atlas)
    }


PORT_SHAPES = [
    pytest.param(
        """
        from typing import Protocol
        class Port(Protocol):
            def alpha(self, a: int, b: int) -> int: ...
        class Adapter(Port):
            def alpha(self, a: int, b: int) -> int: return a
        """,
        id="protocol",
    ),
    pytest.param(
        """
        from typing import Protocol, TypeVar
        T = TypeVar("T")
        class Port(Protocol[T]):
            def alpha(self, a: int, b: int) -> int: ...
        class Adapter(Port[str]):
            def alpha(self, a: int, b: int) -> int: return a
        """,
        id="generic-protocol",
    ),
    pytest.param(
        """
        from typing import Protocol as Renamed
        class Port(Renamed):
            def alpha(self, a: int, b: int) -> int: ...
        class Adapter(Port):
            def alpha(self, a: int, b: int) -> int: return a
        """,
        id="aliased-protocol-import",
    ),
    pytest.param(
        """
        from abc import ABC, abstractmethod
        class Port(ABC):
            @abstractmethod
            def alpha(self, a: int, b: int) -> int: ...
        class Adapter(Port):
            def alpha(self, a: int, b: int) -> int: return a
        """,
        id="abc",
    ),
    pytest.param(
        """
        import abc
        class Port(abc.ABC):
            def alpha(self, a: int, b: int) -> int: ...
        class Adapter(Port):
            def alpha(self, a: int, b: int) -> int: return a
        """,
        id="dotted-abc",
    ),
    pytest.param(
        """
        from abc import ABCMeta
        class Port(metaclass=ABCMeta):
            def alpha(self, a: int, b: int) -> int: ...
        class Adapter(Port):
            def alpha(self, a: int, b: int) -> int: return a
        """,
        id="abcmeta-keyword",
    ),
    pytest.param(
        """
        from typing import Protocol
        class Port(Protocol):
            def alpha(self, a: int, b: int) -> int: ...
            def beta(self) -> None: ...
        class Adapter:
            def alpha(self, a: int, b: int) -> int: return a
            def beta(self) -> None: return None
        """,
        id="structural-conformance-without-inheritance",
    ),
]


@pytest.mark.parametrize("source", PORT_SHAPES)
def test_every_spelling_of_a_port_yields_one_candidate(tmp_path: Path, source: str) -> None:
    """One abstraction, one implementation, however the abstraction was written.

    Parametrised rather than written out, because the assertion is identical each time and
    the only thing that varies is the syntax. Each of these was a silent miss.
    """

    atlas = _atlas(tmp_path, dedent(source).strip() + "\n")

    assert _kinds(atlas)["Port"] == "interface"
    assert _kinds(atlas)["Adapter"] == "class"
    assert _candidates(atlas) == {"Port->Adapter"}


def test_a_port_named_protocol_does_not_swallow_its_own_adapter(tmp_path: Path) -> None:
    """The bug that deleted a boundary rather than reporting it wrongly.

    Classification once matched the *written name* of a base, so any subclass of a port
    called `*Protocol` was itself classified an abstraction. The detector excludes
    abstractions from an implementation count, so the port dropped to zero implementations
    and disappeared. Two identical structures differing only in the port's name proved it:
    `Clock` was found, `GaugeProtocol` was not.
    """

    atlas = _atlas(
        tmp_path,
        """
from typing import Protocol


class Clock(Protocol):
    def alpha(self, a: int, b: int) -> int: ...


class SystemClock(Clock):
    def alpha(self, a: int, b: int) -> int: return a


class GaugeProtocol(Protocol):
    def bravo(self, c: float, d: float) -> float: ...


class SystemGauge(GaugeProtocol):
    def bravo(self, c: float, d: float) -> float: return c
""",
    )

    assert _kinds(atlas)["SystemGauge"] == "class"
    assert _candidates(atlas) == {"Clock->SystemClock", "GaugeProtocol->SystemGauge"}


def test_an_adapter_may_narrow_a_return_and_widen_its_parameters(tmp_path: Path) -> None:
    """A correct adapter differs from its port in exactly the ways matching once rejected.

    Returning the concrete type the abstraction hides is what a port is *for*, and adding
    an optional parameter still honours every call the protocol promises. Comparing
    annotations as strings treated both as evidence the two were unrelated, so every
    honestly written adapter in a real repository failed to match.
    """

    atlas = _atlas(
        tmp_path,
        """
from pathlib import Path
from typing import Protocol


class Voice(Protocol):
    \"\"\"An opaque handle the port hands back.\"\"\"


class ConcreteVoice:
    \"\"\"What the adapter actually returns.\"\"\"


class SpeechPort(Protocol):
    def load_voice(self, spec: str) -> Voice: ...
    def voices(self) -> tuple[str, ...]: ...
    def close(self) -> None: ...


class VendorSpeech:
    def load_voice(self, spec: str) -> ConcreteVoice: return ConcreteVoice()
    def voices(self, root: Path | None = None) -> tuple[str, ...]: return ()
    def close(self) -> None: return None
""",
    )

    assert "SpeechPort->VendorSpeech" in _candidates(atlas)


def test_a_contradicting_signature_is_still_not_an_implementation(tmp_path: Path) -> None:
    """Relaxing the match must not make it meaningless.

    Two builtins disagreeing is a real contradiction — nothing about abstraction turns an
    `int` parameter into a `str` one — and a class that merely shares a method name is not
    an implementation of anything.
    """

    atlas = _atlas(
        tmp_path,
        """
from typing import Protocol


class Port(Protocol):
    def alpha(self, a: int, b: int) -> int: ...
    def beta(self) -> None: ...


class Unrelated:
    def alpha(self, a: str, b: str) -> str: return a
    def beta(self) -> None: return None
""",
    )

    assert _candidates(atlas) == set()


def test_one_shared_method_name_is_not_enough_on_its_own(tmp_path: Path) -> None:
    """The evidence bar moved from each method to the class; it did not disappear.

    A single unannotated operation is a name collision waiting to happen, so a lone
    operation still has to earn the match with annotations. What changed is that a
    no-argument method no longer makes an eight-method port unmatchable.
    """

    atlas = _atlas(
        tmp_path,
        """
from typing import Protocol


class Port(Protocol):
    def close(self): ...


class Unrelated:
    def close(self): return None
""",
    )

    assert _candidates(atlas) == set()


def test_a_plain_base_class_is_not_a_boundary(tmp_path: Path) -> None:
    """Unchanged, and stated so the relaxation above cannot quietly swallow it."""

    atlas = _atlas(
        tmp_path,
        """
class Base:
    def alpha(self, a: int, b: int) -> int: raise NotImplementedError


class Concrete(Base):
    def alpha(self, a: int, b: int) -> int: return a
""",
    )

    assert _kinds(atlas)["Base"] == "class"
    assert _candidates(atlas) == set()
