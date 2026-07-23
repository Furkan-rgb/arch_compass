# RepositoryAtlas

## Construction

The Python analyzer resolves and validates the root, ignores symlinks and common generated or
environment directories, reads candidate files, and parses Python with the built-in `ast` module.
Analysed code is never imported or executed.

Nodes represent repositories, packages, modules, test modules, configuration files/modules,
classes, protocols or abstract interfaces, functions, methods, and test functions. Each carries a
stable ID, repository-relative path, symbol and qualified names, type, source span, parent,
public/private inference, docstring presence, language, and parser version.

Edges represent `contains`, `imports`, `calls`, `inherits`, `implements`, `references`, `tests`,
and `configures`. V1 emits only relationships it can resolve conservatively. Each emitted edge has
confidence and a source location where available. Calls without one resolvable internal target
become `unresolved-call` signals instead of invented edges.

Version identity records the canonical root, repository identity, Git commit when available,
content fingerprint, parser version, and analysis-configuration hash. An explicit rebuild always
creates a new version.

## Query model

Supported queries include repository and subsystem summaries, node details, direct dependencies
and dependants, forward and reverse neighbourhoods, known callers, interface implementations,
related tests, shortest dependency paths, cycles, metric hotspots, token-based node search, and
bounded excerpts.

Progressive zoom is:

```text
repository → subsystem → package → module → symbol → relations/tests/excerpts
```

Query models cap depth, results, terms, context, and excerpt lines. Node IDs are validated against
the selected atlas. Source reads resolve within the canonical root and reject symlinks and
traversal.

## Known limitations

- Python name resolution is incomplete without execution and type inference.
- Dynamic imports, monkey-patching, decorators, descriptors, dependency injection, and reflection
  can hide runtime relationships.
- Method dispatch is resolved only for simple local and imported names.
- Test association is inferred from resolved calls and imports.
- Configuration relationships are conservative.
- Namespace packages and generated code can be interpreted differently from runtime tooling.
- Runtime frequency, latency, production behavior, Git co-change, and whole-program data flow are
  not observed.

Confidence describes static resolution quality; it is not a probability that the architecture is
good.

