from __future__ import annotations

from dataclasses import dataclass

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

    def __post_init__(self) -> None:
        require_text(self.description, "description")
