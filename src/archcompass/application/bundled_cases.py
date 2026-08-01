"""Example cases shipped with ArchCompass, loadable into a workspace in one step.

Writing an `ArchitectureCase` by hand is the first thing anyone has to do and the largest
obstacle to trying the tool at all. Each bundled case pairs a written case with a
repository to run it against, so a new workspace can produce a real review immediately.

Loading one indexes its repository and creates the case. Nothing is cached between loads:
the case is created fresh each time, so a user who edits a bundled case's YAML sees the
change, and two loads produce two independent cases rather than silently sharing one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from archcompass.application.repository_index import RepositoryIndexService
from archcompass.domain.case import ArchitectureCase, CaseRevision, RepositoryReference
from archcompass.domain.errors import CaseNotFoundError
from archcompass.ports.repositories import CaseRepository

#: Shipped alongside the package rather than resolved from the working directory, so a
#: workspace opened from anywhere finds the same examples.
BUNDLED_CASE_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "eval" / "cases"


@dataclass(frozen=True)
class BundledCaseSummary:
    name: str
    title: str
    problem_statement: str
    repository_root: str
    #: Whether the case ships an answer key. Nothing in the workspace grades against it —
    #: the offline harness in `scripts/run_boundary_review.py` does — but it marks which
    #: examples have a measured answer behind them.
    has_expected_answers: bool


def _document(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return cast("dict[str, object]", loaded) if isinstance(loaded, dict) else {}


class BundledCaseService:
    def __init__(
        self,
        *,
        cases: CaseRepository,
        repositories: RepositoryIndexService,
        root: Path = BUNDLED_CASE_ROOT,
    ) -> None:
        self._cases = cases
        self._repositories = repositories
        self._root = root

    def list(self) -> list[BundledCaseSummary]:
        summaries: list[BundledCaseSummary] = []
        for directory in sorted(self._root.iterdir() if self._root.is_dir() else []):
            case_file = directory / "case.yaml"
            repository = directory / "repository"
            # Both parts are required. A case without a repository cannot be reviewed and
            # would fail only after the user selected it.
            if not case_file.is_file() or not repository.is_dir():
                continue
            document = _document(case_file)
            summaries.append(
                BundledCaseSummary(
                    name=directory.name,
                    title=str(document.get("title", directory.name)),
                    problem_statement=str(document.get("problem_statement", "")).strip(),
                    repository_root=str(repository.resolve()),
                    has_expected_answers=(directory / "expected.yaml").is_file(),
                )
            )
        return summaries

    def load(self, name: str) -> CaseRevision:
        directory = self._root / name
        case_file = directory / "case.yaml"
        repository = (directory / "repository").resolve()
        if not case_file.is_file() or not repository.is_dir():
            raise CaseNotFoundError(f"No bundled case named {name!r}")
        case = ArchitectureCase.model_validate(_document(case_file))
        # Indexing before creating the case means a load either produces something
        # reviewable or fails outright, rather than leaving a case pointing at an atlas
        # that was never built.
        self._repositories.index(repository)
        case = case.model_copy(
            update={"repository": RepositoryReference(root_path=str(repository))}
        )
        return self._cases.create(case, actor=f"bundled:{name}")
