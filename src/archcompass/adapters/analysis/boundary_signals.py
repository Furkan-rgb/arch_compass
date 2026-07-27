"""Structural boundary-preparation detection.

These two obscurity signals are the analyzer's only interpretive output: everything
else it emits is a direct measurement of the syntax tree, while these describe a shape
that *may* indicate a port implementation absorbing evidence-selection work. They carry
their own fingerprinting, projection analysis and structural Protocol matching, which
together is more code than the rest of the analyzer's signal handling combined.

Keeping them here leaves the analyzer core to parsing, graph construction and metrics,
and makes the boundary heuristics reviewable as one subject. They remain structural
proxies: `docs/repository-atlas.md` and `docs/atlas-metrics.md` state their limits.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from archcompass.adapters.analysis.ast_support import (
    ParsedModule,
    ast_for_node,
    build_edge,
    lexical_nodes,
)
from archcompass.domain.atlas import (
    AtlasEdge,
    AtlasNode,
    EdgeType,
    MetricNature,
    NodeType,
    ObscuritySignal,
    SourceLocation,
)


@dataclass(frozen=True)
class _BoundaryPreparationFingerprint:
    """Static features used to locate broad input-to-request preparation."""

    input_paths: frozenset[str]
    mapping_keys: frozenset[str]


@dataclass(frozen=True)
class _BoundaryProjection:
    """One located request projection fed by one broad input substructure."""

    input_root: str
    deep_paths: frozenset[str]
    static_keys: frozenset[str]
    input_derived_keys: frozenset[str]
    line: int


def parallel_boundary_preparation_signals(nodes: dict[str, AtlasNode],
    edges: list[AtlasEdge],
    modules: list[ParsedModule],
) -> list[ObscuritySignal]:
    """Surface repeated preparation in sibling implementations as a bounded proxy.

    The atlas cannot establish semantic ownership. It can, however, observe that
    implementations of the same resolved port operation repeatedly read the same
    paths from a broad input and construct similarly keyed request data. That
    makes the relevant methods discoverable for a later evidence-grounded
    consultation.
    """

    parsed_by_path = {module.relative_path: module for module in modules}
    children_by_parent: defaultdict[str, list[AtlasNode]] = defaultdict(list)
    for node in nodes.values():
        if node.parent_id is not None:
            children_by_parent[node.parent_id].append(node)

    implementations_by_port: defaultdict[str, list[AtlasNode]] = defaultdict(list)
    for edge in edges:
        if edge.edge_type != EdgeType.IMPLEMENTS:
            continue
        implementation = nodes.get(edge.source_id)
        port = nodes.get(edge.target_id)
        if (
            implementation is not None
            and port is not None
            and port.node_type == NodeType.INTERFACE
        ):
            implementations_by_port[port.atlas_id].append(implementation)

    matches: defaultdict[
        str,
        list[tuple[AtlasNode, AtlasNode, frozenset[str], frozenset[str]]],
    ] = defaultdict(list)
    for port_id, implementation_classes in implementations_by_port.items():
        if len(implementation_classes) < 2:
            continue
        port = nodes[port_id]
        port_operations = {
            child.symbol_name
            for child in children_by_parent[port_id]
            if child.node_type == NodeType.METHOD
        }
        for operation in sorted(port_operations):
            methods = [
                child
                for implementation in implementation_classes
                for child in children_by_parent[implementation.atlas_id]
                if child.node_type == NodeType.METHOD
                and child.symbol_name == operation
            ]
            fingerprints = {
                method.atlas_id: _boundary_preparation_fingerprint(
                    method,
                    parsed_by_path.get(method.path),
                )
                for method in methods
            }
            for first, second in combinations(methods, 2):
                first_fingerprint = fingerprints[first.atlas_id]
                second_fingerprint = fingerprints[second.atlas_id]
                shared_paths = (
                    first_fingerprint.input_paths & second_fingerprint.input_paths
                )
                shared_keys = (
                    first_fingerprint.mapping_keys & second_fingerprint.mapping_keys
                )
                if not _is_parallel_preparation_match(
                    first_fingerprint,
                    second_fingerprint,
                    shared_paths=shared_paths,
                    shared_keys=shared_keys,
                ):
                    continue
                matches[first.atlas_id].append(
                    (port, second, shared_paths, shared_keys)
                )
                matches[second.atlas_id].append(
                    (port, first, shared_paths, shared_keys)
                )

    result: list[ObscuritySignal] = []
    for method_id, peers in sorted(matches.items()):
        method = nodes[method_id]
        port = peers[0][0]
        peer_names = sorted({peer.qualified_name for _, peer, _, _ in peers})
        observed_paths: set[str] = set()
        observed_keys: set[str] = set()
        for _, _, peer_paths, peer_keys in peers:
            observed_paths.update(peer_paths)
            observed_keys.update(peer_keys)
        path_sample = ", ".join(sorted(observed_paths)[:4])
        key_sample = ", ".join(sorted(observed_keys)[:4])
        observations = [
            f"{len(observed_paths)} shared input paths"
            + (f" ({path_sample})" if path_sample else ""),
            f"{len(observed_keys)} shared mapping keys"
            + (f" ({key_sample})" if key_sample else ""),
        ]
        result.append(
            ObscuritySignal(
                code="parallel-boundary-preparation",
                message=(
                    f"{method.qualified_name} and {', '.join(peer_names)} implement or "
                    f"structurally match {port.qualified_name}.{method.symbol_name} with "
                    f"overlapping "
                    f"input-to-request preparation: {'; '.join(observations)}."
                ),
                node_id=method.atlas_id,
                location=(
                    SourceLocation(
                        path=method.path,
                        start_line=method.start_line,
                        end_line=method.end_line,
                    )
                    if method.start_line is not None
                    and method.end_line is not None
                    else None
                ),
                nature=MetricNature.STRUCTURAL_PROXY,
                definition=(
                    "Sibling implementations of one resolved or conservatively "
                    "structurally matched Protocol operation read overlapping "
                    "parameter-relative paths while constructing request-shaped data."
                ),
                limitations=(
                    "Static overlap does not prove semantic equivalence, provider-neutral "
                    "meaning, duplicated behavior, or misplaced ownership. Structural "
                    "Protocol matching is based on the complete method set and compatible "
                    "type annotations, not runtime dispatch. Inspect the port contract and "
                    "method excerpts before recommending a move."
                ),
            )
        )
    return result

def broad_input_boundary_preparation_signals(nodes: dict[str, AtlasNode],
    edges: list[AtlasEdge],
    modules: list[ParsedModule],
) -> list[ObscuritySignal]:
    """Locate one port implementation that prepares requests from a broad input.

    This is deliberately independent of sibling implementations. It records the
    present structural fact that one boundary method reads several nested paths
    from the same input substructure while also constructing keyed request data.
    Whether those reads are legitimate translation or misplaced responsibility
    remains a consultation question.
    """

    parsed_by_path = {module.relative_path: module for module in modules}
    children_by_parent: defaultdict[str, list[AtlasNode]] = defaultdict(list)
    for node in nodes.values():
        if node.parent_id is not None:
            children_by_parent[node.parent_id].append(node)

    result: list[ObscuritySignal] = []
    inspected_methods: set[str] = set()
    for edge in sorted(edges, key=lambda item: item.edge_id):
        if edge.edge_type != EdgeType.IMPLEMENTS:
            continue
        implementation = nodes.get(edge.source_id)
        port = nodes.get(edge.target_id)
        if (
            implementation is None
            or port is None
            or port.node_type != NodeType.INTERFACE
        ):
            continue
        port_operations = {
            child.symbol_name
            for child in children_by_parent[port.atlas_id]
            if child.node_type == NodeType.METHOD
        }
        for method in children_by_parent[implementation.atlas_id]:
            if (
                method.node_type != NodeType.METHOD
                or method.symbol_name not in port_operations
                or method.atlas_id in inspected_methods
            ):
                continue
            inspected_methods.add(method.atlas_id)
            projections = _boundary_projections(
                method,
                parsed_by_path.get(method.path),
            )
            if not projections:
                continue
            projection = max(
                projections,
                key=lambda item: (
                    len(item.deep_paths),
                    len(item.input_derived_keys),
                    len(item.static_keys),
                    -item.line,
                ),
            )
            path_sample = ", ".join(sorted(projection.deep_paths)[:4])
            key_sample = ", ".join(sorted(projection.static_keys)[:4])
            result.append(
                ObscuritySignal(
                    code="broad-input-boundary-preparation",
                    message=(
                        f"{method.qualified_name} implements or structurally matches "
                        f"{port.qualified_name}.{method.symbol_name}, reads "
                        f"{len(projection.deep_paths)} nested input paths under "
                        f"{projection.input_root} ({path_sample}), and projects them into "
                        f"{len(projection.input_derived_keys)} of "
                        f"{len(projection.static_keys)} static fields ({key_sample}) in data "
                        "passed to another call or returned."
                    ),
                    node_id=method.atlas_id,
                    location=SourceLocation(
                        path=method.path,
                        start_line=projection.line,
                        end_line=projection.line,
                    ),
                    nature=MetricNature.STRUCTURAL_PROXY,
                    definition=(
                        "A resolved or conservatively structurally matched port "
                        "implementation reads at least three nested paths from one input "
                        "substructure, feeds them into at least two fields of one "
                        "three-or-more-field projection, and passes that projection to a "
                        "call or return boundary."
                    ),
                    limitations=(
                        "Static data flow does not prove that the fields are semantic "
                        "decisions, that the downstream call is remote transport, or that "
                        "responsibility is misplaced. Persistence mappers, presenters, "
                        "exporters, and deliberate anti-corruption adapters may legitimately "
                        "project broad inputs. Inspect the port contract and located excerpt "
                        "before advising."
                    ),
                )
            )
    return result

def add_structural_protocol_edges(nodes: dict[str, AtlasNode],
    edges: list[AtlasEdge],
    modules: list[ParsedModule],
) -> None:
    """Add conservative Python Protocol conformance edges.

    Python adapters commonly rely on structural typing and therefore do not
    inherit their Protocol. We require the complete operation set, compatible
    arity, and at least two matching annotations across each operation before
    treating a class as a structural implementation.
    """

    parsed_by_path = {module.relative_path: module for module in modules}
    children_by_parent: defaultdict[str, list[AtlasNode]] = defaultdict(list)
    for node in nodes.values():
        if node.parent_id is not None:
            children_by_parent[node.parent_id].append(node)
    existing = {
        (edge.source_id, edge.target_id)
        for edge in edges
        if edge.edge_type == EdgeType.IMPLEMENTS
    }
    interfaces = [
        node for node in nodes.values() if node.node_type == NodeType.INTERFACE
    ]
    classes = [
        node
        for node in nodes.values()
        if node.node_type == NodeType.CLASS
        and not node.path.startswith("tests/")
    ]
    for interface in interfaces:
        operations = [
            child
            for child in children_by_parent[interface.atlas_id]
            if child.node_type == NodeType.METHOD
            and child.is_public
        ]
        if not operations:
            continue
        for candidate in classes:
            if (candidate.atlas_id, interface.atlas_id) in existing:
                continue
            candidate_methods = {
                child.symbol_name: child
                for child in children_by_parent[candidate.atlas_id]
                if child.node_type == NodeType.METHOD
            }
            if not all(operation.symbol_name in candidate_methods for operation in operations):
                continue
            agreements = [
                _structural_method_match(
                    operation,
                    candidate_methods[operation.symbol_name],
                    parsed_by_path,
                )
                for operation in operations
            ]
            if any(agreement is None for agreement in agreements):
                continue
            # Enough evidence that this is not a coincidence, judged over the whole class
            # rather than one method at a time. Two operations matching by name is already
            # unlikely by accident; a lone operation has to earn it with annotations.
            # The same bar applied per-method made any protocol containing a no-argument
            # method — `close()`, `check_available()` — impossible to satisfy at all.
            if len(operations) < 2 and sum(filter(None, agreements)) < 2:
                continue
            edges.append(
                build_edge(
                    candidate.atlas_id,
                    interface.atlas_id,
                    EdgeType.IMPLEMENTS,
                    confidence=0.8,
                    path=candidate.path,
                    line=candidate.start_line,
                )
            )

def _structural_method_match(protocol_method: AtlasNode,
    candidate_method: AtlasNode,
    parsed_by_path: dict[str, ParsedModule],
) -> int | None:
    """How strongly one operation matches, or `None` when the two contradict.

    The count is annotation positions where both sides are annotated and agree — evidence
    the caller weighs across the whole class. Returning it separately from compatibility is
    the point: an operation can be perfectly compatible and carry no evidence at all
    (`close(self) -> None`), and treating those two as one question is what broke this.
    """

    protocol_syntax = ast_for_node(
        parsed_by_path.get(protocol_method.path),
        protocol_method,
    )
    candidate_syntax = ast_for_node(
        parsed_by_path.get(candidate_method.path),
        candidate_method,
    )
    if not isinstance(
        protocol_syntax,
        (ast.FunctionDef, ast.AsyncFunctionDef),
    ) or not isinstance(
        candidate_syntax,
        (ast.FunctionDef, ast.AsyncFunctionDef),
    ):
        return None
    if isinstance(protocol_syntax, ast.AsyncFunctionDef) != isinstance(
        candidate_syntax,
        ast.AsyncFunctionDef,
    ):
        return None
    agreement = _parameter_agreement(protocol_syntax, candidate_syntax)
    if agreement is None:
        return None
    expected_return = _returned_annotation(protocol_syntax)
    actual_return = _returned_annotation(candidate_syntax)
    if not _compatible_annotation(expected_return, actual_return):
        return None
    returns_agree = bool(expected_return) and expected_return == actual_return
    return agreement + int(returns_agree)


#: Names whose meaning is fixed by the language, so two spellings of one really are
#: comparable. Everything else may be an alias, a re-export, or a subtype the parse cannot
#: resolve — and an adapter narrowing a return or widening a parameter is the abstraction
#: working, not evidence it is a different thing.
_COMPARABLE_ANNOTATIONS = frozenset(
    {
        "bool", "bytes", "complex", "dict", "float", "frozenset", "int", "list",
        "None", "set", "str", "tuple",
    }
)


def _compatible_annotation(expected: str, actual: str) -> bool:
    """Whether an adapter's annotation contradicts the protocol's.

    Only a disagreement between two builtins counts. `-> Voice` against
    `-> _QwenVoice | _QwenBuiltinVoice` is a port doing its job: the adapter returns the
    concrete type the abstraction exists to hide. Comparing those as strings rejected every
    correctly written adapter in a real repository, which is the opposite of the intent.
    """

    if not expected or not actual or expected == actual:
        return True
    return not (expected in _COMPARABLE_ANNOTATIONS and actual in _COMPARABLE_ANNOTATIONS)


def _parameter_agreement(
    protocol_syntax: ast.FunctionDef | ast.AsyncFunctionDef,
    candidate_syntax: ast.FunctionDef | ast.AsyncFunctionDef,
) -> int | None:
    """Agreeing annotated parameters, or `None` when the adapter contradicts the protocol.

    The adapter may take *more* than the protocol declares, so long as the surplus all has
    defaults: refining `voices()` into `voices(root: Path | None = None)` still honours
    every call the protocol promises, and demanding identical arity rejected exactly that.
    """

    expected = _declared_parameters(protocol_syntax)
    actual = _declared_parameters(candidate_syntax)
    if len(actual) < len(expected):
        return None
    agreement = 0
    for wanted, given in zip(expected, actual, strict=False):
        wanted_annotation = _annotation(wanted)
        given_annotation = _annotation(given)
        if not _compatible_annotation(wanted_annotation, given_annotation):
            return None
        if wanted_annotation and wanted_annotation == given_annotation:
            agreement += 1
    surplus = actual[len(expected):]
    if not all(_has_default(candidate_syntax, argument) for argument in surplus):
        return None
    return agreement


def _declared_parameters(
    syntax: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.arg]:
    arguments = [
        *syntax.args.posonlyargs,
        *syntax.args.args,
        *syntax.args.kwonlyargs,
    ]
    return [argument for argument in arguments if argument.arg not in {"self", "cls"}]


def _has_default(
    syntax: ast.FunctionDef | ast.AsyncFunctionDef, argument: ast.arg
) -> bool:
    positional = [*syntax.args.posonlyargs, *syntax.args.args]
    if argument in positional:
        offset = len(positional) - len(syntax.args.defaults)
        return positional.index(argument) >= offset
    if argument in syntax.args.kwonlyargs:
        default = syntax.args.kw_defaults[syntax.args.kwonlyargs.index(argument)]
        return default is not None
    return False


def _annotation(argument: ast.arg) -> str:
    return (
        ast.unparse(argument.annotation).replace(" ", "")
        if argument.annotation is not None
        else ""
    )


def _returned_annotation(syntax: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    return ast.unparse(syntax.returns).replace(" ", "") if syntax.returns is not None else ""


def _boundary_preparation_fingerprint(method: AtlasNode,
    parsed: ParsedModule | None,
) -> _BoundaryPreparationFingerprint:
    syntax = ast_for_node(parsed, method)
    if not isinstance(syntax, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return _BoundaryPreparationFingerprint(frozenset(), frozenset())
    parameters = [
        argument.arg
        for argument in [
            *syntax.args.posonlyargs,
            *syntax.args.args,
            *syntax.args.kwonlyargs,
        ]
        if argument.arg not in {"self", "cls"}
    ]
    parameter_names = set(parameters)
    input_paths: set[str] = set()
    mapping_keys: set[str] = set()
    parent_by_node = {
        child: parent
        for parent in ast.walk(syntax)
        for child in ast.iter_child_nodes(parent)
    }
    for item in lexical_nodes(syntax):
        if (
            isinstance(item, ast.Attribute)
            and not isinstance(parent_by_node.get(item), ast.Attribute)
        ) or (
            isinstance(item, ast.Subscript)
            and not isinstance(
                parent_by_node.get(item),
                (ast.Attribute, ast.Subscript),
            )
        ):
            chain = _input_access_chain(item, parameter_names)
            if chain is not None:
                input_paths.add(chain)
        if isinstance(item, ast.Dict):
            mapping_keys.update(
                key.value
                for key in item.keys
                if isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value
            )
        elif isinstance(item, ast.Call):
            mapping_keys.update(
                keyword.arg
                for keyword in item.keywords
                if keyword.arg is not None
            )
    return _BoundaryPreparationFingerprint(
        input_paths=frozenset(input_paths),
        mapping_keys=frozenset(mapping_keys),
    )

def _boundary_projections(method: AtlasNode,
    parsed: ParsedModule | None,
) -> list[_BoundaryProjection]:
    """Find request projections whose fields consume one broad input."""

    syntax = ast_for_node(parsed, method)
    if not isinstance(syntax, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    parameter_names = {
        argument.arg
        for argument in [
            *syntax.args.posonlyargs,
            *syntax.args.args,
            *syntax.args.kwonlyargs,
        ]
        if argument.arg not in {"self", "cls"}
    }
    parent_by_node = {
        child: parent
        for parent in ast.walk(syntax)
        for child in ast.iter_child_nodes(parent)
    }
    body_nodes = list(lexical_nodes(syntax))
    position_by_node = {
        item: position for position, item in enumerate(body_nodes)
    }
    escaping_uses: defaultdict[str, list[int]] = defaultdict(list)
    binding_positions: defaultdict[str, list[int]] = defaultdict(list)
    for position, item in enumerate(body_nodes):
        for name in _bound_names(item):
            binding_positions[name].append(position)
        expressions: list[ast.AST] = []
        if isinstance(item, ast.Call):
            expressions.extend(item.args)
            expressions.extend(keyword.value for keyword in item.keywords)
        elif isinstance(item, ast.Return) and item.value is not None:
            expressions.append(item.value)
        for expression in expressions:
            for child in ast.walk(expression):
                if isinstance(child, ast.Name):
                    escaping_uses[child.id].append(position)

    local_paths: dict[str, frozenset[str]] = {}
    active_parameter_names = set(parameter_names)
    projections: list[_BoundaryProjection] = []
    for item in body_nodes:
        if isinstance(item, ast.Assign):
            value_paths = _expression_input_paths(
                item.value,
                parameter_names=active_parameter_names,
                local_paths=local_paths,
            )
            for target in item.targets:
                names = _assigned_names(target)
                for name in names:
                    active_parameter_names.discard(name)
                    local_paths.pop(name, None)
                if isinstance(target, ast.Name):
                    local_paths[target.id] = value_paths
        elif isinstance(item, ast.AnnAssign) and item.value is not None:
            value_paths = _expression_input_paths(
                item.value,
                parameter_names=active_parameter_names,
                local_paths=local_paths,
            )
            names = _assigned_names(item.target)
            for name in names:
                active_parameter_names.discard(name)
                local_paths.pop(name, None)
            if isinstance(item.target, ast.Name):
                local_paths[item.target.id] = value_paths
        else:
            for name in _bound_names(item):
                active_parameter_names.discard(name)
                local_paths.pop(name, None)

        if isinstance(item, ast.Dict):
            line = getattr(item, "lineno", method.start_line or 1)
            projection_position = position_by_node[item]
            assigned_names = _projection_assignment_names(
                item,
                parent_by_node=parent_by_node,
            )
            escapes = _expression_reaches_call_or_return(
                item,
                parent_by_node=parent_by_node,
            ) or any(
                use_position > projection_position
                and not any(
                    projection_position < binding_position < use_position
                    for binding_position in binding_positions.get(name, [])
                )
                for name in assigned_names
                for use_position in escaping_uses.get(name, [])
            )
            if not escapes:
                continue
            fields = {
                key.value: _expression_input_paths(
                    value,
                    parameter_names=active_parameter_names,
                    local_paths=local_paths,
                )
                for key, value in zip(item.keys, item.values, strict=True)
                if isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value
            }
            projections.extend(
                _qualifying_boundary_projections(
                    fields,
                    line=line,
                )
            )
        elif isinstance(item, ast.Call):
            fields = {
                keyword.arg: _expression_input_paths(
                    keyword.value,
                    parameter_names=active_parameter_names,
                    local_paths=local_paths,
                )
                for keyword in item.keywords
                if keyword.arg is not None
            }
            projections.extend(
                _qualifying_boundary_projections(
                    fields,
                    line=getattr(item, "lineno", method.start_line or 1),
                )
            )

    unique = {
        (
            projection.input_root,
            projection.deep_paths,
            projection.static_keys,
            projection.input_derived_keys,
            projection.line,
        ): projection
        for projection in projections
    }
    return sorted(
        unique.values(),
        key=lambda item: (
            item.line,
            item.input_root,
            sorted(item.static_keys),
        ),
    )

def _expression_input_paths(expression: ast.AST,
    *,
    parameter_names: set[str],
    local_paths: dict[str, frozenset[str]],
) -> frozenset[str]:
    scope_binders = (
        ast.DictComp,
        ast.GeneratorExp,
        ast.Lambda,
        ast.ListComp,
        ast.SetComp,
    )
    if any(isinstance(item, scope_binders) for item in ast.walk(expression)):
        # Conservatively decline data-flow claims across nested expression scopes.
        # Their binders may shadow the enclosing method parameters.
        return frozenset()
    parent_by_node = {
        child: parent
        for parent in ast.walk(expression)
        for child in ast.iter_child_nodes(parent)
    }
    paths: set[str] = set()
    for item in [expression, *lexical_nodes(expression)]:
        if (
            isinstance(item, ast.Attribute)
            and not isinstance(parent_by_node.get(item), ast.Attribute)
        ) or (
            isinstance(item, ast.Subscript)
            and not isinstance(
                parent_by_node.get(item),
                (ast.Attribute, ast.Subscript),
            )
        ):
            chain = _input_access_chain_with_parameter(
                item,
                parameter_names,
            )
            if chain is not None:
                paths.add(chain)
        if isinstance(item, ast.Name) and item.id in local_paths:
            paths.update(local_paths[item.id])
    return frozenset(paths)

def _input_access_chain_with_parameter(
    node: ast.AST,
    parameter_names: set[str],
) -> str | None:
    parts: list[str] = []
    cursor = node
    while isinstance(cursor, (ast.Attribute, ast.Subscript)):
        if isinstance(cursor, ast.Attribute):
            parts.append(cursor.attr)
            cursor = cursor.value
            continue
        slice_node = cursor.slice
        if not (
            isinstance(slice_node, ast.Constant)
            and isinstance(slice_node.value, str)
        ):
            return None
        parts.append(slice_node.value)
        cursor = cursor.value
    if (
        not isinstance(cursor, ast.Name)
        or cursor.id not in parameter_names
        or len(parts) < 2
    ):
        return None
    parts.reverse()
    return ".".join([cursor.id, *parts])

def _assigned_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.List, ast.Tuple)):
        return {
            name
            for element in target.elts
            for name in _assigned_names(element)
        }
    return set()

def _bound_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Assign):
        return {
            name
            for target in node.targets
            for name in _assigned_names(target)
        }
    if isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
        return _assigned_names(node.target)
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return _assigned_names(node.target)
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return {
            name
            for item in node.items
            if item.optional_vars is not None
            for name in _assigned_names(item.optional_vars)
        }
    if isinstance(node, ast.ExceptHandler) and node.name is not None:
        return {node.name}
    return set()

def _projection_assignment_names(expression: ast.AST,
    *,
    parent_by_node: dict[ast.AST, ast.AST],
) -> set[str]:
    parent = parent_by_node.get(expression)
    if isinstance(parent, ast.Assign) and parent.value is expression:
        return {
            name
            for target in parent.targets
            for name in _assigned_names(target)
        }
    if isinstance(parent, ast.AnnAssign) and parent.value is expression:
        return _assigned_names(parent.target)
    return set()

def _expression_reaches_call_or_return(
    expression: ast.AST,
    *,
    parent_by_node: dict[ast.AST, ast.AST],
) -> bool:
    cursor = expression
    while parent := parent_by_node.get(cursor):
        if isinstance(parent, (ast.Call, ast.Return)):
            return True
        if isinstance(parent, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            return False
        if isinstance(parent, (ast.stmt, ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        cursor = parent
    return False

def _qualifying_boundary_projections(
    fields: dict[str, frozenset[str]],
    *,
    line: int,
) -> list[_BoundaryProjection]:
    if len(fields) < 3:
        return []
    paths_by_root: defaultdict[str, set[str]] = defaultdict(set)
    keys_by_root: defaultdict[str, set[str]] = defaultdict(set)
    for key, paths in fields.items():
        for path in paths:
            parts = path.split(".")
            if len(parts) < 3:
                continue
            root = ".".join(parts[:2])
            paths_by_root[root].add(path)
            keys_by_root[root].add(key)
    return [
        _BoundaryProjection(
            input_root=root,
            deep_paths=frozenset(paths),
            static_keys=frozenset(fields),
            input_derived_keys=frozenset(keys_by_root[root]),
            line=line,
        )
        for root, paths in paths_by_root.items()
        if len(paths) >= 3 and len(keys_by_root[root]) >= 2
    ]

def _input_access_chain(
    node: ast.AST,
    parameter_names: set[str],
) -> str | None:
    parts: list[str] = []
    cursor = node
    while isinstance(cursor, (ast.Attribute, ast.Subscript)):
        if isinstance(cursor, ast.Attribute):
            parts.append(cursor.attr)
            cursor = cursor.value
            continue
        slice_node = cursor.slice
        if not (
            isinstance(slice_node, ast.Constant)
            and isinstance(slice_node.value, str)
        ):
            return None
        parts.append(slice_node.value)
        cursor = cursor.value
    if not isinstance(cursor, ast.Name) or cursor.id not in parameter_names:
        return None
    parts.reverse()
    return ".".join(parts) if len(parts) >= 2 else None

def _is_parallel_preparation_match(
    first: _BoundaryPreparationFingerprint,
    second: _BoundaryPreparationFingerprint,
    *,
    shared_paths: frozenset[str],
    shared_keys: frozenset[str],
) -> bool:
    first_features = len(first.input_paths) + len(first.mapping_keys)
    second_features = len(second.input_paths) + len(second.mapping_keys)
    if min(first_features, second_features) < 4:
        return False
    shared_features = len(shared_paths) + len(shared_keys)
    overlap = shared_features / min(first_features, second_features)
    has_broad_shared_input = len(shared_paths) >= 3
    has_input_and_mapping_shape = len(shared_paths) >= 1 and len(shared_keys) >= 3
    return (
        shared_features >= 4
        and overlap >= 0.6
        and (has_broad_shared_input or has_input_and_mapping_shape)
    )
