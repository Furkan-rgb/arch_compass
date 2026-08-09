# ADR 0017 — A candidate carries its usage

**Status:** Accepted, implemented
**Date:** 2026-08-09
**Related:** ADR 0013 (showing the code); master plan §12.0 (division of labour);
`docs/plans/investigation-quality.md` §1

## What forced the question

The judging stage decided blind, and nobody had noticed because its payload looked complete.
It held the case, the whole policy corpus, and the candidate: pattern, summary, participants
with their qualified names and spans, measurements, limitations. What it did not hold was a
single line of the repository — not the definition, not the comment above it, not one
consumer.

Two of the three patterns this advisor detects are questions about usage. "Are these copies
of `RETRY_LIMIT` one fact or two" is answered by who reads them. "Does this seam earn its
place" is answered by what depends on it. The stage was being asked both from two identifiers
that happen to be spelled the same.

It answered accordingly. On a seeded bench — one duplication provably one fact, both copies
feeding the same vendor client; one provably a coincidence, with a comment at each definition
saying so — a run confidently called the one-fact duplication coincidental, and another run
quoted a value the code does not contain. Prompt work could not reach it: every rule in
`judge-finding-candidate` v5 through v11 is a rule about how to reason, and the input had
nothing in it to reason about.

Elicitation cannot repair it either, and the reason is structural. A question exists only
where a verdict hinges, and a confidently wrong verdict hinges on nothing.

A prototype settled it. Attaching consumer spans and definition spans — with their leading
comments — to the judge payload made the small model call the coincidence correctly in 3/3
runs, *citing the comments*, where the plain judge flipped between runs. The one-fact
duplication became a grounded judgement whose residue was genuine intent ("must these move
together?"), which is exactly what elicitation exists for, and a run then asked it.

## Decision 1 — usage arrives as participants, not as a new field

`UsageEvidenceService.augment` runs over the detected candidates before anything is
fingerprinted, and appends what uses each one as ordinary `FindingParticipant`s: for a
duplicated constant, the lines outside the copies that name it; for a sole implementation,
the nodes that import, call or reference either side of the seam.

A field of its own was the obvious alternative and it buys nothing but work. Excerpt pinning,
source rendering, the conversation stages, the delta partition and both fingerprints already
know what a participant is. Usage inherits every one of them by being one, and a new field
would have had to be threaded through each of them by hand — which is five places to forget.

The application does the assembly and the model is given no way to reach for more, so §12.0
needs no amendment. Its amendment for *investigating* stops at elicitation.

## Decision 2 — the evidence is structural first, and text only where it must be

A sole implementation's dependants come from the atlas: the `IMPORTS`, `CALLS` and
`REFERENCES` edges are already resolved and already carry locations where the parse knew one.
Nothing is searched for.

A duplicated constant leaves no edge — a module reads a name — so that one is a text sweep,
and it goes through the analyser's own file discipline. `searchable_files` and
`numbered_lines` were extracted from `RepositoryInvestigator` and are imported rather than
copied, because a sweep that disagreed with the investigation's about which files exist would
let a candidate be judged against a repository the reader's own questions cannot see.

A `scattered_concept` is left exactly as detected. Its detector's method already *is* a name
search across modules, and every module it found is already a participant pointing at the
line that names the concept. Running the same search again and presenting the second run's
hits as new evidence would be theatre.

## Decision 3 — a cap, with the overflow stated as a fact

At most six usage participants per candidate, ordered by path and line so which six is a
property of the repository rather than of the filesystem's answer order.

Every augmented candidate gains two measurements — `consumer_sites` / `consumer_sites_shown`,
or `dependant_sites` / `dependant_sites_shown` — because "five of forty" is two numbers and
neither implies the other. A constant read forty times is itself a finding, and the
measurement is where that finding belongs; forty spans would spend the payload repeating one
fact and let the excerpt caps downstream decide which of them the model actually saw.

Both are written even when the answer is zero. A candidate with no usage measurement is one
nobody checked; a candidate saying zero is one that was checked and found nothing, and a
stage that cannot tell those apart will read the first as the second every time.

A hit in a file the atlas holds no module node for — a TOML settings file, most often — is
counted and not shown. It has no node id and no qualified name, so a participant made from it
would put a node in the record that no atlas can resolve.

## Decision 4 — a definition is served with the comments above it

`ReviewSourceService.for_candidate` reads the code at the candidate's spans and widens each
one upward over the contiguous run of full-line `#` comments that touches it, bounded at
twelve lines.

This is where the decisive fact sat in every bench case. A constant's recorded span is the
line that assigns it; what the constant *means* is written directly above it. The widening is
deterministic, happens in the service rather than in `SafeSourceReader` — the reader answers
"what do lines a to b say" and must not acquire an opinion about Python syntax — and the run
has to *touch* the span, so a comment separated by a blank line stays with whatever it was
about.

## Consequences

**Every stored verdict dies with this change, and that is the intended behaviour.**
Participants are inputs to both `boundary_fingerprint` and `content_fingerprint`, so an
augmented candidate fingerprints differently from the same candidate detected yesterday. No
cached verdict carries across, no baseline matches, and delta lineage restarts at this
revision. That is what verdict reuse should always have meant: *a verdict cached against
usage must die when usage changes*, and the one-time break is the price of the invariant
holding from here on. The prompt identity in the cache key moves anyway — v11 to v12 — so the
break is not avoidable by pretending otherwise, and no migration shim was written.

**The judging payload grows** by the code at the candidate's spans, capped by
`MAX_EXCERPT_LINES` per participant and by six added participants per candidate. It is the
same order as the excerpts a review already pins.

**A run costs one repository sweep more.** One pass over the searchable files finds every
duplicated constant's occurrences at once, before the first model call, and the read of each
candidate's spans happens on a cache miss only — a run whose verdicts all carry reads
nothing, because nothing is being judged.

**§12.0 is untouched.** The application chose this evidence, as it chose the spans that were
already there. `test_judging_is_deliberately_given_no_way_to_investigate` still passes and
still means what it says.
