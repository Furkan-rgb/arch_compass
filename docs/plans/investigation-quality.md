# Plan: investigation quality — evidence before questions

**Status:** Built, uncommitted on `feat/company-readiness`. Every section below is
implemented: §1 usage evidence (ADR 0017, judge prompt v12), §2 persistence with the
"what the review checked before asking" disclosure on the review page, §3 the Ollama tool
transport (its SDK cannot force the first call; the flag degrades to the prompt, stated
in the transport), §4 Gemini thought-signature round-trip via opaque vendor state, §5 the
`acme-shop` fixture with offline shape tests and the evaluation.md reading guide. Verified
end to end on `gemini-3.5-flash-lite` with thinking: six lookups including three
`read_source` calls (a tool that model never used before §1 landed), grounded verdicts,
zero code-answerable questions, transcript persisted. The section texts below are kept as
written — they are the rationale of record for what was built.

Since then, one step past this plan's scope: the two conversation stages investigate too
(`investigate-for-answer` v1, first turn unforced because a chat turn is usually about the
review's own words), gated on the same freshness answer the excerpts take, recorded on the
message and disclosed under the answer. Verified live: asked what the AcmeHub client's
docstring says, the discussion stage searched, read the file and quoted it exactly. All of
it is on `main`.
**The rule:** a question the code can answer must never reach the reader unchecked — and
a verdict the code contradicts must never be the thing that decides which questions exist.
**Scope:** judge evidence, investigation persistence, provider parity, and measurement.
Everything here stays inside the amended §12.0: the application chooses what a *verdict*
rests on; a model may *look* only where every lookup is recorded.

## What the trials established

All findings come from a seeded bench (a small shop backend where one duplicated constant
is provably one fact — both copies feed the same AcmeHub client, whose docstring names the
vendor's five-attempt guidance — one duplicated constant is provably a coincidence, with
comments saying so at each definition, and one sole-implementation boundary is genuinely a
question for a human). Runs used `gemini-3.5-flash-lite` and `gemini-3.6-flash`, thinking
on. Counts are small; directional only.

1. **The asking stage now looks, structurally.** Gemini's function-calling mode ANY on
   the first turn removed "never looked" as a possible outcome. Prompt v1 had made
   looking optional and a small model took the permission literally.
2. **A small model looks badly regardless of prompt.** flash-lite only ever searched,
   never read a file, and kept asking questions its own hits answered. Prompt v2 (the
   first-refusal rule, read-around-hits) did not move it. The prompt has hit its ceiling
   on that model; `gemini-3.6-flash` asked nothing code-answerable.
3. **The real defect is upstream and ours.** The judge's payload is the candidate's
   metadata — names, paths, roles, an agreement flag. It contains **no source text at
   all**: not the definition line, not the comment above it, not one consumer. On the
   bench it confidently called the one-fact duplication "coincidental", and one run
   hallucinated a value the code does not contain. Elicitation cannot repair this: a
   question exists only where a verdict hinges, and a confidently wrong verdict hinges
   on nothing.
4. **Application-chosen usage evidence fixes what prompts could not.** A prototype that
   attaches definition spans (with their leading comments) and consumer spans to the
   judge payload — assembled deterministically, no tools — made flash-lite call the
   coincidence correctly in 3/3 runs, *citing the comments*, where the plain judge
   flipped between runs. Rationales stopped hallucinating. The one-fact duplication
   became a grounded judgement call whose residue is genuine intent ("must these move
   together?") — which is precisely the question elicitation is for, and one run then
   asked exactly it.

The conclusion this plan builds on: **the model was never the main problem; the evidence
was.** Every stage that decided badly was deciding blind.

## 1. Usage evidence on the candidate

The load-bearing change. For each finding candidate, the application attaches how the
flagged code is actually used, as evidence the judge is shown — chosen by the
application, so §12.0 needs no further amendment for it.

- **Consumers become participants.** For a duplicated constant: every module that reads
  each copy; for a sole implementation: every dependant of the abstraction; for a
  scattered concept: the mentioning sites the detector already records. Discovery is
  structural first — the atlas already carries `REFERENCES`, `IMPORTS` and `CALLS` edges
  — with a bounded text search through the one `SourceReader` path as the named fallback
  (and its use recorded as a limitation on the candidate). Each consumer is a
  `FindingParticipant` with a role saying what it consumes, so excerpt pinning, source
  rendering, the conversation stages and `content_fingerprints` all inherit it with no
  new machinery. The fingerprint inheritance is not incidental: **a verdict cached
  against usage is invalidated when usage changes**, which is what verdict reuse should
  have meant all along.
- **Definition excerpts carry their comments.** The prototype's decisive facts sat in
  comment blocks immediately above definitions, which the recorded spans exclude. Widen
  the excerpt for a definition-site participant upward over its contiguous leading
  comment. Deterministic, application-side, and it improves every stage that shows code.
- **Caps.** Consumers per participant (proposal: 5, with the overflow counted in a
  measurement so "5 of 40 shown" is a stated fact); the existing excerpt and budget
  guards already bound the rest. A constant consumed forty times is itself a finding the
  measurement can carry.
- **Contract.** `JUDGE_FINDING_CANDIDATE` bumps to name the new evidence and what it is
  for: the verdict may rest on it, and "the copies are one fact / two facts" must cite
  it. The prompt-identity change correctly invalidates delta comparisons.
- **Record the decision.** An ADR for "a candidate carries its usage", and the
  architecture.md §12.0 section updated to state the split the code now embodies:
  verdict evidence is application-chosen and this widens it; investigation-before-asking
  is model-driven and recorded. (The `review_source.py` docstring already says this;
  the doctrine document should, too.)

## 2. Persist the investigation

The elicitation investigation currently evaporates: the transcript reaches the asking
stage and is gone. Until it is stored, the feature is unauditable and invisible in the
product — indistinguishable from not existing.

- A `investigation` value on the review (or the elicitation round): the recorded
  lookups — tool, arguments, result — plus the `investigate-usage` prompt identity and
  the closing summary. Written when elicitation runs, immutable after.
- API: serve it with the review. UI: a small "what the review checked before asking"
  disclosure on the questions panel — the product's proof that a question was asked
  *because the repository is silent*, not because nobody looked.
- Schema-version bump on the stored review with a tolerant reader for old rows, in the
  house style.

## 3. Ollama parity

The capability protocol exists precisely so a second vendor is one transport away. The
`ollama` SDK supports tools; implement `complete_with_tools` there, including whatever
its API offers for the forced first call (absent a native ANY mode, the loop's forced
turn degrades to the prompt asking — state that in the transport rather than simulating).
Until then, local models silently ask without looking, which is the pre-feature behaviour
but now a parity gap worth naming in the model chooser.

## 4. Gemini thought signatures

The provider-neutral history drops Gemini's thought signatures when replaying tool turns.
The 3-series documents them as part of function-calling state; the current loop works,
but longer investigations on 3.6-flash are where it will first bite. Carry an opaque
vendor-state field on `AssistantToolTurn`, written and read only by the transport that
produced it.

## 5. Measurement, in eval/

Every claim above rests on n≤6 by hand. The bench belongs in `eval/cases` with ground
truth so the next prompt or evidence change is measured, not eyeballed:

- Promote the seeded shop repository to an eval case: expected verdict per boundary
  (one-fact, coincidence, keep-the-seam) and expected question surface (nothing
  code-answerable; the sole-implementation intent question permitted).
- Metrics per run: seeded-verdict accuracy; code-answerable-question rate (a question is
  a failure if the repository states its answer); lookups made; whether `read_source`
  was used when a hit decided something.
- n ≥ 10 per configuration before believing any delta — judge variance between identical
  runs was large enough to imitate feature effects in both directions.
- Quota reality: `gemini-3.6-flash` free tier allows 20 requests/day, which one bench
  run nearly consumes. Eval sweeps run on flash-lite or a paid key; 3.6-flash is spot
  confirmation.

## Why this order

Evidence (§1) comes first because it is the only change that alters what reaches a
reader: it fixes verdicts, and better verdicts change which questions exist at all.
Persistence (§2) follows because it makes the already-built half visible and auditable.
Measurement (§5) lands before parity (§3–4) so that every later change — including the
next prompt bump — is a number, not an anecdote.

## Non-goals

- **Tools for the judge.** The prototype confirms they are unnecessary: application-
  chosen evidence achieved the correction. A judging stage that browses remains
  forbidden, and `test_judging_is_deliberately_given_no_way_to_investigate` stays.
- **Investigation on the second pass or the summary.** The second pass concludes over a
  case the reader just answered; new evidence entering there would bypass every
  judgement that could have weighed it.
- **More tools.** A file listing, symbol index or git log would widen looking into
  browsing; the two tools answered every code-answerable question the bench could pose.
