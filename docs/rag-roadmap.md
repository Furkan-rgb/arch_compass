# ArchCompass RAG Roadmap

## Purpose

This document defines the roadmap for ArchCompass policy retrieval.

The current implementation is intentionally conservative: it retrieves applicable mandatory/scoped policies plus a dense top-K semantic result, then gives the full selected `Policy` objects to `ArchitectureJudge`.

The long-term goal is a stronger hybrid retriever that improves policy recall and ranking quality **without changing the surrounding domain or workflow architecture**.

The stable boundary remains:

```text
Candidate
  +
ArchitectureCase
  +
Policy corpus
        │
        ▼
PolicyRetriever
        │
        ▼
RetrievedPolicySet
        │
        ▼
ArchitectureJudge
```

The graph, `Candidate`, `Finding`, `ArchitectureCase`, and `ArchitectureJudge` must not depend on the internal retrieval strategy.

---

## Current Baseline

The current production retriever is `dense-scoped`.

For each candidate it:

1. Builds a deterministic retrieval query from:
   - candidate pattern
   - candidate summary
   - participants
   - measurements
   - detection limitations
   - architecture goal
   - architecture constraints

2. Always includes applicable:
   - repository policies
   - organisation policies
   - user policies
   - accepted ADR policies
   - required general policies

3. Chunks policy Markdown by `##` headings.

4. Embeds policy chunks using the selected embedding model.

5. Stores content-addressed vectors in SQLite using `sqlite-vec`.

6. Performs dense cosine similarity search.

7. Scores each policy by its best-matching chunk.

8. Selects dense top-K policies, currently K=20.

9. Deterministically merges dense results with mandatory/scoped policies.

10. Persists generic retrieval provenance with the review.

This baseline is deliberately high-recall and simple enough to reason about.

---

# Roadmap

## Phase 1 — Improve the Retrieval Query

### Goal

Make retrieval respond more accurately to the full `ArchitectureCase`, especially after clarification.

### Changes

Extend the deterministic retrieval query to include:

- case decisions
- previous clarification answers
- explicit non-goals
- expected changes where available
- assumptions where available

The query should remain application-generated. The LLM should not invent or rewrite the retrieval query.

Example:

```text
Pattern: sole_implementation
Candidate: PaymentGateway has one implementation
Participants: PaymentGateway, StripePaymentGateway
Measurements: implementations=1
Detection limits: runtime registrations may not be visible

Architecture goal:
Keep payment providers replaceable without unnecessary abstractions.

Constraints:
Must support Stripe today.

Decisions:
Provider-specific code may remain at the infrastructure edge.

Clarifications:
A second payment provider is expected within six months.
```

### Why

A clarification can change which policies are relevant even if the repository candidate has not changed.

### Acceptance criteria

- retrieval query fingerprint changes when materially relevant case context changes
- clarification-triggered rejudgement performs fresh retrieval
- tests prove case decisions and answers influence retrieval input
- no model-generated query text enters the retrieval pipeline

---

## Phase 2 — Add Keyword / BM25 Retrieval

### Goal

Complement semantic similarity with exact terminology matching.

Dense embeddings are good at conceptual similarity but can miss exact architecture vocabulary, identifiers, policy-specific terms, acronyms, and rare phrases.

### Strategy

Add a lexical retrieval lane using BM25 or an equivalent deterministic full-text scorer.

The hybrid candidate pool becomes:

```text
mandatory/scoped policies
        +
dense semantic matches
        +
BM25 / keyword matches
```

Possible implementation choices:

- SQLite FTS5
- a small in-process BM25 implementation
- another storage implementation behind a lexical index port

Prefer SQLite FTS5 if it keeps deployment and persistence simple.

### Query inputs

Reuse the same deterministic retrieval query, but also consider structured lexical terms separately:

- candidate pattern
- participant names
- participant roles
- package/module names
- detector terminology
- case terminology

### Provenance

Record strategy-specific values only as opaque metadata, for example:

```text
selection_reason=lexical
bm25_rank=3
bm25_score=...
```

Do not add BM25 fields to `Policy`, `Finding`, or graph state contracts.

### Acceptance criteria

- dense-only and lexical-only results can be evaluated independently
- lexical retrieval improves recall on terminology-heavy examples
- scoped/required guarantees remain unchanged
- strategy internals remain behind `PolicyRetriever`

---

## Phase 3 — Candidate-Pattern Priors

### Goal

Use known relationships between detector patterns and policies as an additional ranking signal.

Some policies are repeatedly relevant to the same structural patterns.

Examples:

```text
sole_implementation
    → abstraction / interface / extension policies

duplicate_constant
    → ownership / duplicated knowledge policies

concept_leak
    → boundary / dependency / domain ownership policies
```

These relationships should help ranking, but they must not become hard-coded verdict rules.

### Design

Maintain a retriever-owned prior:

```text
candidate pattern
        ↓
historically / authorially associated policy IDs
```

Possible sources:

1. explicitly authored pattern-policy associations
2. curated evaluation data
3. historical confirmed bearings
4. later, statistically learned associations

Initially prefer explicit or evaluation-derived priors over self-reinforcing learned priors.

### Important constraint

A candidate-pattern prior says:

> "This policy is worth retrieving for this kind of candidate."

It does **not** say:

> "This candidate violates this policy."

Judgement remains the model's responsibility.

### Ranking use

Pattern priors can:

- add policies to the candidate pool
- boost rank
- break close dense/lexical ties

They should not bypass applicability rules.

### Acceptance criteria

- prior data is versioned
- prior changes alter retriever identity/version
- pattern priors improve per-pattern recall in evaluation
- no prior produces a `Finding` without `ArchitectureJudge`

---

## Phase 4 — Historical Known Bearings

### Goal

Use ArchCompass's own review history as retrieval memory.

If a policy has repeatedly been relevant to the same candidate lineage or a closely related candidate, retrieval should be able to surface it again.

### Sources

Historical signals may include:

- policies cited in previous findings for the same candidate ID
- policies cited for a deterministic successor candidate
- policies cited when the candidate previously resurfaced
- policies repeatedly associated with the same candidate pattern in the same repository

### Distinction from Standing Decisions

Standing decisions must remain separate.

A human `accept`, `waive`, or `park` decision must not change what the judge believes the architecture means.

Historical retrieval memory may say:

> "This policy was relevant before."

It must not say:

> "The user waived this, therefore do not retrieve it."

### Cold-start behavior

History must only be an enhancement.

A repository with no previous reviews must still work correctly using:

```text
mandatory/scoped
+
dense
+
lexical
+
pattern priors
```

### Avoiding feedback loops

Historical bearings should not become self-confirming evidence.

Recommended safeguards:

- cap historical boost
- combine with independent retrieval signals
- track whether a bearing was model-produced, human-confirmed, or evaluation-curated
- retain full retrieval evaluation against a reference corpus

### Acceptance criteria

- candidate lineage can surface previous policy bearings
- history is optional and repository-local where appropriate
- deleting review history does not break retrieval
- standing decisions do not feed judge input
- historical boosts are visible in provenance metadata

---

## Phase 5 — Hybrid Candidate Pool

### Goal

Build a broad, high-recall policy candidate set before ranking.

At this stage the retrieval pipeline should look like:

```text
                         ┌────────────────────┐
                         │ mandatory / scoped │
                         └─────────┬──────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
        ▼                          ▼                          ▼
 dense section score        BM25 / lexical           candidate-pattern
                                                      prior policies
        │                          │                          │
        └──────────────────────────┼──────────────────────────┘
                                   │
                                   ▼
                         historical bearings
                                   │
                                   ▼
                         deterministic dedupe
                                   │
                                   ▼
                         high-recall candidate pool
```

### Candidate pool size

The pool may be larger than the final judge context.

For example:

```text
mandatory/scoped     unlimited
dense                 top 20
lexical               top 20
pattern prior         top 12
history               top 12
```

These numbers are starting points, not permanent constants.

The evaluation harness should determine safe limits.

### Deduplication

Deduplicate by policy ID while preserving all contributing retrieval reasons.

Example provenance:

```text
policy: boundary-ownership

reasons:
- dense rank 4
- BM25 rank 2
- pattern prior
- historical bearing
```

The retriever may use multiple signals internally while still returning one `PolicySelection`.

---

## Phase 6 — Reranking

### Goal

Improve precision after high-recall retrieval.

The first-stage retriever should optimize for **not missing relevant policies**.

A reranker can then decide which of those policies deserve the limited context budget sent to the judge.

Pipeline:

```text
high-recall candidate pool
          │
          ▼
       reranker
          │
          ▼
final selected policies
          │
          ▼
ArchitectureJudge
```

### Reranker options

Evaluate in this order.

#### 1. Deterministic weighted fusion

Combine normalized signals:

```text
dense score
lexical score
pattern prior
historical bearing
scope / required guarantees
```

Advantages:

- cheap
- deterministic
- easy to audit
- easy to test

This should be the first reranker.

#### 2. Reciprocal Rank Fusion

Use RRF across retrieval lanes.

Example:

```text
score(policy) =
    1 / (k + dense_rank)
  + 1 / (k + bm25_rank)
  + 1 / (k + prior_rank)
  + 1 / (k + history_rank)
```

Advantages:

- robust across incomparable raw score scales
- simple
- does not require training

#### 3. Embedding cross-encoder / reranking model

A dedicated reranking model may later score:

```text
candidate + case
against
policy
```

Only add this if evaluation shows a meaningful gain.

#### 4. LLM reranker

Use an LLM reranker only if cheaper deterministic/model-based reranking is insufficient.

If introduced:

- it must only rank application-owned policy IDs/positions
- it must not generate policy identity
- it must not make the architecture verdict
- its cost and latency must be separately measurable

### Acceptance criteria

- reranking improves precision without violating recall gates
- mandatory/scoped policies cannot be removed
- reranker output is deterministic where the chosen implementation permits
- reranker identity/version is persisted in provenance

---

## Phase 7 — Context Budgeting

### Goal

Control how much policy content reaches `ArchitectureJudge`.

The current implementation restores the full selected `Policy` after chunk-level retrieval.

That is safe and simple, but may become expensive as policies become larger.

### Possible future strategy

For each selected policy, retain:

- full policy identity and metadata
- the best-matching section(s)
- optionally the policy introduction
- optionally a deterministic surrounding section window

Then decide whether the judge receives:

```text
A. full policy
B. selected sections
C. selected sections + compact policy summary
```

### Important constraint

Do not prematurely optimize this.

Full policies are preferable while corpus size and context budget remain manageable.

Section-only judgement introduces the risk of hiding exceptions or qualifications elsewhere in the policy.

### Acceptance criteria before moving away from full policies

- evaluation shows context size is materially problematic
- section-level input does not increase verdict regression beyond the allowed threshold
- cited policy identity always resolves to the original full policy
- audit UI can show exactly what text the judge received

---

## Phase 8 — Better Policy Chunking

### Goal

Improve semantic units used by dense and lexical retrieval.

The current H2-based chunking is intentionally simple.

Potential improvements:

- preserve heading hierarchy
- include heading path in embedded text
- detect very large sections and split them further
- keep examples/code blocks attached to their explanatory section
- preserve policy introduction as context for child sections
- add metadata such as section heading and ordinal

Example:

```text
Policy: Keep domain code framework-free
Section path: Rationale > Portability

<chunk text>
```

### Constraints

Chunking changes must:

- alter index/content identity
- trigger re-embedding only where necessary
- remain deterministic
- preserve the ability to reconstruct the source policy/section

---

## Phase 9 — Retrieval Evaluation Dataset

### Goal

Turn RAG development into an evidence-driven process rather than manual tuning.

The evaluation set should contain real ArchCompass candidates with known relevant policy bearings.

Each example should capture:

```text
candidate pattern
candidate context
architecture case context
expected relevant policy IDs
required/scoped policy IDs
reference full-corpus verdict where available
```

### Dataset sources

Use a mix of:

- curated synthetic examples
- existing evaluation repositories
- real review cases with human-reviewed bearings
- regression cases from retrieval failures

Avoid using only examples produced by the current retriever, because that would bias evaluation toward the current strategy.

### Required metrics

Retain the existing gates:

- macro policy recall >= 0.95
- recall per candidate pattern >= 0.90
- required/scoped inclusion = 1.00
- full expected bearing-set coverage >= 0.75
- material-verdict regression <= 0.10

Add:

- mean selected policy count
- p95 selected policy count
- retrieval latency
- embedding calls per review
- reranker latency/cost if applicable
- precision@K
- MRR / nDCG where useful

### Release rule

A more complex retriever should only replace the current implementation if it improves evaluation results or substantially reduces context/cost while preserving the gates.

Complexity by itself is not progress.

---

## Phase 10 — Retriever Versioning and Reproducibility

### Goal

Make every review explainable later.

Persist enough provenance to reconstruct the retrieval decision.

Stable provenance should include:

```text
retriever implementation
retriever version
corpus fingerprint
selected policy IDs
embedding identity, if used
query fingerprint
```

Opaque implementation metadata may include:

```text
dense rank / score
BM25 rank / score
pattern-prior contribution
historical-bearing contribution
reranker score
reranker identity
chunk IDs
```

### Do not promote these to domain invariants

Fields such as:

```text
dense_score
bm25_score
lane
prior_score
reranker_score
```

must remain optional strategy metadata.

The graph and domain must not require them.

---

# Target Hybrid Architecture

The intended mature retrieval pipeline is:

```text
Candidate + ArchitectureCase
            │
            ▼
 deterministic query/context builder
            │
            ├───────────────────────────────┐
            │                               │
            ▼                               ▼
     dense section search             lexical / BM25
            │                               │
            ├──────────────┬────────────────┘
            │              │
            ▼              ▼
   candidate-pattern     historical
        priors           known bearings
            │              │
            └───────┬──────┘
                    ▼
            candidate policy pool
                    │
                    ▼
          deterministic applicability
             and mandatory guarantees
                    │
                    ▼
                 reranker
                    │
                    ▼
           final policy selection
                    │
                    ▼
           RetrievedPolicySet
                    │
                    ▼
           ArchitectureJudge
                    │
                    ▼
                 Finding
```

---

# Recommended Implementation Order

Implement in this order:

1. **Enrich the deterministic retrieval query**
   - decisions
   - clarification answers
   - other case facets

2. **Add lexical/BM25 retrieval**
   - preferably SQLite FTS5

3. **Add candidate-pattern priors**

4. **Add historical known bearings**

5. **Create unified hybrid candidate-pool logic**

6. **Add deterministic fusion / RRF reranking**

7. **Expand retrieval evaluation and regression coverage**

8. **Only then evaluate learned/model-based reranking**

9. **Only optimize full-policy context if context size becomes a demonstrated problem**

This order keeps each improvement independently measurable.

---

# Non-Goals

The RAG roadmap does **not** turn ArchCompass into an autonomous repository agent.

The retriever must not:

- decide which repository files to inspect
- create candidates
- invent application identity
- make architecture verdicts
- interpret standing decisions as architecture truth
- mutate the `ArchitectureCase`
- control LangGraph routing

Those responsibilities remain elsewhere in ArchCompass.

---

# Architectural Invariants

The following should remain true throughout the roadmap.

## 1. Retrieval is replaceable

A different `PolicyRetriever` implementation should not require changes to:

- `workflow/graph.py`
- `Candidate`
- `ArchitectureCase`
- `Finding`
- `ArchitectureJudge`

except composition/configuration wiring where necessary.

## 2. Candidate detection remains deterministic

The application decides what architectural structures deserve review.

Retrieval only decides which policies should be available when judging those structures.

## 3. The model does not own identity

Any model-assisted ranking must refer to application-owned positions or IDs that ArchCompass resolves itself.

## 4. Mandatory policy guarantees are deterministic

Applicable required/scoped policies must never depend on semantic ranking.

## 5. Retrieval provenance remains auditable

Every review should explain which policies were available to the judge and why.

## 6. History informs retrieval, not truth

Historical policy bearings may improve recall, but do not replace fresh judgement.

## 7. Standing decisions remain separate

Human disposition such as accepted, waived, or parked findings must not suppress or alter policy retrieval semantics.

---

# Definition of Done for the Mature Retriever

The RAG system can be considered mature when:

- retrieval combines semantic, lexical, pattern, and historical signals
- mandatory/scoped policy coverage remains deterministic and complete
- reranking is evaluation-backed
- clarification answers materially influence retrieval
- retrieval works with both Google and Ollama embedding providers
- changing embedding models creates isolated index namespaces
- unchanged policy content is not unnecessarily re-embedded
- every selected policy has auditable provenance
- retrieval quality is covered by a representative regression dataset
- a future retrieval implementation can replace the current one without a domain or workflow redesign

At that point the stable architectural story remains simple:

```text
ArchCompass determines what architectural structure needs judgement.
PolicyRetriever determines which guidance is relevant.
ArchitectureJudge determines what that guidance means for the candidate.
```
