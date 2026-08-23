from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from archcompass.domain._support import require_text, stable_id

#: The branch a run is attributed to when git will not name one. A detached HEAD is the
#: ordinary shape of a CI checkout, and a non-git directory has no branches at all; neither
#: is a reason to leave a run unattached, because then the first CI run of a repository would
#: share nothing with the workspace runs of the same repository. `main` is a guess, and it is
#: a guess the caller can always override by naming the branch explicitly — which is what CI
#: does, since the branch is in the environment even when it is not in the working tree.
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
