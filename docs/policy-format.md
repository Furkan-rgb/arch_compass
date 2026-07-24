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
Strength is `guidance`, `preferred`, or `required`.

`general` policies apply everywhere and must omit `applies_to`. `user` and `organisation`
policies require an explicit, nonempty subject:

```yaml
scope: organisation
applies_to: example-organisation
```

Repository and accepted-ADR policies apply to a repository subject. When they live under
`<repository>/.archcompass/policies/`, `applies_to` may be omitted: the parser derives the same
stable `repo_...` identity used by that repository's Atlas. They may instead declare an explicit
subject. Outside a repository-local policy directory, an explicit subject is required. Indexing
reads but never writes repository-local policy files.

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

`policies rebuild --source PATH` registers each supplied source before rebuilding. Global source
registration rejects any `repository` or `accepted_adr` document; those documents belong in the
selected repository's local policy directory. Registration preserves each remaining policy's
authored scope and applicability subject.

Consultation preflight parses and validates all effective sources. It compares the corpus hash,
embedding provider, model, and dimensions with the latest index. A matching index is reused; a
missing or stale index is rebuilt before reasoning begins. An empty or invalid corpus and any
embedding failure stop the consultation before a reasoning prompt executes. The corpus hash
includes each policy's applicability and source identity, so byte-identical local policy files
from different repositories cannot reuse the wrong immutable index.

Rebuild rejects duplicate IDs, creates one content-stable chunk per section, embeds chunks, and
stores them in a dimension-specific `sqlite-vec` table. Each rebuild creates a new immutable index
version. Consultation embeds a structured force query, performs bounded nearest-neighbour search,
joins back to original text, and expands the nearest-chunk window until it has exactly `top_k`
applicable unique policies or exhausts the index. Scoped candidates are filtered against the
consultation's user, organisation, and repository identities during that expansion. A retrieval
without an applicability context returns only general policies; missing identity never widens
access to scoped guidance. Ranking is deterministic under tied distances. Sections are
deduplicated by normalized `(policy ID, section heading)`; the packaged default retains at most
three nearest sections per policy through `retrieval.max_sections_per_policy: 3`.
Repository/ADR/organisation/user/general scope is only a relevance tie-break after distance
among policies that apply.

The model receives original text, IDs, scope, applicability, and strength—not vectors. Reports
retain canonical policy evidence metadata: ID, title, scope, applicability subject, strength,
and matched sections.
Conflicting guidance is represented explicitly by at least two retrieved policy IDs, an
explanation, and a reconciliation. Concern and final-report validation reject invented policy
IDs.

## Bundled corpus provenance

Bundled policy text is authored and paraphrased by ArchCompass. The `source.inspiration` field
names a concept's intellectual source where the relationship is direct; it does not imply that
the policy body is a quotation or that its source endorses ArchCompass.

Several bundled policies draw on John Ousterhout's software-design concepts. Primary references
used for their terminology and intent are:

- [A Philosophy of Software Design](https://web.stanford.edu/~ouster/cgi-bin/aposd.php), the
  author's official book page.
- [Modular Design](https://web.stanford.edu/~ouster/cgi-bin/cs190-winter18/lecture.php?topic=modularDesign),
  Ousterhout's Stanford CS 190 notes on deep modules, information hiding, different-layer
  abstractions, pulling complexity downward, and comparing two designs.
- [Working Isn't Good Enough](https://web.stanford.edu/~ouster/cgi-bin/cs190-winter18/lecture.php?topic=working),
  his CS 190 notes contrasting tactical and strategic programming.
