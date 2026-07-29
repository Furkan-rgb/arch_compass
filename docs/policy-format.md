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

Global source registration rejects any `repository` or `accepted_adr` document; those documents
belong in the selected repository's local policy directory. Registration preserves each remaining
policy's authored scope and applicability subject.

## There is no index, and no rebuild

Policies are read from their sources whenever they are asked for. There is no build step, no
stored index, and no command to bring one up to date — a policy edited on disk is the policy the
next review is shown.

That is a deliberate removal rather than an omission (ADR 0013). A `sqlite-vec` index used to
chunk each policy by section, embed the chunks, and return the `top_k` nearest to a query. It
stopped being read once judgement began receiving the whole corpus in one request: 48 policies
against an input budget near 490,000 characters, which fits several times over. What retrieval
added at that size was a ranking that could leave the passage a reader needed out of the request,
and a build step between editing a policy and seeing it apply.

What this removes with it: the embedding model a workspace had to configure, the corpus hash and
index version that decided whether a rebuild was needed, per-section chunking, and the
distance-ranked, scope-tie-broken selection that produced `matched_sections` evidence.

Duplicate policy IDs across effective sources are still rejected, at parse time. Applicability is
still enforced: a repository's own policies are in reach only for a caller that names that
repository, and scoped policies never widen to a caller with no identity.

The model receives original text, IDs, scope, applicability, and strength. A verdict binds to
policies by position in the presented list, so no policy ID is ever read back out of a reply.

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
