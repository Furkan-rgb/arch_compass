from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from archcompass.domain._support import require_text


@dataclass(frozen=True, slots=True)
class SourceLocation:
    path: str
    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        require_text(self.path, "path")
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError("source lines must be positive and ordered")


@dataclass(frozen=True, slots=True)
class Evidence:
    description: str
    location: SourceLocation | None = None
    excerpt: str | None = None
    #: A caption about the text, when the text needs one — a span the excerpt ceiling cut
    #: short, or lines widened upward to carry a definition's leading comment. Carried
    #: beside the code rather than folded into it, so a reader or a model can repeat the
    #: caveat without mistaking it for a line of the file.
    note: str | None = None

    def __post_init__(self) -> None:
        require_text(self.description, "description")


class MetricNature(StrEnum):
    """How directly a measured value represents repository structure.

    The distinction is the whole point of carrying it. `dependants_of_abstraction = 0` is a
    `STRUCTURAL_PROXY`: it counts statically resolvable references, so it reads zero both
    for an abstraction nothing uses and for one reached only through wiring the parse
    cannot see. A judge shown the bare number cannot tell those apart, and the two lead to
    opposite verdicts.
    """

    MEASUREMENT = "objective_measurement"
    STRUCTURAL_PROXY = "structural_proxy"


@dataclass(frozen=True, slots=True)
class Measurement:
    """One quantity that establishes a candidate's pattern, with its own honesty attached.

    The value stays numeric rather than pre-formatted. A reader wants "0 references" and
    gets it from `display`, but grouping candidates by shape has to bucket on the number
    itself, and a string that has to be parsed back is a number that has been lost.
    """

    name: str
    value: float
    unit: str = ""
    nature: MetricNature = MetricNature.MEASUREMENT
    definition: str = ""
    limitations: str = ""

    def __post_init__(self) -> None:
        require_text(self.name, "measurement name")

    @property
    def display(self) -> str:
        return f"{self.value:g} {self.unit}".strip()


@dataclass(frozen=True, slots=True)
class Relationship:
    """One edge between a candidate's participants, named the way a reader names them.

    Qualified names rather than atlas node ids. An id is an internal handle — it means
    nothing to a person reading a finding and nothing to a model judging one — so it is
    resolved at the boundary where the atlas is still in hand.

    `resolved_by` is carried because it is a confidence statement: `parse` is the static
    AST resolution that always runs, `types` is the type checker's own answer. An edge the
    parser guessed at and an edge mypy confirmed are not the same evidence.
    """

    source: str
    target: str
    kind: str
    resolved_by: str = "parse"

    def __post_init__(self) -> None:
        require_text(self.source, "relationship source")
        require_text(self.target, "relationship target")
        require_text(self.kind, "relationship kind")
