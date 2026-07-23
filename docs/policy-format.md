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

Rebuild parses and validates every source, rejects duplicate IDs, creates one content-stable chunk
per section, embeds chunks, and stores them in a dimension-specific `sqlite-vec` table. A rebuild
creates a new immutable index version. Consultation embeds a structured force query, performs
bounded nearest-neighbour search, joins back to original text, deduplicates sections and policies,
and applies repository/ADR/team/user/general scope only as a relevance tie-break.

The model receives original text, IDs, scope, and strength—not vectors. Conflicting retrieved
guidance remains visible. A report cannot cite a policy absent from the retrieved set.

