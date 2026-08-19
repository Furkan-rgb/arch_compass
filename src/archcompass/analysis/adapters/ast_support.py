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
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from archcompass.analysis.atlas import AtlasEdge, AtlasNode, EdgeType, SourceLocation
from archcompass.records import stable_id


@dataclass
class ParsedModule:
    """One parsed source file and the Atlas identities derived from it."""

    path: Path
    relative_path: str
    qualified_name: str
    node: AtlasNode
    #: The parsed syntax, or `None` once it has been released. Released deliberately: a
    #: repository's worth of trees is ten to twenty times its source in memory, and almost
    #: everything that reads one is finished with it the moment its file has been turned
    #: into nodes. What still wants syntax afterwards asks `TreeSource`, which parses the
    #: file again and keeps a handful at a time.
    tree: ast.Module | None
    source: str
    symbols: dict[str, AtlasNode] = field(default_factory=dict[str, AtlasNode])
    import_aliases: dict[str, str] = field(default_factory=dict[str, str])

    def syntax(self) -> ast.Module:
        """The tree, for a caller that runs while it is still there.

        Everything reached from the parse loop is such a caller: the file has just been read
        and nothing has released it yet. Anything running after that loop asks `TreeSource`
        instead, which will parse the file again. Raising rather than returning `None` keeps
        those two worlds apart — a reader that gets here after the release is a bug in the
        order of the analysis, not a module that happens to have no syntax.
        """

        if self.tree is None:
            raise RuntimeError(
                f"The syntax of {self.relative_path} was released. Read it through "
                "TreeSource, which parses the file again."
            )
        return self.tree


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


class DefinitionIndex:
    """Every definition in a module, found by where it starts and what it is called.

    The same answer `ast_for_node` gives, asked once per module instead of once per node.
    That function walks the whole tree on every call, and it is called for each node in the
    file — so a module with two hundred symbols walked its own tree two hundred times, and
    the cost of a repository was the number of its symbols times the size of its trees.

    First match in `ast.walk` order wins, exactly as the linear scan did: two definitions can
    share a line and a name — a decorated function inside a conditional, most often — and
    which one was returned is behaviour, not an accident to be tidied up.

    Keyed by `id(module)`, which is only sound because an instance of this class lives inside
    one call and every `ParsedModule` it sees is held alive for that whole call by the
    caller's own map. An index promoted to instance or module scope would outlive the modules
    it cached, and CPython would hand a recycled id to a different object: not a crash, but a
    wrong answer, silently. Build one per analysis and let it go with the analysis.
    """

    def __init__(self) -> None:
        self._by_module: dict[int, dict[tuple[int | None, str], ast.AST]] = {}

    def get(self, module: ParsedModule | None, node: AtlasNode) -> ast.AST | None:
        if module is None or module.tree is None:
            return None
        if node.atlas_id == module.node.atlas_id:
            return module.tree
        return self._definitions(module).get((node.start_line, node.symbol_name))

    def _definitions(self, module: ParsedModule) -> dict[tuple[int | None, str], ast.AST]:
        cached = self._by_module.get(id(module))
        if cached is not None:
            return cached
        found: dict[tuple[int | None, str], ast.AST] = {}
        for item in ast.walk(module.tree or ast.Module(body=[], type_ignores=[])):
            if not isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            found.setdefault((item.lineno, item.name), item)
        self._by_module[id(module)] = found
        return found


class TreeSource:
    """Syntax for a module whose tree was released, parsed again and not kept for long.

    The comparisons that outlive a file — a protocol's method against a candidate's, one
    implementation's shape against another's — are the only readers left that need syntax
    after the parse loop, and they need two files at a time rather than all of them. So the
    trees go, and this brings back the few that are asked for.

    Parsing a file again costs milliseconds and the analysis is no longer short of time; a
    repository's worth of retained trees costs hundreds of megabytes and the container is
    short of those. `limit` is what bounds the trade: small enough that the cache is not the
    thing it replaced, large enough that a pairwise comparison never evicts its own operand.
    """

    def __init__(self, modules: list[ParsedModule], *, limit: int = 8) -> None:
        self._by_path = {module.relative_path: module for module in modules}
        self._limit = limit
        self._live: OrderedDict[str, ParsedModule] = OrderedDict()

    def for_path(self, relative_path: str | None) -> ParsedModule | None:
        if relative_path is None:
            return None
        module = self._by_path.get(relative_path)
        if module is None:
            return None
        if module.tree is None:
            # The same refusals the first parse made, made again. A file that would not
            # parse then will not parse now, and a caller asking for one must get the
            # absence rather than an exception thrown from somewhere it cannot expect —
            # the first parse reports an unreadable module as a signal and carries on,
            # and a second parse that killed the analysis instead would undo that.
            try:
                module.tree = ast.parse(
                    module.path.read_bytes().decode("utf-8", errors="replace"),
                    filename=module.relative_path,
                    type_comments=True,
                )
            except (SyntaxError, RecursionError, MemoryError, OSError):
                return None
        self._live[relative_path] = module
        self._live.move_to_end(relative_path)
        while len(self._live) > self._limit:
            _, evicted = self._live.popitem(last=False)
            evicted.tree = None
        return module


def ast_for_node(module: ParsedModule | None, node: AtlasNode) -> ast.AST | None:
    """The syntax an Atlas node was derived from, when it is still resolvable."""

    if module is None or module.tree is None:
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
