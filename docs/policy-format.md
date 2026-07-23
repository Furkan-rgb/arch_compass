# Policy format and retrieval

Each policy is one Markdown file with YAML front matter:

```yaml
id: hide-implementation-details
title: Hide implementation details behind the owning boundary
scope: general
strength: guidance
tags: [information-hiding, dependencies]
source:
  author: ArchCompass
  inspiration: [software-design literature]
```

Supported scopes are `general`, `user`, `organisation`, `repository`, and `accepted_adr`.
Strength is `guidance`, `preferred`, or `required`. Repository-local policy files live in
`<repository>/.archcompass/policies/`; indexing reads but never writes them.

The body must contain `Intent`, `Guidance`, `Signals`, `Diagnostic questions`,
`Likely consequences`, `Exceptions`, `Positive example`, `Counterexample`, and
`Related policies` level-two sections.

Required sections must contain text. Duplicate level-two headings are rejected
case-insensitively. Policy-source roots are canonicalized; source-root symlinks and descendant
policy paths that escape a source directory are rejected.

## Source registry

Effective consultation sources are:

1. the bundled corpus;
2. canonical sources registered in the workspace database; and
3. `<repository>/.archcompass/policies/` for the currently selected repository.

Repository-local sources are never added to the workspace registry. Manage persistent sources
with:

```bash
archcompass policies sources add /path/to/policies
archcompass policies sources remove /path/to/policies
archcompass policies sources list
```

`policies rebuild --source PATH` registers each supplied source before rebuilding. Registration
preserves each policy's authored scope.

Consultation preflight parses and validates all effective sources. It compares the corpus hash,
embedding provider, model, and dimensions with the latest index. A matching index is reused; a
missing or stale index is rebuilt before reasoning begins. An empty or invalid corpus and any
embedding failure stop the consultation before a reasoning prompt executes.

Rebuild rejects duplicate IDs, creates one content-stable chunk per section, embeds chunks, and
stores them in a dimension-specific `sqlite-vec` table. Each rebuild creates a new immutable index
version. Consultation embeds a structured force query, performs bounded nearest-neighbour search,
joins back to original text, and expands the nearest-chunk window until it has exactly `top_k`
unique policies or exhausts the index. Ranking is deterministic under tied distances. Sections
are deduplicated by normalized `(policy ID, section heading)`; the packaged default retains at
most three nearest sections per policy through `retrieval.max_sections_per_policy: 3`.
Repository/ADR/organisation/user/general scope is only a relevance tie-break after distance.

The model receives original text, IDs, scope, and strength—not vectors. Reports retain canonical
policy evidence metadata: ID, title, scope, strength, and matched sections. Conflicting guidance
is represented explicitly by at least two retrieved policy IDs, an explanation, and a
reconciliation. Concern and final-report validation reject invented policy IDs.
