# Product definition

## Goal

ArchCompass helps a developer or coding agent choose software structure using requirements,
constraints, future plans, architectural policies, and optional repository evidence. It supports
greenfield and brownfield decisions through one pipeline; the atlas is an optional context source,
not a separate product.

A successful consultation gives a decision summary, confirmed context, assumptions, design
forces, repository observations, policy guidance, responsibility allocation, conceptual
interfaces, credible alternatives, scenario analysis, blast-radius implications, trade-offs,
an implementation sequence, confidence, reversal conditions, revisit triggers, an ADR, and an
evidence appendix.

“No architectural change is justified,” “keep the behavior local,” and “gather more information”
are valid outcomes.

## Audience

- Developers making a new architectural decision.
- Maintainers locating misplaced responsibility in a Python repository.
- Coding agents that need bounded, typed structural evidence.
- Teams applying reusable policies without treating them as automatic lint rules.

## Product principles

- One evolving `ArchitectureCase` owns case-specific facts.
- A deterministic, immutable `RepositoryAtlas` owns objective repository structure and is rejected
  when its repository identity becomes stale.
- A reusable `PolicyCorpus` and persistent workspace source registry own normative guidance.
- An immutable successful or failed `ConsultationRun` records how one recommendation was produced.
- Important claims identify their classification and evidence; substantive conclusions cite
  supporting claim IDs.
- Local complication may contain system-wide complexity; metrics remain separate.

## V1 non-goals

V1 excludes fine-tuning, autonomous code changes, PR comments, remote or multi-user hosting,
MCP, continuous monitoring, languages other than Python, runtime tracing, Git co-change
analysis, whole-program data flow, organisation accounts, authentication, cloud deployment,
automatic principle enforcement, and any universal maintainability or complexity score.

Interfaces are narrow enough to permit later adapters, but V1 contains no unused extension
platform.
