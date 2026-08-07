# ADR 0016 — A review can be asked about part of a repository

**Status:** Accepted, implemented
**Date:** 2026-08-07
**Related:** ADR 0015 (an analysis holds one file at a time); `docs/deploy.md` (hosted limits)

## What forced the question

ADR 0015 measured what an analysis costs and settled on a node cap, because memory turned out
to be the graph rather than the parse. That made the caps honest and did nothing about what
they are spent on: a repository's tests, its documentation, its vendored copy of somebody
else's library and its examples are all Python, and they buy nodes at the same price as the
code the review is about.

For a visitor pointing the hosted demo at a real repository, that is the difference between
being reviewed and being refused. The repository is not too large; the interesting part of it
is well inside the cap, and the uninteresting part spends the cap first.

So a caller can now name folders to leave out, and there is an endpoint that lists what is
there so the choice can be made with the sizes in front of them.

## Decision 1 — an exclusion is an input to one analysis, never a default

`IGNORED_DIRECTORIES` is a property of the analyser: a `.git` is not source for anybody. An
exclusion is a property of a request: `tests/` is not what one reader wants reviewed, and is
exactly what the next reader is asking about.

Concretely, that means an analysis given no exclusions must be byte-for-byte the analysis it
was before this feature existed — same discovery, same fingerprint, same configuration hash.
`tests/unit/test_analysis_equivalence.py` is the proof obligation and its goldens were not
regenerated.

## Decision 2 — the scope lives in the fingerprint, not in the configuration hash

The tempting move is to hash the exclusion list into `_analysis_config_hash`, beside the
parser version and the ignored directories. It is wrong twice.

It is redundant. The content fingerprint is a digest over the files the analysis read, in
order; a file that was excluded never entered it. An atlas built without `tests/` already
fingerprints differently from one built with it, without anything being told to say so.

It is also destructive in the one case that matters most — the empty one. The configuration
hash is deliberately conservative: ADR 0015's limits are recorded in it *only when there are
limits*, so that an unlimited analysis hashes to what it always did rather than marking every
stored atlas in every workspace stale to record that nothing changed. Adding a scope key
would have to make the same exception, and the exception is the whole rule; there is nothing
left for the key to do.

The general form of the rule: the configuration hash says what kind of analysis this was, and
the fingerprint says what it was of. Which folders were read is the second question.

## Decision 3 — the selection is persisted server-side

This is the part that could not be skipped, and the reason is not convenience.

Every use of a stored atlas begins by asking the repository what it fingerprints as *now*
(`AtlasFreshnessService`). That recomputation walks the repository again. Asked without the
exclusions the analysis was run under, it reads the folders that were skipped, produces a
different digest, and reports the atlas stale — and re-indexing lands in the same place, so a
scoped atlas would be stale from the moment it was written, forever.

The caller that checks freshness is not the caller that chose the scope: it has a stored atlas
and a `root_path`, and nothing else. So the scope is stored under that same canonical root
path, in `scope_selections` (migration 032), keyed exactly like `source_origins`. Indexing
without naming a scope applies the remembered one, which is also what somebody who narrowed a
review and then pressed re-index means.

An empty list is stored and is not the same as no row. No row is "nobody has chosen"; `[]` is
"somebody looked and chose everything", and it survives a later index that names nothing.

## Decision 4 — suggestions are advisory, and stay a flag

`POST /api/repositories/tree` lists directories two levels deep that have Python under them,
with recursive file and byte counts, and marks the ones whose name is in `SUGGESTED_EXCLUSIONS`
— `tests`, `docs`, `examples` and their singulars.

It is a guess from a directory's name and it is never applied. A library of examples keeps its
product in `examples/`; a review about how a project tests itself is a review of `tests/`.
Silently excluding either would produce a confident review of a repository the reader did not
point at, and the counts are what actually informs the choice — `suggested` only decides which
checkboxes start out looking obvious.

The listing skips the ignored directories and symlinks, the same way discovery does, because
its numbers are an answer to "what would excluding this save" and a number the analysis would
not agree with is worse than no number. It spends no budget: walking a directory is cheap, and
this is the cheap step that avoids the expensive one.

## What this does not do

Nothing here excludes a *file*, and nothing excludes by pattern. A subtree is what the reader
is choosing between in the listing they were given, and a glob would be a second language with
its own answer to "is `src/apps` inside `src/app`". Exclusions are compared part by part for
that reason.
