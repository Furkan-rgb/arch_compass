"""Repository analysis, source, freshness, atlas-query and edge-resolution ports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from archcompass.boundary.atlas import (
    Atlas,
    AtlasQuery,
    AtlasQueryResult,
    RepositoryContentIdentity,
)


class RepositoryAnalyzer(Protocol):
    def analyze(self, root: Path, *, excluded_paths: tuple[str, ...] = ()) -> Atlas:
        """The atlas of this repository, less the subtrees named in `excluded_paths`.

        Relative POSIX directory paths, already validated by `domain.scope`: an analyzer
        applies a scope and does not decide what a legal one is. Empty — the default — is
        the whole repository, and analyses exactly what it did before scopes existed.
        """
        ...


#: Which rule admitted a conformance verdict. `strict` is the backend's own subtyping
#: question; `structural` is the relaxed rule — every member present, return types checked,
#: parameters by arity — that credits the ordinary adapter idiom of narrowing a parameter.
ConformanceRule = Literal["strict", "structural"]


@dataclass(frozen=True, order=True)
class ConformanceQuestion:
    """One (class, abstraction) pair to judge, identified by where each is written.

    Identified by path and qualified name rather than by atlas id, because the resolver
    reads source and has never seen an atlas. The caller maps the answer back.
    """

    class_path: str
    class_qualified_name: str
    abstraction_path: str
    abstraction_qualified_name: str


@dataclass(frozen=True, order=True)
class ReferenceQuestion:
    """One reference the parse could not attach to a symbol, by site and spelling.

    The spelling is carried as well as the position because a line may hold several
    references, and the caller has to know which of them an answer belongs to.
    """

    path: str
    line: int
    expression: str


@dataclass(frozen=True)
class EdgeResolutionRequest:
    """Everything to be asked of one repository, in one call.

    Bounded by construction: the caller names the pairs and the sites, so the resolver
    never searches. Both sequences are sorted by the caller and answered in that order —
    two runs on the same commit must produce the same edges in the same order.
    """

    conformances: tuple[ConformanceQuestion, ...] = ()
    references: tuple[ReferenceQuestion, ...] = ()

    def is_empty(self) -> bool:
        return not self.conformances and not self.references


@dataclass(frozen=True)
class ConformanceVerdict:
    """A pair that conforms, and under which rule. Absence is the negative answer."""

    question: ConformanceQuestion
    rule: ConformanceRule


@dataclass(frozen=True)
class ResolvedReference:
    """A site the resolver could name a definition for, as a qualified name.

    The name may be outside the repository — `builtins.list.append` is a correct answer to
    `.append`. Deciding that such a target is not an atlas node is the caller's job.
    """

    question: ReferenceQuestion
    target_qualified_name: str


@dataclass(frozen=True)
class EdgeResolutionResult:
    conformances: tuple[ConformanceVerdict, ...] = ()
    references: tuple[ResolvedReference, ...] = ()


class EdgeResolver(Protocol):
    """A type oracle for edges: does this class satisfy that abstraction, and where does
    this reference land.

    One method wide on purpose. Building a type checker's view of a repository is the
    expensive part, so everything is asked at once and answered from one view; a per-
    question port would rebuild it thousands of times.

    Informs detection, never a verdict — nothing the backend emits (diagnostics, rule
    names, error codes) reaches a model. It names edges, and the edge set is the whole of
    its influence.
    """

    def fingerprint(self) -> Mapping[str, str]:
        """What about this resolver changes the edge set, for the analysis config hash.

        Cheap and callable without a repository: it is read once per analysis to decide
        whether a stored atlas is still the atlas this configuration would produce.
        """
        ...

    def resolve(self, root: Path, request: EdgeResolutionRequest) -> EdgeResolutionResult: ...


class RepositoryIdentityReader(Protocol):
    def current_identity(
        self, root: Path, *, excluded_paths: tuple[str, ...] = ()
    ) -> RepositoryContentIdentity:
        """What this repository fingerprints as now, under the given exclusions.

        The exclusions have to be the ones the stored atlas was built under. A fingerprint
        computed over a different set of files is a different digest, so asking without them
        would report a scoped atlas stale for as long as it exists.
        """
        ...


class SourceReader(Protocol):
    def excerpt(
        self,
        root: Path,
        relative_path: str,
        start_line: int,
        end_line: int,
        *,
        max_lines: int,
        numbered: bool = True,
    ) -> str: ...


class AtlasFreshnessChecker(Protocol):
    def ensure_fresh(self, atlas: Atlas) -> None: ...


class AtlasQueryService(Protocol):
    def execute(self, atlas: Atlas, query: AtlasQuery) -> AtlasQueryResult: ...
