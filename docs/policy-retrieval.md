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

**Against the corpus that ships, lanes 1 and 2 select nothing.** All 54 bundled policies are
`scope: general`, and none is `strength: required` (53 are `guidance`, one `preferred`), so
the shipped behaviour is pure dense top-K and the evaluation numbers measure that. The scoped
and required lanes exist for a workspace that registers its own policy sources — that is what
`ArchitectureCase.policy_context` gates — and they are untested by the bundled corpus.

Queries are deterministically assembled from candidate pattern, summary, participants,
measurements, limitations, and whatever the case has been told — which is the answers a
clarification round recorded, and says "nothing yet" where none have been.

The content-hashed SQLite vector index tracks policy/chunk identity, applicability, content
hash, embedding identity, and vector. When it is being built, changed and new chunks are
embedded and stale chunks removed in the same transaction.

A review does not build it. The shipped index runs with generation off: a chunk it does not
hold raises rather than being embedded on demand, so a corpus the index does not cover is a
refusal before any reasoning is spent rather than a slow first review.

Embedding identity is `provider:model:dimensions`, plus a suffix naming anything else that
changes the vectors a model returns — currently `:task-prompted`, for providers whose API
carries no task type and where the instruction must therefore be prefixed to the text.
`factory.embedding_identity` is its only author, because the index namespaces its chunks by
this string and an index may be reused only where its vectors still compare. A hosted API
carries the distinction on the request itself and needs no suffix.

Reasoning and embedding providers are configured independently. A review is refused before
reasoning expenditure when the configured retriever lacks its embedding provider or index.
The shipped minimum retriever uses K=20, recorded in its `1-k20` provenance version.

## Evaluation gate

The harness evaluates K values 8, 12, 16, and 20 in ascending order and identifies the
smallest configuration satisfying all gates:

- macro bearing recall at least 0.95;
- recall for every candidate pattern at least 0.90;
- complete bearing-set coverage for at least 75% of candidates;
- complete required/applicable scoped inclusion;
- no more than 10% material-verdict divergence against full-corpus reference runs.

Five conditions, and that is all of them — `policies/evaluation.py` is the whole predicate.
Deterministic ordering is a property the retriever has (sorted mandatory, then dense by score
then policy id) and a unit test asserts it, but the gate does not check it.

Full-corpus judgement is the gate's reference oracle. It is *also* what the graph retrieves
whenever the selected reasoning provider is `fake` — `SelectedDensePolicyRetriever.retrieve`
short-circuits to the sorted whole corpus, stamped into real review provenance as
`retriever="full-corpus-test-oracle"`. That is the offline path the test suite runs on, so
the branch is reachable in production code even though no shipped deployment selects it.

This is a release gate, not workspace configuration. A maintainer runs `archcompass
retrieval evaluate --from <recorded-results>.yaml` over a reference run before changing the
release-owned K/version constants. No such file is committed, so the command does not run
from a fresh checkout. End users do not approve a shipped retriever in each workspace.

This is not the only measurement of the retriever, and the two are not separate machines.
[evaluation/README.md](../evaluation/README.md) is the harness: a notebook over labelled
cases reporting recall, MRR, MAP and nDCG against `embeddinggemma`, run with `make
evaluation`. It builds the gate's own `RetrievalExample` rows, calls
`choose_smallest_passing_k` itself, and writes `evaluation/results/evaluation.yaml` — which
is the file the CLI command above reads. The notebook decides whether a strategy is worth
shipping; the gate decides which K ships; and the notebook runs the gate.

## Upgrade path

A future implementation may combine BM25, authored pattern priors, historical bearings,
multiple lanes, quotas, reranking, graph retrieval, or different embeddings. It must return
the same generic result, pass the same evaluation, and require only configuration/wiring
changes. `Candidate`, `Finding`, `ArchitectureJudge`, `Review`, and `workflow/graph.py` stay
unchanged.
