"""Example repositories shipped with ArchCompass, indexable in one step.

Each example is a repository and a manifest naming it — no case. A visitor picks one, the
review runs against the code alone, and the questions it comes back with are what write the
case. Shipping a case with the repository would hand over the answers
and hide the flow the product is: the first pass would conclude instead of asking.

Nothing is cached between loads. Indexing again is how an edited example repository is
picked up, and it is cheap enough that skipping it would only trade a re-parse for a stale
atlas.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from archcompass.analysis.atlas import AtlasVersion
from archcompass.domain.errors import ExampleNotFoundError
from archcompass.repositories.service import RepositoryIndexService

#: Shipped alongside the package rather than resolved from the working directory, so a
#: workspace opened from anywhere finds the same examples.
BUNDLED_EXAMPLE_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent / "eval" / "cases"
)


@dataclass(frozen=True)
class BundledExampleSummary:
    name: str
    title: str
    #: One sentence about what the repository is, for the reader choosing between them.
    #: Never what the review will find: that is the run's to say, not the manifest's.
    description: str
    repository_root: str


def _manifest(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return cast("dict[str, object]", loaded) if isinstance(loaded, dict) else {}


class BundledExampleService:
    def __init__(
        self,
        *,
        repositories: RepositoryIndexService,
        root: Path = BUNDLED_EXAMPLE_ROOT,
    ) -> None:
        self._repositories = repositories
        self._root = root

    def list(self) -> list[BundledExampleSummary]:
        summaries: list[BundledExampleSummary] = []
        for directory in sorted(self._root.iterdir() if self._root.is_dir() else []):
            manifest = directory / "example.yaml"
            repository = directory / "repository"
            # Both parts are required. A manifest without a repository cannot be reviewed
            # and would fail only after the visitor had chosen it.
            if not manifest.is_file() or not repository.is_dir():
                continue
            document = _manifest(manifest)
            summaries.append(
                BundledExampleSummary(
                    name=directory.name,
                    title=str(document.get("title", directory.name)),
                    description=str(document.get("description", "")).strip(),
                    repository_root=str(repository.resolve()),
                )
            )
        return summaries

    def load(self, name: str) -> AtlasVersion:
        """Index the example's repository and answer with the atlas it produced.

        The caller then continues exactly as it would with a repository a user picked
        themselves — same route, same empty case, same questions. An example that took its
        own path through the application would demonstrate something nobody else gets.
        """

        directory = self._root / name
        repository = (directory / "repository").resolve()
        if not (directory / "example.yaml").is_file() or not repository.is_dir():
            raise ExampleNotFoundError(f"No bundled example named {name!r}")
        return self._repositories.index(repository)
