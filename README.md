# ArchCompass

ArchCompass is a local-first, context-aware software architecture advisor. It combines a
validated architecture case, reusable policies, and—when present—a deterministic structural
atlas of a Python repository. It produces an evidence-checked recommendation, alternatives,
trade-offs, future scenarios, an implementation outline, and an ADR in JSON and Markdown.

ArchCompass never imports or modifies an analysed repository. Repository analysis is optional:
greenfield and brownfield consultations run through the same advisory workflow.

## V1 capabilities

- Append-only architecture cases and immutable consultation runs in SQLite.
- Versioned Python AST repository atlases with nodes, edges, separate metric dimensions, and
  objective obscurity signals.
- Section-aware Markdown policy indexing and retrieval through `sqlite-vec`.
- Bounded progressive atlas queries; the model never receives the full source tree.
- Configurable Ollama chat and embedding adapters with validated structured outputs.
- Deterministic fake providers for tests and evaluations.
- Evidence validation with one constrained repair attempt.
- Typer CLI with Markdown and JSON reports.

V1 does not modify code, comment on pull requests, expose a web UI, monitor repositories,
perform runtime tracing, or calculate a universal complexity score.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A SQLite build that supports loadable extensions
- Optional: a local Ollama service for real consultations

On macOS, use a Python distribution whose SQLite supports loadable extensions, such as
Homebrew Python.

## Setup

```bash
uv sync --locked
uv run archcompass init
```

The repository's `config/models.yaml` is the single source for provider identity, model names,
embedding dimensions, timeouts, and consultation limits. The default expects:

```bash
ollama pull gemma4:12b
ollama pull embeddinggemma
```

ArchCompass does not pull models automatically. Before each consultation, preflight builds the
policy index when it is missing and rebuilds it when the policy corpus or embedding configuration
has changed. A matching index is reused without calling the embedding model. Use
`uv run archcompass policies rebuild` only when you explicitly want a new immutable index version.

## Quick start

Create a case from one of the evaluation inputs:

```bash
uv run archcompass case create --from eval/cases/audiobook-greenfield/case.yaml
uv run archcompass case show <case-id>
uv run archcompass advise <case-id>
```

For an existing Python repository:

```bash
uv run archcompass repo index /path/to/repository
uv run archcompass atlas summary /path/to/repository
uv run archcompass atlas hotspots /path/to/repository \
  --metric reverse-dependency-reach
uv run archcompass advise <case-id> --repo /path/to/repository
```

Reports are printed and saved as `reports/<run-id>.md` and `reports/<run-id>.json`.
Use `--json` to print structured output.

## Development

```bash
make check
make eval
make test-ollama
make full
make build
```

`make check` runs the fast deterministic suite and never requires a live model.
`make test-ollama` checks the configured embedding model and runs a complete consultation
against the configured reasoning model. `make full` runs linting, strict type checking, all
deterministic tests, the live Ollama suite, and the package build.

## Documentation

- [Product definition](docs/product-design.md)
- [Architecture and dependency direction](docs/architecture.md)
- [Domain model](docs/domain-model.md)
- [Repository atlas](docs/repository-atlas.md)
- [Atlas metrics](docs/atlas-metrics.md)
- [Policy format](docs/policy-format.md)
- [Advisory workflow](docs/advisory-workflow.md)
- [Persistence model](docs/persistence-model.md)
- [Report contract](docs/report-contract.md)
- [Evaluation methodology](docs/evaluation.md)

## License

Apache-2.0.
