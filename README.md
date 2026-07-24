# ArchCompass

ArchCompass is a local-first, context-aware software architecture advisor. It combines a
validated architecture case, reusable policies, and—when present—a deterministic structural
atlas of a Python repository. It produces an evidence-checked recommendation, alternatives,
trade-offs, future scenarios, an implementation outline, and an ADR in JSON and Markdown.

ArchCompass never imports or modifies an analysed repository. Repository analysis is optional:
greenfield and brownfield consultations run through the same advisory workflow. Brownfield
evidence is accepted only while its persisted atlas still matches the repository.

## V1 capabilities

- Append-only architecture cases and immutable successful or failed consultation runs in SQLite.
- Immutable Python AST atlases with typed queries, separate metric dimensions, freshness checks,
  and objective obscurity signals.
- Persistent workspace policy sources and section-aware, exact unique-policy retrieval through
  `sqlite-vec`.
- Validated concern clusters and bounded focused packets; the model never receives the complete
  atlas or source tree.
- Configurable Ollama chat and embedding adapters with validated structured outputs.
- Deterministic fake providers for tests and evaluations.
- Classified, claim-supported recommendation prose with one constrained evidence-repair pass.
- A Typer CLI backed by application services, with lossless Markdown and structured JSON reports.
- A loopback-only React workspace with guided cases, live structured progress, evidence inspection,
  report downloads, repository indexing, and policy browsing.
- Schema-v2 outputs with compatibility upgrades for stored schema-v1 cases, runs, and reports.

V1 does not modify code, comment on pull requests, expose a remote or multi-user service,
monitor repositories, perform runtime tracing, or calculate a universal complexity score.

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

The packaged local web workspace can then be launched with:

```bash
uv run archcompass web
```

It binds only to `127.0.0.1`, opens `http://127.0.0.1:8765` by default, and uses the same
workspace, services, SQLite state, reports, model configuration, and safety checks as the CLI.
Use `--no-open` for headless environments or `--port PORT` to select another loopback port.

`init` copies the packaged default configuration to the workspace's `config/models.yaml` and
does not overwrite an existing file. That workspace file (or an explicit `--models-config`
path) owns provider identity, model names, embedding dimensions, timeouts, retrieval limits, and
consultation evidence budgets. The packaged default expects:

```bash
ollama pull gemma4:12b
ollama pull embeddinggemma
```

ArchCompass does not pull models automatically. Before each consultation, preflight builds the
policy index when it is missing and rebuilds it when the policy corpus or embedding configuration
has changed. A matching index is reused without calling the embedding model. Use
`uv run archcompass policies rebuild` only when you explicitly want a new immutable index version.

Additional policy files or directories can be registered persistently:

```bash
uv run archcompass policies sources add /path/to/team-policies
uv run archcompass policies sources list
uv run archcompass policies rebuild
```

`policies rebuild --source PATH` also registers `PATH` before rebuilding. Repository-local
policies are included only for that repository and are not registered globally.

## Quick start

Create a case from one of the evaluation inputs:

```bash
uv run archcompass case create --from eval/cases/audiobook-greenfield/case.yaml
uv run archcompass case show <case-id>
uv run archcompass advise <case-id>
```

For an existing Python repository, the ArchCompass checkout can be the workspace. Run
these commands from this repository and point `TARGET` at the repository to analyse:

```bash
uv run archcompass init
TARGET=/path/to/repository
uv run archcompass repo index "$TARGET"
uv run archcompass atlas summary "$TARGET"
uv run archcompass atlas hotspots "$TARGET" \
  --metric reverse-dependency-reach
uv run archcompass advise <case-id> --repo "$TARGET"
```

With this local workflow, state is stored in the gitignored `.archcompass/` directory and reports
in the gitignored `reports/` directory. The target may be a nested fixture, sibling checkout, or
other external repository. To analyse the ArchCompass checkout itself, use a separate workspace:
the workspace must not equal or sit inside the analysed repository. State and report writers
remain inside that validated workspace and reject traversal and symlink escapes. If repository
contents or its Git commit change after indexing, atlas queries and advice reject the stale
version and direct you to run `repo index` again.

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
- [Local web workspace](docs/web-workspace.md)

## License

Apache-2.0.
