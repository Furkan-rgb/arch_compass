"""Type-aware edge resolution backed by mypy, asked as a library.

The only module in this project that imports mypy, and the only place its internal APIs
are named. mypy ships as an optional extra, so importing this module at all is what tells
the composition root whether typed edges are available (`bootstrap`); everything above it
depends on `EdgeResolver` and never learns which backend answered.

Nothing mypy emits as a diagnostic is read. It is asked two questions — does this class
satisfy that abstraction, where does this reference land — and its error output, rule names
and exit status are all discarded. An edge oracle, not a linter.

The version pin carries the risk. `is_subtype` is the stable internal; `find_member` is the
churn-prone one; the mypyc-compiled wheel hides node attributes behind native slots, so the
expression walk below reads them reflectively rather than subclassing `TraverserVisitor`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import cast

from mypy import build, subtypes
from mypy.errors import CompileError
from mypy.modulefinder import BuildSource
from mypy.nodes import (
    ARG_NAMED,
    ARG_POS,
    Decorator,
    Expression,
    FuncBase,
    IndexExpr,
    MemberExpr,
    NameExpr,
    Node,
    OverloadedFuncDef,
    TypeInfo,
)
from mypy.options import Options
from mypy.types import (
    AnyType,
    CallableType,
    Instance,
    Type,
    TypeOfAny,
    get_proper_type,
)
from mypy.version import __version__ as MYPY_VERSION

from archcompass.analysis.adapters.ast_support import (
    canonical_roots,
    excluded_within,
    import_roots,
    lies_within,
    module_name,
)
from archcompass.analysis.ports import (
    ConformanceQuestion,
    ConformanceVerdict,
    EdgeResolutionRequest,
    EdgeResolutionResult,
    ReferenceQuestion,
    ResolvedReference,
)
from archcompass.analysis.scope import IGNORED_DIRECTORIES

#: Bumped whenever the relaxed rule below decides differently. It is folded into the
#: analysis config hash beside mypy's own version, because a change to either changes the
#: edge set and a stored atlas built under the old one is then a different atlas.
CONFORMANCE_RULE_VERSION = "conformance-rule-v1"

#: Directories that are never part of the repository under review. Mirrors the analyzer's
#: own list; a resolver that fed mypy a vendored `.venv` would spend minutes on code the
#: atlas has no nodes for.

#: Attributes that lead away from the expression tree rather than through it. `node` and
#: `info` point at definitions the walk would otherwise re-enter through every reference,
#: turning a file's walk into a walk of the whole build.
_NON_TREE_ATTRIBUTES = frozenset({"node", "info", "def_var", "fullname", "type", "items"})

_child_attributes: dict[type[Node], tuple[str, ...]] = {}


class MypyEdgeResolver:
    """Answers a whole repository's worth of edge questions from one mypy build.

    Non-incremental every time: a warm cache exports no types and loads no trees, so the
    incremental mode returns an empty view rather than a fast one. The content-fingerprint
    cache above this is the only cache.
    """

    def __init__(self, excluded_roots: tuple[Path, ...] = ()) -> None:
        #: The same subtrees the analyzer leaves out of its snapshot — an ArchCompass
        #: workspace inside the analysed repository, above all. Fed to mypy they would be
        #: type-checked at cost for code the atlas has no nodes for, and a stray module there
        #: could collide with a real one on its dotted name.
        self._excluded_roots = canonical_roots(excluded_roots)

    def fingerprint(self) -> Mapping[str, str]:
        # No excluded roots: they say where this machine keeps its workspace, and the
        # fingerprint is folded into the analysis config hash, which has to name the same
        # analysis on every machine.
        return {
            "backend": "mypy",
            "backend_version": MYPY_VERSION,
            "conformance_rule": CONFORMANCE_RULE_VERSION,
        }

    def resolve(
        self,
        root: Path,
        request: EdgeResolutionRequest,
        *,
        excluded_paths: tuple[str, ...] = (),
    ) -> EdgeResolutionResult:
        if request.is_empty():
            return EdgeResolutionResult()
        try:
            view = _RepositoryTypes.build(root, self._excluded_roots, excluded_paths)
        # `CompileError` is what mypy raises when it cannot get through the code. The rest
        # are what it raises when it cannot get through *itself*: the semantic analyser
        # recurses, and its internal invariants are assertions, so a pathological input
        # surfaces as a `RecursionError`, a `MemoryError` or an `AssertionError` rather than
        # as a diagnostic. That matters more here than it looks, because the file list this
        # resolver is given is not the whole of what mypy will read — a `.pyi` stub beside
        # the code is followed whatever `follow_imports` says, and stubs are not in the
        # snapshot at all. Any of these means the same thing to this layer: no typed edges.
        # The parse already produced an atlas, and indexing must not depend on mypy
        # surviving whatever it was pointed at.
        except (CompileError, RecursionError, MemoryError, AssertionError):
            # `answered=False`, not an empty answer. The caller falls back to the structural
            # heuristic on this, and cannot without being told: an empty result is also what
            # a repository with nothing to report looks like.
            return EdgeResolutionResult(answered=False)
        return EdgeResolutionResult(
            conformances=tuple(
                verdict
                for question in request.conformances
                if (verdict := view.conformance(question)) is not None
            ),
            references=tuple(
                resolved
                for question in request.references
                if (resolved := view.reference(question)) is not None
            ),
        )


class _RepositoryTypes:
    """One mypy build of one repository, and the two questions asked of it."""

    def __init__(self, result: build.BuildResult, modules: Mapping[str, str]) -> None:
        self._types = result.types
        self._files = result.files
        #: Relative path -> dotted module name, using the analyzer's own derivation, so a
        #: mypy fullname is directly comparable with an atlas node's qualified name.
        self._modules = modules
        self._expressions: dict[str, dict[tuple[int, str], Expression]] = {}

    @classmethod
    def build(
        cls,
        root: Path,
        excluded_roots: tuple[Path, ...] = (),
        excluded_paths: tuple[str, ...] = (),
    ) -> _RepositoryTypes:
        excluded = excluded_within(root, excluded_roots)
        # The review's own scope, which this used to walk straight past. It builds its module
        # list from the file system rather than from the snapshot, so a folder the reader
        # left out was still type-checked — and `examples/` holding two vendored repositories
        # that each have a top-level `main.py` is a `CompileError` about duplicate modules,
        # raised over files the atlas does not contain and nobody asked about.
        left_out = tuple(f"{item.strip('/')}/" for item in excluded_paths if item.strip("/"))
        relative = [
            candidate
            for path in sorted(root.rglob("*.py"))
            if not any(part in IGNORED_DIRECTORIES for part in path.relative_to(root).parts)
            and not path.is_symlink()
            and path.is_file()
            and not lies_within(path, excluded)
            and not (candidate := path.relative_to(root).as_posix()).startswith(left_out)
        ]
        # The same import roots the analyzer derives, from the same rule. A resolver that
        # named `src/archcompass/x.py` differently from the atlas would answer every
        # question about a src-layout repository with names nothing could be matched to.
        roots = import_roots(relative)
        modules = {path: module_name(path, roots) for path in relative}
        sources = [
            # The dotted name is explicit because mypy otherwise infers it from the file
            # system and calls every root-level script `__main__`, which aborts the build
            # with a duplicate-module error before a single type is exported.
            BuildSource(str(root / relative), module, None)
            for relative, module in modules.items()
        ]
        options = Options()
        options.export_types = True
        # Required alongside `export_types`: the exported map is keyed by expression nodes,
        # and without the trees preserved those nodes are discarded as each file finishes.
        options.preserve_asts = True
        options.incremental = False
        # Third-party imports are left unfollowed. Every file of the repository is passed
        # explicitly, so `skip` only reaches its dependencies — and following them costs an
        # order of magnitude (10s against 0.9s on this project) to type code the atlas has
        # no nodes for and can therefore never draw an edge to.
        options.follow_imports = "skip"
        options.ignore_missing_imports = True
        options.mypy_path = [str(root)]
        options.python_version = (3, 12)
        options.show_traceback = True
        return cls(build.build(sources=sources, options=options), modules)

    def conformance(self, question: ConformanceQuestion) -> ConformanceVerdict | None:
        implementation = self._type_info(question.class_path, question.class_qualified_name)
        abstraction = self._type_info(
            question.abstraction_path, question.abstraction_qualified_name
        )
        if implementation is None or abstraction is None or implementation is abstraction:
            return None
        if _is_opaque(implementation) or _is_opaque(abstraction):
            return None
        required = _required_members(abstraction)
        # A protocol with no members is satisfied by everything — `int` included. Judging
        # one would wire every class in the repository to it, so it is never judged.
        if not required:
            return None
        candidate = _instance(implementation)
        target = _instance(abstraction)
        if subtypes.is_subtype(candidate, target):
            return ConformanceVerdict(question=question, rule="strict")
        if _satisfies_structurally(candidate, target, required):
            return ConformanceVerdict(question=question, rule="structural")
        return None

    def reference(self, question: ReferenceQuestion) -> ResolvedReference | None:
        expression = self._expressions_in(question.path).get(
            (question.line, question.expression)
        )
        if expression is None:
            return None
        target = self._definition_of(expression)
        if target is None:
            return None
        return ResolvedReference(question=question, target_qualified_name=target)

    def _definition_of(self, expression: Expression) -> str | None:
        if isinstance(expression, NameExpr):
            return expression.node.fullname if expression.node is not None else None
        if not isinstance(expression, MemberExpr):
            return None
        # A module-level reference carries its definition on the node itself; an attribute
        # of a value does not, and has to be looked up on the inferred type of the base.
        if expression.node is not None:
            return expression.node.fullname
        base = get_proper_type(self._types.get(expression.expr))
        if not isinstance(base, Instance):
            return None
        symbol = base.type.get(expression.name)
        return symbol.node.fullname if symbol is not None and symbol.node is not None else None

    def _expressions_in(self, relative_path: str) -> dict[tuple[int, str], Expression]:
        """Every named reference in one file, indexed by line and written spelling.

        Built on demand and once per file. The first spelling on a line wins: two identical
        spellings on one line refer to the same definition, and the caller asked about the
        spelling rather than about a column.
        """

        cached = self._expressions.get(relative_path)
        if cached is not None:
            return cached
        index: dict[tuple[int, str], Expression] = {}
        module = self._modules.get(relative_path)
        tree = self._files.get(module) if module is not None else None
        if tree is not None:
            for expression in _walk_expressions(tree):
                spelling = _spelling(expression)
                if spelling:
                    index.setdefault((expression.line, spelling), expression)
        self._expressions[relative_path] = index
        return index

    def _type_info(self, relative_path: str, qualified_name: str) -> TypeInfo | None:
        module = self._modules.get(relative_path)
        tree = self._files.get(module) if module is not None else None
        if module is None or tree is None:
            return None
        local = qualified_name.removeprefix(f"{module}.")
        if local == qualified_name:
            return None
        symbol = tree.names.get(local.split(".")[0])
        for part in local.split(".")[1:]:
            if symbol is None or not isinstance(symbol.node, TypeInfo):
                return None
            symbol = symbol.node.names.get(part)
        if symbol is None or not isinstance(symbol.node, TypeInfo):
            return None
        # A name imported into this module resolves to a `TypeInfo` defined elsewhere. Only
        # the class written here answers for this question's identity.
        return symbol.node if symbol.node.module_name == module else None


def _is_opaque(info: TypeInfo) -> bool:
    """Whether this class inherits from something the build did not follow.

    Third-party imports are left unfollowed for cost, so a base class from one of them is
    `Any` — and a class with an `Any` anywhere in its ancestry answers *yes* to every
    member the checker is asked about. Left in the sweep, that is not a near miss but a
    catastrophe: on this repository it turned 38 correct conformance pairs into 10 176,
    because every pydantic model in it satisfies every protocol in it.

    Skipped rather than guessed at. A class whose base is invisible cannot be judged, and
    the honest answer to a question that cannot be asked is no answer.
    """

    return any(base.fallback_to_any for base in info.mro)


def _required_members(abstraction: TypeInfo) -> tuple[str, ...]:
    """The operations a class has to supply to count as implementing this abstraction.

    A `Protocol` states its own set. An abstract base does not, so its public methods stand
    in — the same population the untyped heuristic reads, which keeps the typed sweep a
    strictly better answer to the same question rather than a narrower one.
    """

    if abstraction.is_protocol:
        return tuple(sorted(abstraction.protocol_members))
    return tuple(
        sorted(
            name
            for name, symbol in abstraction.names.items()
            if not name.startswith("_")
            and isinstance(symbol.node, (FuncBase, Decorator, OverloadedFuncDef))
        )
    )


def _instance(info: TypeInfo) -> Instance:
    """The class as a type, with its own type variables erased.

    Erased rather than solved: the question is whether the class shape satisfies the
    abstraction's shape, and pinning a type variable to a particular argument would answer
    a narrower question than the atlas is asking.
    """

    return Instance(info, [AnyType(TypeOfAny.special_form)] * len(info.defn.type_vars))


def _satisfies_structurally(
    candidate: Instance, target: Instance, required: Sequence[str]
) -> bool:
    """The relaxed rule: members present, return types checked, parameters by arity.

    Strict subtyping rejects the ordinary adapter idiom of narrowing a parameter — an
    implementation typed `voice: QwenVoice` against a port typed `voice: Voice` is
    contravariance-unsafe and mypy says so, correctly. That is a fact about the adapter,
    not evidence that it is not the port's implementation, and the atlas exists to record
    which classes stand behind which boundary.

    Return types are still checked with the backend's own `is_subtype`, so a method that
    hands back the wrong thing is not credited. Parameters are compared by count only:
    equal required arity, and at least as many total, so an implementation may add optional
    parameters but never drop one the port promises.
    """

    for name in required:
        wanted = subtypes.find_member(name, target, target)
        supplied = subtypes.find_member(name, candidate, candidate)
        if wanted is None or supplied is None:
            return False
        wanted_signature = _signature(wanted)
        supplied_signature = _signature(supplied)
        if wanted_signature is None or supplied_signature is None:
            # An attribute rather than a method on either side: compared as a type, since
            # there is no arity to relax.
            if wanted_signature is not None or supplied_signature is not None:
                return False
            if not subtypes.is_subtype(supplied, wanted):
                return False
            continue
        wanted_required, wanted_total, wanted_return = wanted_signature
        supplied_required, supplied_total, supplied_return = supplied_signature
        if supplied_required != wanted_required or supplied_total < wanted_total:
            return False
        if not subtypes.is_subtype(supplied_return, wanted_return):
            return False
    return True


def _signature(member: Type) -> tuple[int, int, Type] | None:
    """Required arity, total arity and return type, or nothing when this is not callable."""

    proper = get_proper_type(member)
    if not isinstance(proper, CallableType):
        return None
    required = sum(1 for kind in proper.arg_kinds if kind in (ARG_POS, ARG_NAMED))
    return required, len(proper.arg_types), proper.ret_type


def _walk_expressions(root: Node) -> Iterator[Expression]:
    """Every expression under one file's tree, found by reading node attributes.

    Reflective because the wheel is mypyc-compiled: `TraverserVisitor` cannot be relied on
    to dispatch to an override, and the compiled node classes expose their fields through
    `dir` rather than through `__dict__` or `__slots__`.
    """

    seen: set[int] = set()
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, Expression):
            yield node
        stack.extend(_children(node))


def _children(node: Node) -> list[Node]:
    attributes = _child_attributes.get(type(node))
    if attributes is None:
        attributes = tuple(
            name
            for name in dir(type(node))
            if not name.startswith("_")
            and name not in _NON_TREE_ATTRIBUTES
            and not callable(getattr(type(node), name, None))
        )
        _child_attributes[type(node)] = attributes
    found: list[Node] = []
    for name in attributes:
        value: object = getattr(node, name, None)
        if isinstance(value, Node):
            found.append(value)
        elif isinstance(value, (list, tuple)):
            found.extend(item for item in cast("Sequence[object]", value) if isinstance(item, Node))
    return found


def _spelling(expression: Expression) -> str:
    """The dotted name an expression is written as, matching the analyzer's own reading.

    `Repository[Book]` is `Repository`, for the same reason the AST side reads a subscript
    through to its base: the question was asked about the name, not about its arguments.
    """

    if isinstance(expression, NameExpr):
        return expression.name
    if isinstance(expression, MemberExpr):
        base = _spelling(expression.expr)
        return f"{base}.{expression.name}" if base else ""
    if isinstance(expression, IndexExpr):
        return _spelling(expression.base)
    return ""
