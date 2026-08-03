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

Because Python `Protocol` conformance is normally structural, the analyzer can also emit a
lower-confidence `implements` edge without explicit inheritance. It does so only when a class
provides the Protocol's complete operation set with compatible arity and at least two matching
type annotations per operation. This remains static conformance evidence, not proof of runtime
dispatch.

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

The workspace may sit inside the analysed repository — indexing ArchCompass itself from its own
workspace is the ordinary case — because the analyzer excludes the workspace subtree from every
snapshot. Its files are absent from the atlas and, since a review writes to the workspace on every
run, absent from the content fingerprint too; without the exclusion the atlas would be stale the
moment it was built. Explicit repository arguments are still checked to exist and be a directory
before runtime construction. Indexing, queries, and advice never modify the analysed repository.

## Query model

Supported queries include repository and subsystem summaries, node details, direct dependencies
and dependants, forward and reverse neighbourhoods, known callers, interface implementations,
related tests, shortest dependency paths, cycles, metric hotspots, token-based node search, and
bounded excerpts. The ID-free `signals` query can retrieve all signals or filter by signal code,
allowing a consultation to investigate a bounded signal exposed in its initial overview without
already knowing a node ID.

Every result has typed fields for node summaries, metric values, relationships, test IDs,
signals, and excerpts in addition to its bounded summary and node IDs. Hotspot metric values
include deterministic ranks, canonical names, measurement/proxy classification, calculation
scope, definitions, and limitations. Metrics are named `public_call_targets_in_affected_modules`
and `bounded_resolved_call_chain_nodes`; the earlier overstated spellings are not accepted.
Unsupported metric names and unknown node IDs are rejected.

Before focused querying, brownfield reasoning receives a deterministic `AtlasOverview`, not a
raw graph or count-only prose string. It contains bounded inventory counts, top-level named
nodes, at most eight non-zero module/class/configuration hotspots, their salient typed metrics,
up to twenty representative typed signals, explicit selection reasons, and static-analysis
limitations. Focused packets
then carry self-describing node and relationship evidence: paths, qualified names, types,
locations, resolved endpoints, metric semantics, signals, and why each node was selected.

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
- `broad-input-boundary-preparation` is a structural proxy that does not require sibling
  implementations. It records when one resolved port implementation feeds at least three nested
  paths from one input substructure into at least two fields of one three-or-more-field projection
  passed to a call or return. It does not label that projection as misplaced responsibility;
  persistence mappers, presenters, exporters, and anti-corruption adapters may legitimately have
  this shape.
- `parallel-boundary-preparation` is a structural proxy: it requires sibling implementations of
  one resolved or structurally matched Protocol operation to share a substantial static
  input-to-request fingerprint. It makes those methods inspectable, but cannot prove semantic
  duplication, provider-neutral meaning, or misplaced ownership.

Confidence describes static resolution quality; it is not a probability that the architecture is
good.
