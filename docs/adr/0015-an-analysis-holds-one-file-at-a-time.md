# ADR 0015 — An analysis holds one file at a time

**Status:** Accepted, partly implemented
**Date:** 2026-08-06
**Related:** ADR 0002 (no shims for superseded schemas); `docs/deploy.md` (hosted limits)

## What forced the question

The hosted demo now fetches a repository a visitor names, so the analyser is pointed at code
nobody chose in advance. Measured against real repositories, it does not scale:

| repository | Python | nodes | peak memory | time |
|---|---|---|---|---|
| pallets/flask | 0.6 MB | 1,693 | 147 MB | 1s |
| psf/black | 5.2 MB | 2,235 | 375 MB | 4s |
| sqlalchemy | 19.6 MB | 38,720 | 1,648 MB | 50s |
| django | 30 MB | — | >814 MB, did not finish | >240s |

A container's `/tmp` is memory, so this is spent from the same allowance the server runs in;
exhausting it kills the process rather than the analysis, taking every session on the
instance with it.

## What measurement showed, twice

Both times the cost was somewhere other than where reading the code suggested.

The first guess was the optional mypy resolver. Removing it made django **worse** — 814 MB
against 679 MB — because mypy's cost is bounded and the analyser's is not.

The second guess was `_compute_metrics`, whose per-node loop rescans every edge. Memoising it
by owning module was correct and bought almost nothing: profiling put it at 3.2s of 21s. The
real cost was `_resolve_symbol`, whose last-resort suffix match scanned every symbol for
every reference — 56.6 million string comparisons on psf/black, 63% of the run. Replaced with
a table of dotted tails built once, black went 21s → 4s and sqlalchemy from never finishing
to 50s.

The lesson is recorded because it will recur: **profile this analyser, do not reason about
it.** Its hot paths have twice been invisible to reading.

## The remaining problem

Time is no longer what stops a repository being reviewed. Memory is, and it is structural
rather than incidental: `analyze()` holds, simultaneously and for the whole run, every file's
raw bytes, every file's decoded text, and every file's parsed AST. A Python AST is roughly
ten to twenty times the size of its source, which is where the ~40 KB per node goes.

Nothing that survives the run needs any of it. The atlas — nodes, edges, signals, metrics —
is what reaches SQLite, and the review path reads code excerpts from disk on demand
(`SafeSourceReader`), with findings snapshotting their own excerpt text
(`domain/review.py`, `BoundaryExcerpt`). No caller needs a tree after the file it came from
has been read.

## Decision

Restructure `analyze()` so that one tree is live at a time.

- **Pass 0** — discover files; build package nodes, the module-name map and the `owned` set
  from paths alone. None of it needs a parse.
- **Pass 1, per file** — read bytes, update the fingerprint digest, decode, parse; collect
  symbols, local signals, module facts and **local metrics**; extract unresolved reference
  sites (source node, line, dotted expression, edge kind) and per-method signature records
  for the structural-protocol comparison. **Then drop the tree and the text.**
- **Pass 2** — resolve the recorded sites against the completed symbol table and the suffix
  index. No trees: resolution is table lookup, and it must happen after pass 1 because the
  0.7 suffix match needs every symbol before it can say a name is unambiguous.
- **Pass 3** — metrics from the graph and the local metrics recorded in pass 1.

Expected: transient cost becomes one tree at a time; resident cost is the graph, around 3–6
MB per MB of Python rather than 48. `ARCHCOMPASS_MAX_PYTHON_MB` could then plausibly go to
30–50 rather than the current 8.

## Constraints on doing it

- **The atlas must not change.** `tests/unit/test_analysis_equivalence.py` compares the whole
  serialised atlas against committed goldens for three bundled examples, and is the proof
  obligation for every step. `PARSER_VERSION` and the analysis config hash must not move — a
  bump would mark every stored atlas in every workspace stale to record that nothing changed.
- **Two details are easy to break silently:** the fingerprint must hash Python and
  configuration files interleaved in the same sorted order it does today, and signature
  extraction must reproduce `ast.unparse`'s annotation strings exactly.
- **Land it in one code path.** No second "streaming analyser" beside the old one.
- **Do not spill trees to disk.** On the deployment that needs this, `/tmp` is the same RAM.
- **The mypy resolver stays as it is** — whole-program by nature, a subprocess, and its
  memory is its own.

## Order

1. Stream the fingerprint and stop retaining `SnapshotFile.content`. Small, and worth little
   on its own — bytes are ~40 MB of sqlalchemy's 1,648.
2. Move local metrics and reference-site extraction into pass 1 and free trees there. **This
   is the whole win**; the steps around it are bookkeeping.
3. Convert the structural-protocol comparison in `boundary_signals.py` to work from extracted
   signatures rather than from two live ASTs — the one place today where two files' syntax
   meet.

Until step 2 lands, the caps in `docs/deploy.md` are what keeps the demo inside its
container, and they are sized from the measurements above rather than from round numbers.
