# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The workspace's primary humans are an **architect or tech lead** reviewing structure in code they largely did not write, steering others' work through policies, and a **developer embedded in a team** whose review output — verdicts, reasoning, ADRs — is read by teammates who never open the workspace themselves. (Confirmed 2026-07-30.) Coding agents consume the same pipeline through typed evidence, but they are not the workspace's audience.

## Product Purpose

ArchCompass is a software architecture advisor. It reviews the boundaries in an existing repository — abstractions, ports, indirections — and decides, one at a time, whether each is earning its place given what the user is actually building. It exists because AI-assisted coding makes producing working code cheap while leaving the harder problem — containing complexity, limiting change amplification — untouched. Success for the product is credible, evidence-backed judgement; success for this codebase is additionally **portfolio-grade craft**: the workspace itself is a demonstration of the standard it advocates. (Confirmed 2026-07-30.)

## Positioning

Verdicts with reasoning, not lint. Three structural detectors cover both directions a boundary can be wrong (indirection hiding nothing; knowledge with no owner; a concept escaped its package), and every candidate is judged by a model against the user's case and the whole policy corpus. "Remove the boundary," "give this knowledge one owner," and "leave it exactly as it is" are all first-class answers — an advisor that only ever recommends change is an advocate, not a judge. Nothing the model writes is used as an identifier.

## Operating Context

Single-user browser workspace, served either locally from the Python package (`archcompass web`, binds 127.0.0.1 only) or as a hosted deployment in restricted mode. No authentication in either case. The current directory is the workspace. The navigation is the flow, behind one front door: Home is a showcase page whose hero verdict card cycles three clearly-labelled specimen verdicts written for the page (it reads nothing from the workspace), Start starts a review (two order-free rails — repository and case — converging on one Run button), Policies is the standing library the judgement reads, Reviews is the standing record it writes. Reviews take minutes and may pause to ask the user clarifying questions mid-run. Bundled examples fill both rails in one click so a fresh workspace can produce a real review immediately.

## Capabilities and Constraints

- One evolving `ArchitectureCase` owns case-specific facts; a deterministic immutable `RepositoryAtlas` owns objective repository structure; a reusable `PolicyCorpus` owns normative guidance; an immutable `Review` records how every verdict was reached, including boundaries examined and cleared.
- Clarification QA pairs are first-class on the case (approved 2026-07-30); answers to a review's questions can move verdicts on a second pass, and the workspace attributes moved verdicts to the user's own answers.
- V1 excludes: autonomous code changes, PR comments, multi-user workspaces, MCP, continuous monitoring, languages other than Python, authentication, and any universal maintainability score.
- Hosting is no longer excluded. The `Dockerfile` sets `ARCHCOMPASS_HOSTED=1` and `.github/workflows/deploy.yml` deploys to Cloud Run on push to `main`; hosted mode restricts which repositories may be reached and meters daily runs and fetches. Authentication is still excluded, which bounds what a hosted deployment may be used for.
- Domain vocabulary in active use: boundary, case, atlas, bearing, ledger, verdict, holding/awaiting answers.

## Brand Commitments

None are binding. The user confirmed (2026-07-30) that the redesign may treat everything as open — the "AC" mark, Instrument Sans, the Porcelain/Onyx material system, and even the rendering of the name. The name **ArchCompass** itself remains the product's name in code and CLI.

## Evidence on Hand

- Bundled example cases + repositories that produce real reviews (loaded from Home).
- Extensive real documentation: README.md, docs/architecture.md, docs/workflow.md, docs/operations.md, docs/charter.md, and the interface documents under docs/.
- No testimonials, customers, or benchmarks exist; future work must not fabricate any.

## Product Principles

1. **Judgement over detection.** Every screen serves a verdict-with-reasoning; the UI never presents a detector hit as a conclusion.
2. **Epistemic honesty is the interface.** Withhold what is likely wrong, attribute what changed to what the user said, never invent data, keep the server's words verbatim.
3. **The navigation is the flow.** Cases and repositories are rails of the start step, not destinations; the revise-and-re-run loop is the product's core motion.
4. **The workspace demonstrates its own standard.** As a portfolio-grade artifact, the frontend's craft is part of the product's claim to architectural judgement.
5. **Single-user and immutable.** One workspace, one origin, reviews as permanent records.

## Accessibility & Inclusion

Keyboard-first operation and screen-reader support are established practice in the incumbent code (live regions, focus management, aria-pressed pickers) and must be preserved or exceeded; contrast should reach WCAG AA everywhere, including the 11px metadata tier where the incumbent falls to 4.4:1.
