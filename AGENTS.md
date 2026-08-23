# Working on ArchCompass

Rules for coding agents. Short on purpose — [docs/architecture.md](docs/architecture.md) is
where the reasoning lives, and you should read it before any structural change.

## Before you add an abstraction

**State what concrete boundary, policy or lifecycle it owns.** If the answer is "it wraps a
class" or "it makes this testable", it is not a boundary and it should not exist. A protocol
with one implementation can be right — persistence, providers, workflow seams — but only when
it protects something that genuinely varies or must not leak.

Equally: do not delete a boundary because it has one implementation. Implementation count
decides nothing in either direction.

## Structure

- Follow feature ownership: `domain`, `analysis`, `policies`, `reasoning`, `workflow`,
  `persistence`, `repositories`, `presentation`, `ports`. Where a feature has vendor code it
  lives in that feature's own `adapters/` — four of them do; the rest reach nothing vendored.
- **Never create a generic bucket** — no `common.py`, `helpers.py`, `utils.py`, `misc.py`,
  `implementations.py`, `defaults.py`. If a symbol has no obvious owner, that is information
  about the symbol. Only the top-level `adapters/`, `application/` and `boundary/` names are
  enforced by a test; the rest of this rule is on you.
- `ports/` holds only the seams the review graph is sequenced out of. A feature's own
  contracts live in that feature's `ports.py`.
- `domain/` imports the standard library and itself. No Pydantic, no LangChain, no
  LangGraph, no provider SDKs, no other feature. Pydantic validates at boundaries;
  domain concepts use the domain's own types.
- LangGraph owns workflow *execution*. It does not own durable product history — that is
  SQLite, and the two are never the same record.

## The model

- **The application decides what to examine. The model decides what it means.**
- Two surfaces let a model choose what it looks at — the hinge investigation and a review
  conversation — and both are bounded, read-only and fully recorded. A third would need the
  same bargain.
- A model may *name* something the application holds. It may never index into a list the
  application built: an out-of-range ordinal is fatal and an in-range wrong one is recorded
  for ever as correct. Unrecognised names are visibly refused or dropped.
- **Never derive a verdict from prose.** The model chooses the verdict explicitly; the
  application does not parse what the reasoning "sounds like".
- **Do not add a second semantic authority.** `ArchitectureJudge` alone produces `material`,
  `cleared` and `held`. No verifier model, no reconciliation pass, no classifier over the
  judge's output.
- Investigation establishes repository facts. It reaches no verdict, narrows no question.

## Domain distinctions that must not blur

- `Candidate` (what a detector found) / `Finding` (what a judgement made of it) /
  `StandingDecision` (what a team decided about it) are three concepts. A decision is filed
  under branch and candidate so it outlives the finding — and so a team's disposition never
  becomes an input to the next judgement.
- **Investigation observations never become `Finding.evidence`.** Evidence is
  detector-selected. Observations are model-selected and recorded separately, with their own
  provenance.
- **Human answers go into `ArchitectureCase`.** Repository observations do not. The case is
  intent; the atlas is fact.
- Deterministic analysis and model judgement stay separate. Candidate detection never asks a
  model anything.

## Changing things

- Prefer the simplest implementation that preserves the real boundary.
- Do not build a compatibility layer for internal code you can simply update. Do keep
  reading old *stored* records — a review is immutable and somebody will open one.
- Do not keep dead code as documentation of a problem. If the problem is real, fix the
  lifecycle or write it down in [docs/known-defects.md](docs/known-defects.md).
- When you delete a mechanism, delete the comments and documentation that describe it in the
  same commit. Stale prose teaching a removed architecture is the expensive kind of wrong.
- When architecture changes, update the canonical document that owns it.

## Verifying

`make check` — ruff, pyright (strict, `src` only), the Python suite, generated API types, the
frontend suite. Green before every commit.

Gated suites are not in `make check` and will not tell you they are broken:
`make test-ollama`, `make test-google`, `make test-browser`, `make evaluation`. Run the
relevant one when you touch what it covers.

`make examples` is not one of them — those tests already run inside `make check`, because
pytest's default filter deselects only `ollama`, `google` and `browser`.

A test that cannot fail is worse than no test. If you are unsure yours can, break the code
deliberately and watch it fail.
