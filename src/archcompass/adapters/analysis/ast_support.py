"""Shared AST helpers for Python repository analysis.

The analyzer core and the boundary-preparation detectors both need to walk one
lexical body, find the syntax behind an Atlas node, and mint an edge. Keeping these
here lets the detectors live in their own module without either importing the other.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

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
) -> AtlasEdge:
    if source is None:
        raise ValueError("Atlas edge source cannot be absent")
    location = (
        SourceLocation(path=path, start_line=line, end_line=line)
        if path is not None and line is not None
        else None
    )
    return AtlasEdge(
        edge_id=stable_id("edge", source, target, kind, path or "", str(line or 0)),
        source_id=source,
        target_id=target,
        edge_type=kind,
        confidence=confidence,
        location=location,
    )
