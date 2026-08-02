"""Shared AST and file-selection helpers for Python repository analysis.

The analyzer core and the boundary-preparation detectors both need to walk one
lexical body, find the syntax behind an Atlas node, and mint an edge. Keeping these
here lets the detectors live in their own module without either importing the other.

The subtree-exclusion pair is here for the same reason: the analyzer and the type
resolver each build their own file list, and they have to leave out the same files or
the resolver would answer about code the atlas has no nodes for.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from archcompass.domain.atlas import AtlasEdge, AtlasNode, EdgeType, SourceLocation
from archcompass.domain.base import stable_id


@dataclass
class ParsedModule:
    """One parsed source file and the Atlas identities derived from it."""

    path: Path
    relative_path: str
    qualified_name: str
    node: AtlasNode
    tree: ast.Module
    source: str
    symbols: dict[str, AtlasNode] = field(default_factory=dict[str, AtlasNode])
    import_aliases: dict[str, str] = field(default_factory=dict[str, str])


def module_name(relative_path: str) -> str:
    """The dotted name a repository-relative source path is imported under.

    Shared with the type-aware resolver, which has to hand the same names to its backend or
    the qualified names it answers with will not line up with the atlas's own.
    """

    parts = relative_path.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or "__root__"


def canonical_roots(roots: Iterable[Path]) -> tuple[Path, ...]:
    """Excluded subtrees as absolute, symlink-free paths, resolved once."""

    return tuple(sorted(root.expanduser().resolve() for root in roots))


def excluded_within(root: Path, excluded_roots: tuple[Path, ...]) -> tuple[Path, ...]:
    """The excluded subtrees that lie strictly inside this repository.

    A root equal to or containing the repository is dropped rather than honoured. The
    ArchCompass workspace is excluded so that a repository holding one can still be
    analysed; a workspace that *is* the repository, or that has the repository inside it,
    would exclude every file and leave an empty atlas — which is a worse answer than
    indexing the tool's own state, and not the question the caller asked.
    """

    return tuple(
        excluded
        for excluded in excluded_roots
        if excluded != root and excluded.is_relative_to(root)
    )


def lies_within(path: Path, roots: tuple[Path, ...]) -> bool:
    """Whether a file sits under one of these subtrees, symlinked parents included.

    Resolved rather than compared as written, so a subtree reached through a symlinked
    parent is still recognised. Only reached when something is excluded, because it costs a
    syscall per file.
    """

    if not roots:
        return False
    canonical = path.resolve()
    return any(canonical.is_relative_to(root) for root in roots)


def lexical_nodes(syntax: ast.AST) -> Iterable[ast.AST]:
    """Walk one lexical body while treating nested definitions as opaque."""

    boundaries = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    if isinstance(syntax, (ast.Module, *boundaries)):
        stack: list[ast.AST] = list(reversed(syntax.body))
    else:
        stack = list(reversed(list(ast.iter_child_nodes(syntax))))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, boundaries):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


def ast_for_node(module: ParsedModule | None, node: AtlasNode) -> ast.AST | None:
    """The syntax an Atlas node was derived from, when it is still resolvable."""

    if module is None:
        return None
    if node.atlas_id == module.node.atlas_id:
        return module.tree
    for item in ast.walk(module.tree):
        if not isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if item.lineno == node.start_line and item.name == node.symbol_name:
            return item
    return None


def build_edge(
    source: str | None,
    target: str,
    kind: EdgeType,
    *,
    confidence: float = 1.0,
    path: str | None = None,
    line: int | None = None,
    resolved_by: Literal["parse", "types"] = "parse",
    conformance: Literal["strict", "structural"] | None = None,
) -> AtlasEdge:
    if source is None:
        raise ValueError("Atlas edge source cannot be absent")
    location = (
        SourceLocation(path=path, start_line=line, end_line=line)
        if path is not None and line is not None
        else None
    )
    # Provenance is deliberately outside the identity. The two passes that can produce a
    # structural `IMPLEMENTS` edge never both run, so an edge at one site is one edge, and
    # keying on the pass would make an atlas rebuilt with the extra installed look like it
    # had gained edges it had merely re-derived.
    return AtlasEdge(
        edge_id=stable_id("edge", source, target, kind, path or "", str(line or 0)),
        source_id=source,
        target_id=target,
        edge_type=kind,
        confidence=confidence,
        location=location,
        resolved_by=resolved_by,
        conformance=conformance,
    )
