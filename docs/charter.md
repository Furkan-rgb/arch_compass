# The ArchCompass charter

What ArchCompass is for, what it refuses to be, and the rules that settle an argument about
what to build next. [architecture.md](architecture.md) and [workflow.md](workflow.md) describe how the thing
works; this one says why it works that way, so that a decision taken today still makes sense
in six months.

If a proposal cannot be argued for from this page, it is probably not an ArchCompass
feature — however good an idea it is.

## The problem

A codebase records what was built. It does not record what the team was trying to build.

Every tool that reads only the code is therefore stuck answering a smaller question than the
one people actually have. A linter can tell you a module imports another module. It cannot
tell you whether that import is a mistake, a deliberate shortcut with a date on it, or the
entire point of the design — because the answer lives in a decision somebody made, possibly
years ago, possibly never written down.

So teams end up with two failure modes. Either nobody checks the architecture, and it erodes
one reasonable-looking commit at a time. Or a tool checks it against rules that do not know
the team's intent, and everyone learns to ignore the output.

## The mission

**Give a team architectural judgement they can trust, argue with, and re-check as the code
changes.**

Trust comes from evidence: every claim points at the source that produced it. Argument comes
from separating the machine's conclusion from the team's decision. Re-checking comes from
reviews being immutable records that can be compared, not reports that get regenerated and
lost.

## Who it is for

The person who is responsible for a codebase's structure over time — a tech lead, a staff
engineer, an architect, the maintainer who will still be here next year. Someone with the
standing to decide that a dependency is fine, and the need to have that decision remembered.

Not the person trying to get one pull request merged this afternoon. ArchCompass is worth
opening when the question is "is this still the system we meant to build", not "does this
line pass".

## Three commitments

Everything ArchCompass does follows from these. They are not aspirations; they are already
load-bearing in the code, and breaking one is a redesign rather than a change.

**1. Evidence before opinion.** Nothing is asserted without saying where it came from. The
repository is analysed deterministically — parsed, never imported or executed — and every
candidate carries pinned source excerpts, measurements that state their own nature and
limits, and a detection rationale. The model is given evidence and asked what it means. It
is never asked what a verdict should rest on.

There are two places a model is allowed to choose what it looks at, and both are the same
bargain. A judgement that would stop the review and ask a person may first put read-only
questions to the repository, because a question the code already answers is not worth an
interruption; and a reader asking a follow-up about a finished review is answered through the
same toolbox. Both are permitted only because every lookup is recorded with its arguments and
its answer, and shown.

What that pass may do is bounded precisely. It changes whether a question is asked, and it
may change the verdict — but only by handing what it found back to the same judge, which
decides again with the policies in front of it. It never writes a lookup into the evidence a
finding rests on. Evidence is the detector's; observations are the model's; they are recorded
apart and a reader can see which is which.

**2. The machine assembles, the model judges, the person decides.** These are three
different jobs and ArchCompass keeps them visibly apart. Deterministic code owns identity,
structure, delta, retrieval and provenance. The model owns the verdict and its reasoning.
The human owns the disposition — which is why `Finding` (what ArchCompass concluded) and
`StandingDecision` (what the team decided to do) are separate records, and why a decision
never edits a judgement.

A corollary, small enough to look like a coding convention and load-bearing enough to
belong here: **a model may name what the application holds, and may never index into it.**
Identity is the application's, so a list ArchCompass built for a prompt is never numbered for
a model to point back into. Ask for the identifier and drop what does not match, or make one
call about one thing so there is nothing to point at.

The reason is that an ordinal has no wrong reading a program can see. Out of range it is
fatal; in range but wrong it resolves to the wrong policy and is recorded for ever as a
correct citation. A name has exactly one failure and it is visible: it matches nothing, and
matching nothing can be dropped without losing the answer around it. This is not
hypothetical — a clarification round that numbered every finding, forbade some of the numbers
in prose and raised on the rest destroyed reviews that had already judged every candidate.
`tests/unit/test_boundaries.py` sweeps the model schemas and fails on a field that asks for a
place in a list.

**3. A review is a record, not a message.** Reviews are immutable and sequenced per branch —
one number line a branch keeps whatever case is being reviewed against. That is what makes the second review meaningful: it can be compared with the
first, candidates can be tracked through succession, and "we already decided this" survives
a rerun. A tool whose output is disposable cannot accumulate trust.

## What ArchCompass is not

Stated plainly because each of these is a plausible-sounding direction that would break a
commitment above.

- **Not a linter.** A candidate is a structural shape that deserves judgement, not a
  violation. If it could be decided by a rule, it should be a rule, in someone's linter.
- **Not a code generator.** ArchCompass does not write the fix. It can recommend a response;
  acting on it is the team's.
- **Not an autonomous agent.** It does not roam the repository, choose its own goals, or act
  without being asked. The model never picks which candidates are reviewed, and the lookups
  it may make about one are bounded, read-only, and recorded where the reader can see them.
- **Not a dashboard.** Counts are orientation, read once, on the way to the work. A number
  that nobody acts on is decoration.

## What "good" means in the interface

The workbench is where the commitments meet a person, so it has its own rules. These are the
ones that decide most day-to-day design questions.

**The queue is the product.** A review's value is realised when a human works down the list
and decides things. Every surface is either that list, something that helps you decide an
item on it, or the record of what you decided. Anything that is none of those is competing
with the work.

**Scanning beats reading.** A reviewer arrives with a list of things to triage, not an
article to read. Lead with the identifier, because that is what is being looked for; keep
the sentence, because it is what explains; but never make someone read a column of prose to
find out which item is theirs. This is why the queue and the delta both lead with the
qualified name in mono and demote the summary to a line beneath it.

**The second visit is the important one.** Most reviews are not somebody's first. What they
want is the short list of what is different from the last time — so the delta is a first
class surface, it names *what moved* rather than restating everything, and seeing a change
and opening it is one action rather than two.

**Say where it came from.** Every verdict carries its policies, its evidence, its model
identity and its retrieval provenance. Uncertainty is stated, not smoothed: a finding that
turns on something the repository cannot answer says so, in its hinge.

**Ask rather than assume.** When a judgement depends on context that is not in the code,
ArchCompass stops and asks a person. Answers are recorded on the case revision the
asking review opened, and every candidate is judged again — unless the answers were submitted
with "stop", which records them and finishes the review without another round. This is a feature,
not a failure — a confident wrong answer is worth less than an honest question.

The corollary is that ArchCompass does not demand context up front. A case starts empty and
fills in as reviews ask for what they actually need. Anything a form asks for before the
first finding exists is asked of someone with no reason yet to answer it, which is how you
get a field everybody leaves blank.

**Never make someone type what they could pick; never make them pick when the truth is not
on the menu.** The model proposes the answers it thinks likely, and the interface always
offers writing your own and skipping the question outright. A proposed answer is a shortcut,
never a closed set.

**A colour never carries meaning alone.** Every verdict has a glyph and a word. Only one of
the three still has a hue: `material` is the accent red, and `held` and `cleared` gave theirs
up for weight, because three colours competing on one screen taught a reader to read the
colour first.

**Nothing is inferred on a person's behalf.** A skipped question is recorded as skipped. An
unanswered one is not guessed at. Explicit unknowns are more useful than implied knowledge.

## How to use this when deciding something

Ask, in order:

1. **Does it serve the queue?** Does this help someone decide an item, or record what they
   decided? If not, it is a different product.
2. **Does it keep the three jobs apart?** Does it let the machine assert something it cannot
   evidence, or let the model decide something the person should?
3. **Does it survive the second review?** Will it still make sense when there are eight
   reviews in the lineage and most candidates are unchanged?
4. **Can someone see where it came from?** If it appears on screen, its provenance is
   reachable.

Three worked examples, so the rules read as something that was actually used:

| Question | What the charter said | What was built |
| --- | --- | --- |
| Evidence surface listed every excerpt flat | "Say where it came from" — an excerpt only means something next to the claim it supports | Grouped under the candidate it was pinned for, and labelled by which step pinned it |
| The delta was four panels of full sentences | "Scanning beats reading", "the second visit is the important one" | One list keyed on the identifier, filtered by change state, each row opening the finding |
| Clarification questions were a blank box | "Ask rather than assume", "never make someone type what they could pick" | The model proposes likely answers; writing your own and skipping are always offered |
| The architecture case carried a free-text goal, then hand-authored constraints and decisions | "Ask rather than assume", "nothing is inferred on a person's behalf" | Both removed. A form asking for intent before a finding exists is asked of someone with no reason yet to answer it. Intent now enters two ways only: the policies that bear on a candidate, and the answers a clarification round records |
| A review asked a person what the code already said | "Ask rather than assume", "evidence before opinion" | A judgement may read the reviewed repository while it decides, so a verdict that turns on a fact the code holds goes and gets it instead of becoming a question. See [workflow.md](workflow.md#what-a-judgement-may-look-at) |
| A real model almost never asked anything | "a confident wrong answer is worth less than an honest question" | The prompt permitted a hinge and gave it no standing. It now says an empty case out loud, gives asking first-class standing, says when *not* to ask, and requires two to four proposed answers |

## Where this is still open

Written down so that nobody mistakes an unsettled question for a settled one.

- **Rejudgement scope.** Every extant candidate is rejudged after a case revision, because
  an answer is about intent and intent bears on all of them. That is a correctness-first
  starting point, not a proven rule, and it is the expensive choice — note that it is the
  *opposite* of what a first-round review does, where only changed and new candidates reach
  a model at all.
- **Retrieval strategy.** Dense top-K plus scoped and required policies is the current
  default. The provenance record is deliberately generic so a hybrid or graph retriever can
  replace it without touching the domain.
- **Languages.** Deterministic analysis is Python-only today. Nothing in the domain assumes
  it.
- **Scale.** The workbench is designed around a review a person can work through. What a
  thousand-candidate review should do is not yet answered.
