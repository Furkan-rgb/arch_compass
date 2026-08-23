# Three design questions — ArchCompass hinge investigation

Self-contained brief for a second opinion. You do not need the codebase.

## What the system is

ArchCompass reviews a software repository's architecture. A deterministic analyser builds an
**atlas** (a graph of the repo: modules, classes, functions, and the imports/calls/implements
edges between them) and picks **candidates** — structural patterns worth judging, e.g. "this
interface has exactly one implementation". A language model then judges each candidate against
a corpus of ~54 authored architecture policies and returns a verdict: `material`, `cleared`,
or `held`.

`held` means the model cannot decide without a fact the code does not carry — typically
intent. It emits a **hinge**: the question it would need answered. A hinge normally stops the
review and asks a person.

Before interrupting a person, a **hinge investigation** runs: the model is given a small
toolbox over the atlas and up to 6 turns to find out whether the interruption is warranted.

## Invariants that constrain any answer

These are fixed and an answer that breaks one is not usable:

1. **"The application decides what to look at. The model decides what it means. Nothing the
   model writes is ever used as a key."** In practice: a model may *name* a thing the
   application holds, but may never return an ordinal/index into a list the application built.
   An unrecognised name must either visibly fail or be dropped — never silently resolve to
   something else.
2. **Verdict evidence is application-chosen.** The detector picks the source spans, the
   application reads them, and nothing the model asked to see is pinned as `Finding.evidence`.
3. **Every lookup is recorded** — tool name, arguments, and the result — because an
   unverifiable finding is not acceptable.
4. The reasoning layer may read source only from the **immutable git revision that produced
   the atlas**, never the live working tree.
5. Orchestration is LangGraph; tool-calling is LangChain's `create_agent` + `StructuredTool` +
   `ModelCallLimitMiddleware`. Prefer library machinery over hand-written loops.

## The toolbox today

Five tools. Four of the five take `node_id`, an opaque atlas handle like
`node_75abb475658e0ce374ac60cd`:

| tool | arguments |
|---|---|
| `find_code` | `name` (free text) |
| `describe_code` | `node_id` |
| `related_code` | `node_id`, `kind` ∈ {direct_dependencies, direct_dependants, known_callers, implementations, related_tests} |
| `read_code` | `node_id` |
| `flagged_signals` | `codes` (optional) |

Node ids appear only in `find_code` output. So every investigation must begin with a
`find_code` call to convert a name it already knows into a handle.

## Evidence from one instrumented run

Local model (Qwen3 27B, no thinking), a 6-candidate repository. n=1 per case — treat as
illustrative, not measured.

**Observation A — the id round-trip is expensive.** In a follow-up conversation about a
finished review, the model made 33 lookups. The **first six all failed**: it passed
`candidate_<hex>` ids (the ids the prompt shows it, because findings are addressed that way)
to tools wanting `node_<hex>` ids. Each returned `Unknown atlas node ID: candidate_b5e4…`.
It recovered by calling `find_code`, but ran out of turns and produced no closing statement.

*(Note: no invariant was broken here — every bad id was visibly rejected, none silently
resolved. It is a cost, not a correctness failure.)*

**Observation B — 2 of 3 hinge investigations ran out of budget.** One hit the 6-turn limit
after 12 lookups and stayed unresolved; one hit a result-size ceiling. The one that finished
inside budget (7 lookups) produced a genuinely good result: it found a test double
implementing the same protocol, read the consumer, and correctly cleared the finding as a
legitimate testing boundary.

**Observation C — a self-contradicting verdict.** One investigation returned
`material: true` alongside reasoning arguing the exact opposite in every sentence:

> "The 'sole_implementation' pattern does not hold in a meaningful sense… The boundary is
> deliberate… The policy 'Delay abstractions until variation is credible' **is not violated**…
> 'Contain volatile dependencies behind a narrow boundary' **is satisfied**."

The output schema is:

```python
class HingeResolutionOutput(BaseModel):
    findings: str              # what the lookups established, required
    material: bool | None      # the verdict, or None if the lookups support none
    reasoning: str | None      # why, empty exactly when there is no verdict
    recommended_response: str | None = None
    hinge: str | None = None   # a narrower question, if the lookups changed what is unknown
```

`material` and `reasoning` are independent fields, so no JSON schema can make them agree.
A cross-field validator has been rewritten three times and each version was defeated by the
model finding a new incoherent shape. **This pass is never shown the policies** — its prompt
contains no policy text at all — yet its `material` boolean is written straight onto the
`Finding`, overwriting the verdict that the judge produced *with* the policies in front of it.

---

## Question 1 — should the tools take qualified names instead of node ids?

Proposal: replace `node_id` with `qualified_name` (e.g. `ports.TaskStore`,
`adapters.SqliteTaskStore.save`) in `describe_code`, `related_code` and `read_code`. The model
already has these names — they are in the finding it is investigating — so the mandatory
`find_code` round-trip disappears.

Measured uniqueness of `qualified_name` across four real atlases (1,670 nodes in the largest):

| node kind | count | colliding names |
|---|---|---|
| class | 370 | 0 |
| function | 432 | 0 |
| method | 662 | 0 |
| interface | 49 | 0 |
| module/package | — | 18 collisions, **all** a package and its own `__init__.py` |

Asking:

- Is this sound, or is there a failure mode being missed? (Consider: atlas rebuilt between
  review and conversation; two checkouts; renamed symbols; dynamically generated names.)
- How should the package/`__init__.py` ambiguity be handled — return both and say so, prefer
  one by node kind, or require a disambiguator?
- Does the reject message matter as much as it seems? Proposal is to replace
  `Unknown atlas node ID: X` with something naming the recovery step, the way the same
  toolbox already does for a bad relation kind ("There is no relationship called 'foo'. The
  relationships this repository can be asked about are …").
- Should `find_code` survive at all once names are the key, or become a search-only fallback?

## Question 2 — what should the turn limit be?

Currently 6 model calls per investigation, enforced by LangChain's `ModelCallLimitMiddleware`
with `exit_behavior="end"` (conclude with what you have, rather than raise). The stated
rationale: "enough for a find, two relations and a read."

Asking:

- If Question 1 removes the mandatory `find_code`, does 6 become adequate, or is the number
  wrong independently of the round-trip?
- Is a fixed model-call cap even the right instrument? Alternatives: a budget in *lookups*
  rather than turns; a token budget; an adaptive stop ("you have N calls left" told to the
  model); no cap plus a wall-clock timeout.
- The run that exceeded the cap produced *no closing statement at all*. Is that acceptable
  behaviour for a truncated investigation, or should the last turn always be reserved for a
  conclusion?

## Question 3 — establish facts, then let the judge judge

Proposed fundamental fix for Observation C: **the investigation stops producing a verdict.**

- `HingeResolutionOutput` keeps only `findings` (what was established) and optional `hinge`
  (a narrowed question). `material`, `reasoning` and `recommended_response` are deleted,
  along with the cross-field validator and the derived `resolved` property.
- The investigated finding keeps or narrows its hinge, and is routed back through the same
  re-judgement path the graph *already has* for when a person answers a question — because
  an investigation and an answer are the same kind of event: a new fact about a held finding.
- The judge then decides, once, with the policies in front of it.

Asking:

- **Is there a tension with invariant 2?** The judge would now see text describing lookups the
  *model* chose. Is it enough to pass this as a separate, labelled input (e.g. "what was
  looked up") while `Finding.evidence` stays strictly detector-chosen — or does model-chosen
  material reaching the judge's prompt at all undermine the rule?
- Should the judge receive the **raw recorded lookups** (tool, arguments, verbatim result) or
  the model's **prose summary** of them? Raw is more faithful and auditable; prose is far
  smaller and the raw transcript can be large.
- Cost: this adds one judge call per investigated hinge. Could the tool loop's own closing
  message serve as `findings`, removing the separate structured call — noting it is empty when
  the loop ends on the turn ceiling?
- Is there a **better** decomposition than the one proposed? The goal is fewer concepts, not
  more — the current design's flaw is two places minting a verdict under two contracts.

## What a useful answer looks like

Pick the questions where you have something substantive. For each: the recommendation, the
reasoning, and — most usefully — the failure mode being guarded against. Say plainly where
the proposal above is already right; disagreement is more valuable than confirmation, but
manufactured disagreement is not.
