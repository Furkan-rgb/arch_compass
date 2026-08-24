# Retrieval evaluation

Measurement of the policy retriever, kept outside `src/` because it is not part of the
product. The notebook is the report; everything with a right answer lives in `harness/`.

```
retrieval-evaluation.ipynb        the report: runs it, shows it, says what it means
harness/corpus.py                 the shipped policies, read by the workspace's parser
harness/dataset.py                the labelled cases, and the join to detector output
harness/indexes.py                the retriever variants and the two baselines
harness/metrics.py                recall, precision, MRR, MAP, nDCG
harness/runner.py                 running a case set over an index or the retriever
harness/report.py                 tables and charts, so a notebook cell is one line
dataset/candidate-labels.yaml     labels for the candidates the detectors find
dataset/intent-cases.yaml         40 design situations written from the problem
dataset/scoped-policies/          four policies for the mandatory arm
results/                          written by a run, not committed
```

The split is deliberate: nothing in `harness/` decides anything a reader has to take on
trust, and nothing in the notebook does arithmetic. A metric defined in a cell is one
nobody can test and one that quietly changes between runs.

## Why this measures a local model, when the shipped index is OpenRouter's

Deliberate, and worth saying because the two now name different providers.

The retriever is what is under test, not the embedder. Measuring it needs the same function
every time, on demand, without a credit balance or a network — so the harness pins a local
model explicitly (`indexes.ollama_config`) rather than reading whatever a workspace happens
to be configured with. That is what makes a number from last month comparable to one from
today.

The shipped index answers a different question: what a workspace embeds with when nobody has
configured anything, which is the hosted boundary. Both are correct and they are not required
to agree.

One thing does have to hold, and did not: the local model must be the same local model.
`embeddinggemma:latest` is a moving tag, so `indexes.EXPECTED_EMBEDDER_DIGEST` records the
manifest these numbers were measured against and `assert_expected_embedder()` refuses to
measure against another. Ollama can report a digest and cannot be asked to serve one, so it
is an assertion rather than a constraint — enough to turn a silent change of function into a
named failure.

## Running it

Needs Ollama on `localhost:11434` holding `embeddinggemma`:

```
ollama pull embeddinggemma
make evaluation                                      # headless, writes results/ and an HTML report
uv run --group evaluation jupyter lab evaluation/retrieval-evaluation.ipynb
```

No reasoning model is used and no network beyond the local Ollama is reached. A cold run
embeds 486 chunks and takes about a minute; the SQLite index persists in `results/`, so a
second run is faster.

## What it measures, and against what

The corpus is the shipped Markdown in `src/archcompass/policies/general`, read by the
workspace's own parser. A score against a corpus written for the evaluation would say
nothing about the product.

The test set is 68 labelled cases of two kinds.

**28 candidate cases** are not written down. `examples/cases` is parsed by the production
analyser, run through the production detectors, and turned into a query by the production
`retrieval_query`. The YAML holds only relevance labels, joined to the detector output by
participant list, and the join is checked in both directions — an unmatched label and an
unlabelled candidate are both load errors. A detector change fails loudly here rather than
quietly shrinking the test set.

**40 intent cases** are design situations described the way an engineer describes them.
They exist because the detectors know three shapes, so a set built from those alone would
measure the corpus for three questions and say nothing about the other fifty policies. Each
is written in the vocabulary of the problem, not of the policy that answers it.

Labels are graded. `bearing` is what a reviewer would cite in the verdict, and recall is
reported over those alone; `supporting` and `adjacent` let nDCG tell rank 1 from rank 18
without turning a defensible extra into a miss.

## Adding a case

Add an entry to `dataset/intent-cases.yaml` with a `query` and at least one `bearing`
policy. For a candidate case, add the participants of a candidate the detectors already
find — the loader will tell you if they name nothing.

Label from the policy text, never from what a retriever returned. A label written by
reading the output is not a test; it is a transcript.

## Changing the retriever

`harness/indexes.py` holds the variants. Each satisfies `DensePolicyIndex`, so the shipped
`DensePolicyRetriever` drives a lexical baseline or a different chunker without knowing it.
A new one is a class with `synchronize` and `search`, added to the ablation table.

The in-memory index is checked against `SQLitePolicyIndex` on every query before any metric
is read from it, so a divergence between the harness and the product is a failed cell
rather than a wrong number.
