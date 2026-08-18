from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from archcompass.domain._support import require_text, stable_id

DEFAULT_BRANCH_NAME = "main"


def derive_branch_id(repository_id: str, branch_name: str) -> str:
    return stable_id("branch", repository_id, branch_name)


@dataclass(frozen=True, slots=True)
class RepositoryRef:
    id: str
    path: Path
    branch_id: str
    content_id: str
    remote_url: str | None = None
    branch: str | None = None
    commit: str | None = None

    def __post_init__(self) -> None:
        require_text(self.id, "repository id")
        require_text(self.branch_id, "branch id")
        require_text(self.content_id, "content id")
        if not self.path.is_absolute():
            raise ValueError("repository path must be absolute")
