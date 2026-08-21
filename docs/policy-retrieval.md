# Policy retrieval

`PolicyRetriever` is the stable application capability for policy selection. The domain,
judge, and graph do not depend on a retrieval algorithm.

```python
class PolicyRetriever(Protocol):
    def retrieve(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        corpus: tuple[Policy, ...],
    ) -> RetrievedPolicySet: ...
```

`RetrievedPolicySet` contains ordered `PolicySelection` values and generic
`RetrievalProvenance`. Stable audit data includes retriever/version, corpus fingerprint,
selected policy IDs, optional embedding/model identity, query fingerprint, and opaque
metadata. Consumers do not require fields such as `dense_score`, `prior_score`, `lane`, or
`reranker_score`.

## Initial retriever

The initial `dense-scoped` implementation:

1. includes applicable non-general policies;
2. includes applicable required policies;
3. retrieves dense top-K results from Markdown-heading chunks;
4. deduplicates by policy ID;
5. orders mandatory/scoped selections first, then dense results deterministically.

Queries are deterministically assembled from candidate pattern, summary, participants,
measurements, limitations, and whatever the case has been told — which is the answers a
clarification round recorded, and says "nothing yet" where none have been.

The content-hashed SQLite vector index tracks policy/chunk identity, applicability, content
hash, embedding identity, and vector. Changed/new chunks are embedded and stale chunks are
removed in the same transaction.

Embedding identity is `provider:model:dimensions`, plus a suffix naming anything else that
changes the vectors a model returns — currently `:task-prompted`, for providers whose API
carries no task type and where the instruction must therefore be prefixed to the text.
`factory.embedding_identity` is its only author, because the index namespaces its chunks by
this string and an index may be reused only where its vectors still compare. Google sends
the equivalent as a `task_type` on the request and needs no suffix.

Reasoning and embedding providers are configured independently. A review is refused before
reasoning expenditure when the configured retriever lacks its embedding provider or index.
The shipped minimum retriever uses K=20, recorded in its `1-k20` provenance version.

## Evaluation gate

The harness evaluates K values 8, 12, 16, and 20 in ascending order and identifies the
smallest configuration satisfying all gates:

- macro bearing recall at least 0.95;
- recall for every candidate pattern at least 0.90;
- complete required/applicable scoped inclusion;
- complete bearing-set coverage for at least 75% of candidates;
- no more than 10% material-verdict regression against full-corpus reference runs;
- deterministic ordering for identical inputs and retriever identity.

Full-corpus judgement is an evaluation oracle, never a production graph branch.

This is a release gate, not workspace configuration. Maintainers run `archcompass retrieval
evaluate --from evaluation.yaml` before changing the release-owned K/version constants.
End users do not approve a shipped retriever in each workspace.

## Upgrade path

A future implementation may combine BM25, authored pattern priors, historical bearings,
multiple lanes, quotas, reranking, graph retrieval, or different embeddings. It must return
the same generic result, pass the same evaluation, and require only configuration/wiring
changes. `Candidate`, `Finding`, `ArchitectureJudge`, `Review`, and `workflow/graph.py` stay
unchanged.
