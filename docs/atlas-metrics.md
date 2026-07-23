# Atlas metric definitions

Metrics are objective structural dimensions and proxies. ArchCompass does not calculate a
universal complexity or maintainability score. Cognitive load and obscurity cannot be measured
directly; only explicit proxies and signals are reported.

## Local structural metrics

- Physical lines: inclusive `end_line - start_line + 1` source span.
- Logical statements: count of lexical descendant `ast.stmt` nodes, excluding nested
  class/function bodies.
- Branch count: count of lexical `if`, loop, `try`, exception handler, `match`, and match-case
  nodes, excluding nested class/function bodies.
- Maximum nesting depth: deepest nested control construct (`if`, loop, `try`, context manager,
  or match) within the same lexical scope.
- Parameters: positional-only, positional, keyword-only, variadic positional, and variadic
  keyword parameters.
- Public symbols: direct classes and callables whose names do not begin with `_`.
- Imported modules: distinct imported module names in the node's lexical scope, not aliases.
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
- Transitively affected tests: test modules in the reverse import-and-call impact neighbourhood.

## Change-amplification proxies

- Likely affected modules: distinct owners in the reverse import-and-call impact graph, excluding
  the selected node's owning module.
- Public interfaces crossed: distinct public class/function/interface/method targets of resolved
  calls whose endpoints are in the affected module set.
- Coordinated implementations: implementations of the selected interface.
- Configuration locations: direct resolved configuration relationships.
- Reverse-neighbourhood tests: test modules reached through that reverse impact graph.

## Cognitive-scope proxies

- Dependency-neighbourhood modules: union of forward and reverse reachable modules.
- Symbols in a representative path: node count on a bounded deterministic resolved-call path.
- Abstraction boundaries: transitions into or out of interface ownership along that call path.
- Related configuration locations: resolved configuration owners.
- Local control-flow complexity: branch count.
- Public API surface: direct public-symbol count.

## Obscurity signals

V1 records wildcard imports, dynamic imports, module mutable state, public callables without
docstrings, similarly named constants, parse failures, unresolved calls, and cyclic dependencies
when evidenced. Signals are prompts for interpretation, not automatic design violations.
Cycle signals are emitted from multi-module strongly connected components of the resolved import
graph.
