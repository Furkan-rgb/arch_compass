# ArchCompass

ArchCompass is an evidence-grounded software architecture advisor. It analyses a Python
repository deterministically, finds the structural shapes that deserve architectural
judgement, puts each one to a model against the policies that bear on it, asks a person when
the answer turns on something the code cannot say, and keeps the result as an immutable
review history.

It is not a linter, a code generator, or an autonomous repository agent. **A candidate is not
a violation.** ArchCompass assembles the evidence; the model judges what it means; people
decide what to do about the finding.

## The one idea

> The application decides what to examine. The model decides what it means. Nothing the model
> writes is ever used as a key.

Deterministic analysis owns identity, structure, delta, retrieval and provenance. The model
owns the verdict and its reasoning. The person owns the disposition — which is why `Finding`
(what ArchCompass concluded) and `StandingDecision` (what the team decided) are separate
records, and why a decision never edits a judgement.

```text
RepositoryRef -> RepositoryAtlas -> Candidate
                                      |
ArchitectureCase ---------------------+
                                      |
PolicyRetriever -> selected Policies -+
                                      v
                              ArchitectureJudge
                                      |
                                      v
                                   Finding
                                      |
                           clarification needed?
                              /              \
                     Question -> Answer       no
                              |                |
                    ArchitectureCase           v
                       revision             Review ------> next ReviewDelta
                                               |
                                               v
                                       StandingDecision
                                     (filed under branch
                                       and candidate)
```

`StandingDecision` hangs off to the side deliberately. The delta never reads one — a team's
disposition is not an input to the next judgement — and it is filed under branch and
candidate so it outlives the finding that raised it.

LangGraph owns workflow orchestration. LangChain supplies model and retrieval infrastructure.
ArchCompass owns the domain — stdlib dataclasses, no vendor types, no persistence records.

Full picture: **[docs/architecture.md](docs/architecture.md)**. How a review executes,
node by node: **[docs/workflow.md](docs/workflow.md)**.

## Install and run

Requires Python 3.12, `uv`, Node.js and `pnpm`.

```bash
uv sync --locked
cd frontend && pnpm install --frozen-lockfile && cd ..
make run
```

`make run` builds the frontend, serves it on loopback and opens a browser. The Models screen
asks for **two** independent choices — which model judges and which model embeds — and a
review needs a policy index built for the embedding one. The index that ships was built with
Google's `gemini-embedding-2` at 3,072 dimensions; any other embedder needs
`scripts/build_policy_index.py` run for it first.

Pin a reasoning model for a single run instead:

```bash
uv run archcompass --provider google --model gemini-3.5-flash-lite web
uv run archcompass --provider ollama --model qwen3.8:27b web
```

Google, Ollama, Groq and Cerebras are supported for judging; only Google and Ollama serve
embeddings, so a run judging on Groq or Cerebras still embeds through one of those two. Everything about running it — the CLI,
the frontend loop, every environment variable, every limit — is in
**[docs/operations.md](docs/operations.md)**.

## What it does deterministically

Repository, branch, commit and content identity. Parsing, without ever importing or executing
the reviewed repository. The atlas and its relationships, metrics and signals. Candidate
detection and stable ids. Bounded source excerpts, widened to a definition's leading comment
and captioned when truncated. Review deltas, succession, resurfacing. Which candidates and
which policies are put to a model. Provenance and immutable snapshots.

## What the model does

Judges one application-selected candidate against one application-selected policy set — and
after the first review, only the changed and the new candidates are put to it at all; a
finding for an unchanged candidate is carried out of the previous review.

It says which of `material`, `cleared` and `held` it is — a word it chooses, never one the
application reads out of its prose. Explains the verdict and which policies it bears on.
Proposes clarification questions through a validated structured response.

And, for a finding whose verdict turns on a fact — a *hinge* — it may put bounded, recorded,
read-only questions to the repository before anyone is interrupted: structure from the atlas
the review judged, and source read out of the commit that atlas recorded rather than out of
whatever is checked out now. (Where there is no revision to read, it falls back to the
working tree, and only after a check that the tree still is what was judged.) That pass
establishes facts and reaches no verdict. What it found goes back to the same
judge, and every lookup it made is kept on the review and shown beneath the finding.

The model never chooses which candidates are reviewed, and never owns an identifier, a
fingerprint, a persistence key or a standing decision.

## Verify

```bash
make check
```

The frontend build, generated API types, Ruff, Pyright, the offline pytest suite, the
frontend suite, and a check that the shipped policy index still covers the corpus beside it.

The live suites are separate and are the end-to-end ones. Both drive a whole review over the
HTTP API against real services — a repository indexed, every candidate judged, a question
answered, the review resumed on the same graph thread, a decision recorded and a grounded
follow-up asked — and both skip with a message rather than failing when the machine cannot
serve them.

```bash
make test-google    # judges on Google, embeds on a local Ollama — two vendors, one review
make test-ollama    # both halves on this machine, and two further reviews of the same repo
make test-browser
```

`make test-google` is the sharpest demonstration that the reasoning and embedding selections
are independent: they are not even the same vendor. `make test-ollama` is the deployment
somebody evaluating ArchCompass on their own source actually gets, and it goes two steps
further because there is no metered quota to ration — it asks for a second review of the
unchanged repository, which should be refused rather than charged for, then changes the
repository and asks again.

## Documentation

Four documents own the system, and everything else links to them rather than restating them.

- **[Architecture](docs/architecture.md)** — the concepts, the package tree, the dependency
  direction, and which boundaries exist for a reason. Read this before any structural change.
- **[Review workflow](docs/workflow.md)** — the execution graph, the clarification round, the
  hinge investigation, checkpoints versus immutable reviews.
- **[Operations](docs/operations.md)** — running it, every supported environment variable,
  provider behaviour, and what happens at each limit.
- **[Charter](docs/charter.md)** — what ArchCompass is for, and the rules that settle a design
  argument about it.

Focused depth:

- [Policy retrieval](docs/policy-retrieval.md) — the retrieval contract and the shipped strategy
- [Known defects](docs/known-defects.md) — what is understood to be broken, and the evidence
- [AGENTS.md](AGENTS.md) — the short rules a coding agent should follow

The interface has its own four: [the design system](docs/design-system.md),
[the experience](docs/experience.md), [frontend regions](docs/frontend-regions.md) and
[the landing page](docs/landing-page.md).

Licensed under Apache-2.0.
