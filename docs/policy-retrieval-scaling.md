# Advisory — When (and when not) to retrieve policies instead of presenting them all

**Status:** Advisory, nothing implemented. Records an experiment run on 2026-07-29 so the
numbers survive the session that produced them.
**Related:** `application/reviews.py` (the full-corpus judgement decision and its comment),
`adapters/models/prompt_contracts.py` (the positional bearing contract), master plan §12.0.

## The question

Judgement today presents the entire policy corpus to the model once per candidate, and the
response must contain one bearing entry per presented policy, bound by position. Two
pressures invite replacing that with retrieval:

1. **Cost.** The corpus is ~9,700 tokens per judgement call. A top-8 shortlist would be
   ~2,900.
2. **Trust.** The positional contract is validated for *count* (exactly N entries, wrong
   count retries deterministically) but not for *alignment*: an answer about policy 5
   written into slot 6 passes validation and misattributes silently. Retrieval keeps
   selection in deterministic code — cosine and argsort cannot misattribute.

Whether retrieval is *safe* depends on one number: how often the policies that would have
borne on a finding survive into the shortlist.

## The experiment

Ground truth came from the workspace itself: 25 succeeded reviews in
`boundary_reviews.review_json` carry per-candidate `policy_bearings` — what gemma4:26b said
bears when shown all 27 policies. That is 149 judgements, deduplicated to 34 unique
candidates, with majority-vote bearing sets (mean 4.9 policies of 27). Retrieval used
`embeddinggemma` through Ollama; queries were built from the candidate (pattern, summary,
participants, measurements, detection limits), documents from the policy files.

Recall@10 of majority bearings, i.e. the share of policies-that-bear present in a top-10
shortlist:

| approach | R@10 | candidates fully covered @10 |
| --- | --- | --- |
| BM25 (lexical) | 0.52 | 15% |
| embeddings, whole-policy vectors | 0.76 | 27% |
| embeddings, per-`##`-section chunks, max-pooled | 0.76 | 32% |
| + past bearings' *how* texts as extra chunks, + pattern description in query | 0.86 | 47% |
| per-pattern frequency shortlist, leave-one-out, **no embeddings** | **0.94** | **74%** |

Standard retrieval refinements were tried and did **not** help: HyDE, contextual
(intent-prefixed) chunks, dense+BM25 fusion, per-policy score normalisation, single-section
indexes, alternative pooling. Fusing the dense ranking *into* the pattern shortlist made
the shortlist worse (0.92).

Two reference points for reading those numbers. Random ranking scores 0.37 at k=10, so
embeddings genuinely work. And the judge itself is noisy: a single full-corpus run recalls
only 0.90 of the majority bearing set, so the pattern shortlist at 0.94 already sits above
the judge's agreement with itself.

## Why it comes out this way

**"Bears on" is an inference, not a topic.** Embeddings score topical similarity, and a
finding like "VoiceProvider is implemented only by QwenProvider" shares no topic with
"make interfaces somewhat general" — the connection exists only after reasoning about
speculative abstraction. This is why the vocabulary-gap fixes (HyDE, contextual chunks,
hybrid fusion) changed nothing, and why the one helpful refinement was indexing past *how*
texts: a *how* is that inference already written down in finding-language. The
systematically-missed policies were exactly the broad ones — `contain-dependencies`,
`make-interfaces-somewhat-general`, `optimize-locality-of-change`.

**Bearings are pattern-shaped.** Each detector pattern's eight most-frequent policies cover
~90% of all bearing slots for that pattern. Which policies bear is mostly a property of
*what kind of finding this is*, not of the individual candidate — and the kinds are
enumerable because findings come from a fixed detector set.

## Advice for scaling

- **At the current scale (tens of general policies), change nothing.** The corpus fits in
  the prompt, and any shortlist silently discards policies the judge would have used —
  a miss no downstream check can see. If the positional contract's alignment risk is the
  worry, the proportionate fix is inside the present design: require the model to echo each
  policy's id and validate the echo against position in code (a checksum, not a binding —
  identity still resolves by position, so no model-written id enters the record).
  Misalignment then becomes a detectable retry instead of a silent misattribution.

- **When judgement history accumulates, the first shortlist mechanism should be the
  pattern table, not a vector index.** Rank policies by how often they bore on findings of
  the same detector pattern; it is deterministic, inspectable, better than every retriever
  tried, and a median shortlist of 7 policies fully covered the bearing set (p75 = 11).
  Give k headroom — around 12 — rather than tuning it tight.

- **Embeddings earn a place only where history cannot reach**: a newly added user,
  organisation, or repository policy, or a new detector pattern with no judged findings
  yet. Route those through dense retrieval (section chunks, max-pooled, EmbeddingGemma
  task prompts) as a backfill lane alongside the pattern table — or simpler, present
  history-less policies unconditionally until they have bearings of their own.

- **If the corpus ever reaches hundreds of policies**, full presentation stops fitting and
  a first-stage filter becomes unavoidable. Expect the trade to look better than it does
  today — a large corpus contains topically-close policies for a retriever to find — but
  keep the pattern table as the primary lane and treat recall of stored bearings, measured
  exactly as above, as the gate before any cutover: the ground truth regenerates for free
  from `boundary_reviews`.

## Caveats

Thirty-four candidates from synthetic evaluation cases, skewed 23/34 toward
`sole_implementation`, judged by one model whose run-to-run agreement caps how precisely
any of this can be measured. One stored review predates the full corpus (18 policies
presented). The pattern table's advantage is partly structural — only three detector
patterns exist today — which is honest about the present system but will dilute as
detectors multiply. Re-run before acting: the method needs only the workspace database and
an Ollama with `embeddinggemma`.
