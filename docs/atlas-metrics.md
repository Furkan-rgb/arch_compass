# Atlas metric definitions

Metrics are objective structural dimensions and proxies. ArchCompass does not calculate a
universal complexity or maintainability score. Cognitive load and obscurity cannot be measured
directly; only explicit proxies and signals are reported.

## Local structural metrics

- Physical lines: inclusive `end_line - start_line + 1` source span.
- Logical statements: count of descendant `ast.stmt` nodes.
- Branch count: count of `if`, loop, `try`, exception handler, `match`, and match-case nodes.
- Maximum nesting depth: deepest nested control construct (`if`, loop, `try`, context manager,
  or match).
- Parameters: positional-only, positional, keyword-only, variadic positional, and variadic
  keyword parameters.
- Public symbols: direct classes and callables whose names do not begin with `_`.
- Imported modules: distinct imported names in the node's AST subtree.
- Outgoing static calls: distinct resolved call targets.
- Incoming known callers: distinct resolved callers.

## Dependency metrics

Module dependency graphs use resolved internal import edges. A symbol inherits the metrics of its
owning module where a module-level graph is required.

- Fan-in/fan-out: direct dependant/dependency module counts.
- Direct dependencies/dependants: stable module node IDs.
- Forward/reverse reach: distinct transitively reachable modules, excluding self.
- Dependency depth: maximum reachable edge depth, bounded by graph size.
- SCC membership: content-derived component ID for components with more than one module.
- Cycle size: modules in that SCC, or zero.
- Interface implementations: direct `implements` sources.
- Public-interface callers: resolved direct callers when the node is public.
- Directly associated tests: distinct test modules with a `tests` edge.
- Transitively affected tests: test modules in the reverse dependency neighbourhood.

## Change-amplification proxies

- Likely affected modules: reverse dependency reach.
- Public interfaces crossed: public modules in the reverse neighbourhood.
- Coordinated implementations: implementations of the selected interface.
- Configuration locations: direct resolved configuration relationships.
- Reverse-neighbourhood tests: test modules reached in reverse.

## Cognitive-scope proxies

- Dependency-neighbourhood modules: union of forward and reverse reachable modules.
- Symbols in a representative path: bounded proxy based on reachable dependency steps.
- Abstraction boundaries: outgoing dependencies on interface nodes.
- Related configuration locations: resolved configuration owners.
- Local control-flow complexity: branch count.
- Public API surface: direct public-symbol count.

## Obscurity signals

V1 records wildcard imports, dynamic imports, module mutable state, public callables without
docstrings, similarly named constants, parse failures, unresolved calls, and cyclic dependencies
when evidenced. Signals are prompts for interpretation, not automatic design violations.

