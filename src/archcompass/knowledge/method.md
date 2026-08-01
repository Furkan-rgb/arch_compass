# How ArchCompass works

Background for answering questions about a boundary review. This describes the method that
produced the review — what was looked at, how, and what the words in it mean. It is not
evidence about any particular repository, and it never settles a question about one: where
it disagrees with a verdict in the review, the verdict is what happened.

## What ArchCompass is

ArchCompass is an architecture advisor. It reads a Python repository, finds the
boundaries in it, and judges one at a time whether each is earning its place — given what
that repository is actually being asked to do. It does not propose an architecture, rank
repositories, or score code quality. It answers one question, repeatedly, about structure
that already exists.

## What a boundary is

A boundary is an abstraction that stands in front of an implementation: a port, an
interface, a protocol, an abstract base class, a wrapper — anything a caller depends on
instead of depending on the concrete thing behind it.

The clearest case is an abstraction where **exactly one implementation exists**. That is a
shape, not a fault. Such a boundary may be exactly right: it can own a seam at a process,
vendor or storage edge; keep a dependency out of the domain; give tests something to
substitute; carry a contract more than one caller reads; or absorb a variation that is
genuinely coming. It is only a problem when it buys none of those things here.

Unnecessary complexity has two directions, though, and ArchCompass looks for both — an
advisor that found only surplus abstraction would quietly argue for copying instead. So it
also looks for the opposite: knowledge with **no owner at all**. The same constant stated
in several modules, or a concept whose name has spread into modules that have no reason to
know it exists. There the advice, where the case supports any, is the reverse — give the
fact one owner, rather than remove a boundary.

## What the detector does, and what it cannot see

Detection is deterministic and complete: the repository is parsed into an atlas of nodes
and relationships, and every instance of each shape is surfaced. No model chooses what to
look at, so nothing is quietly skipped and the same repository always yields the same set
in the same order.

Three detectors run. **Sole implementation** finds an abstraction with one implementation
behind it. **Duplicated knowledge** finds one module-level constant stated in several
modules, and reports whether the copies still agree. **Scattered concept** finds a module
that already sits behind an abstraction whose name is nonetheless written into modules
outside its package.

Static analysis has real limits, and every finding states them. It cannot see an
implementation registered at runtime, supplied by a different repository, or planned but
not yet written. So the count alone can never establish that no variation exists — only the
case can say that. Equally, the detector cannot establish that variation *does* exist.

One detector runs. Finding nothing means that shape is absent, not that the repository is
structurally sound.

## What a case is

An ArchitectureCase is the requirements, constraints and expected future changes for one
decision — written by the person asking for the review, not inferred from the code. It is
what makes a verdict possible: the same boundary is right in one case and wrong in another,
and without a case there is only a general preference about abstractions.

Cases are append-only. Each revision is immutable, and a review pins the exact revision it
judged against, so a review can never be quietly re-grounded by a later edit.

## How policies are used

The policy corpus is a set of markdown documents, each naming one design principle with its
intent, guidance, signals, exceptions, and examples. Policies are reasoning lenses, not
rules: a policy that bears on a boundary is a consideration to weigh, never an automatic
violation.

Every policy in the corpus is presented **whole and in full** with every single candidate.
Nothing is retrieved, ranked or filtered first. That is why a review can say how many
policies bore on a boundary out of how many were presented: a policy that does not appear
against a boundary was considered and found not to apply, which is a different statement
from never having been shown.

## What a verdict means

Each boundary gets one verdict, reached in its own model call with that boundary's
evidence, the case, and the whole corpus in front of it.

Either it earns what it costs in this case, or it does not. Only the second carries a
recommendation; a verdict that nothing needs doing has no next action.

The verdict is worded in the vocabulary of the shape it is about, because one phrase cannot
serve both directions. For an abstraction it reads *earning its place* or *not earning its
place*. For a constant with no owner it reads *needs one owner* or *separate concerns* —
"not earning its place" would be nonsense there, since the finding is that something is
missing rather than surplus. For a concept named outside its package it reads *has leaked
past its boundary* or *named where it should be*.

Both outcomes are recorded and both are results. A boundary examined and cleared is
evidence that the advisor looked, and it is often the useful answer to a question. The two
errors are equally wrong: condemning a shape that is earning what it costs, and clearing
one that is not — because clearing reads as approval, and what is cleared stays forever.

## References, and where they come from

Each reviewed boundary carries a reference like `BR-001`, assigned by ArchCompass in
detection order — never written by a model. Detection is deterministic, so the same
boundary in the same atlas always gets the same reference.

The same rule governs everything identifying in a review: policies and boundaries are
answered by position, and identity is attached afterwards by the application. Nothing a
model writes is ever used as a key. This is why an answer should name an abstraction rather
than quote a code back — the codes exist for the reader.

## What a review is, and what it is not

A review is immutable. It pins the case revision, the atlas version, the policy corpus, the
model and the prompt identity that produced it. Re-running against a changed case creates a
new review; both stay, and neither is edited.

A review speaks only about what it examined. It examined every instance of the three
detectable shapes, so it can be exhaustive about those and is silent about everything else —
coupling, naming, performance, test coverage, and any abstraction with two or more
implementations are all outside what it looked at. Repetition that did not take the form of
a shared constant name, or of a concept name spreading, is also outside it: several bespoke
implementations preparing the same request in parallel is a shape the parser measures but
does not yet raise for judgement.

## What this conversation can answer

The whole review is in front of you every turn, along with the case it was judged against.
There is nothing further to retrieve.

Where the review settles a question, say so and say which boundaries settle it. Where it
does not, say plainly that it does not, rather than reasoning past the evidence: a review
that examined six boundaries cannot speak about a seventh, and the honest answer is that it
was never looked at. Verdicts are not re-litigated here — if a reader disagrees with one,
explain what it rested on and what would have to be different in the case for it to change.
