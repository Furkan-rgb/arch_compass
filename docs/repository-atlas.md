# RepositoryAtlas

## Construction

The Python analyzer resolves and validates the root, ignores symlinks and common generated or
environment directories, and reads every discovered Python/configuration file exactly once into
an in-memory snapshot. The same bytes are used for the content fingerprint and built-in `ast`
parsing, so an atlas never combines an identity from one read with structure from another.
Analysed code is never imported or executed.

Nodes represent repositories, packages, modules, test modules, configuration files/modules,
classes, protocols or abstract interfaces, functions, methods, and test functions. Each carries a
stable ID, repository-relative path, symbol and qualified names, type, source span, parent,
public/private inference, docstring presence, language, and parser version.

Edges represent `contains`, `imports`, `calls`, `inherits`, `implements`, `references`, `tests`,
and `configures`. V1 emits only relationships it can resolve conservatively. Each emitted edge has
confidence and a source location where available. Calls without one resolvable internal target
become `unresolved-call` signals instead of invented edges.

Calls, references, statements, branches, and imports are attributed to their lexical owner.
Walking a module, class, or callable treats nested class/function definitions as opaque, so a
nested callable's behavior is not charged to its parent. Test relationships come from resolved
test calls and internal imports.

Version identity records the canonical root, repository identity, Git commit when available,
content fingerprint, parser version, and analysis-configuration hash. An explicit rebuild always
creates a new immutable version.

## Freshness and workspace safety

Before brownfield advice and application-level atlas queries, ArchCompass recomputes the
repository content fingerprint and Git commit identity. Source excerpts perform the same check
before reading code. A mismatch raises `StaleAtlasError` and instructs the caller to run
`archcompass repo index <repository>`; old versions are usable only while their evidence identity
still matches.

The selected ArchCompass workspace must not equal or be contained by the analysed repository.
Explicit repository arguments are checked before runtime construction, and every atlas root
resolved from a case or persisted version is checked again before use. This prevents SQLite state
or reports from being written into the repository. Indexing, queries, and advice never modify the
analysed repository.

## Query model

Supported queries include repository and subsystem summaries, node details, direct dependencies
and dependants, forward and reverse neighbourhoods, known callers, interface implementations,
related tests, shortest dependency paths, cycles, metric hotspots, token-based node search, and
bounded excerpts.

Every result has typed fields for node summaries, metric values, relationships, test IDs,
signals, and excerpts in addition to its bounded summary and node IDs. Hotspot metric values
include deterministic ranks. Unsupported metric names and unknown node IDs are rejected.

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
