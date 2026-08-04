# Plan: company readiness — identity, incremental runs, triage

**Status:** Proposed. Nothing in this plan is built.
**Scope:** The features that make ArchCompass demonstrable to a real team: durable
repository/branch identity, verdict reuse, baseline semantics, per-boundary triage with
discussion, and a CI/PR mode. Auth, multi-user hosting, languages beyond Python, cost
controls, and procurement-grade data-handling are named at the end and deliberately
deferred — they make the product *buyable*, not *demonstrable*.

## Why this order

The demo that sells the product is a loop, not a screen: run a review, waive one verdict
with a reason, change the code, open a PR — and the PR comment shows only the one boundary
that changed, with the waived one silent and attributed. Every feature below exists to
make that loop real. The dependency chain is strict: identity → verdict fingerprint →
baseline → triage → incremental CI. Building any later stage first means rebuilding it
when the identity model lands.

## 1. Repository and branch identity

Today `repository_identity = stable_id("repo", canonical_root)`
(`adapters/analysis/ast_analyzer.py`). Two clones of the same repo are two strangers; the
same clone moved to a new directory is a new repo. That is the wrong identity for
everything this plan builds.

**Proposed model:**

- `repo_id` — durable identity of the repository itself, independent of where it is
  checked out. Derivation, in preference order: the SHA of the root commit (first commit
  of the default branch — stable across clones, forks excepted), falling back to the
  hash of the canonical path for non-git directories. Never the remote URL alone: remotes
  get renamed, and a repo can have several.
- `branch_id` — a lineage under one `repo_id`, keyed by `(repo_id, branch_name)`. Runs,
  baselines, and standing decisions attach to a branch lineage; the atlas version keeps
  its `git_commit_sha` as the point-in-time pin it already is.
- The existing path-derived identity remains as a *checkout location*, not an identity.
  A migration maps existing rows: each old `repository_identity` becomes one `repo_id`
  with a single implicit branch (the branch present at migration time, else `main`).

Decisions live at the branch level, not the run level, because that is where humans think:
"on main, this boundary is accepted." A PR branch inherits its base branch's decisions and
baseline (see §3) rather than starting blank.

**Non-goal:** tracking branch renames or force-pushed history. A renamed branch is a new
lineage; the old one goes stale and can be pruned.

## 2. Verdict identity and reuse

Incremental anything requires answering "is this the same boundary as last time?" without
asking the model. The product already refuses model-authored identifiers, which makes this
tractable: a boundary's identity comes from the atlas, deterministically.

- **Boundary fingerprint:** a stable hash over the structural facts that define the
  candidate — detector kind, the participating symbols' qualified names, and the edge set
  the detector matched on. Not file paths alone (files move), not line numbers (they churn
  under every edit), not any model output.
- **Verdict cache:** keyed by `(boundary_fingerprint, policy_corpus_fingerprint,
  case_revision, model_descriptor)`. On a re-run, an unchanged key reuses the stored
  verdict verbatim — same words, same evidence — and the review marks it as carried
  forward. Only changed or new boundaries reach the model.

This buys three things at once: re-runs cost a fraction of a full run, they finish in
seconds instead of minutes, and — most important for trust — an unchanged boundary can
never flip its verdict between runs. Verdict flapping on unchanged code would kill CI
credibility faster than any missing feature; the cache makes it structurally impossible
rather than statistically unlikely.

**Open question:** how much symbol renaming should the fingerprint survive? V1 answer:
none. A renamed port is a re-judged port. Cheap re-judgement (this section) makes that
acceptable; fuzzy matching is a later refinement with real failure modes.

## 3. Baseline and the ratchet

A team adopting on a legacy repo gets a first run with dozens or hundreds of boundaries.
If every subsequent run re-presents all of them, nobody looks at run two. The baseline is
the mechanism that makes run two quieter than run one.

- A **baseline** is a branch-level set of boundary fingerprints marked *known*: the
  team has seen them and either accepted the verdict, waived it, or explicitly parked it.
  Adopting a repo is one action: "baseline everything in this review."
- A subsequent run partitions its boundaries into **new**, **changed** (fingerprint
  survives but the verdict moved — possible when the case or policies changed), and
  **known**. The review surface leads with new and changed; known boundaries collapse
  into a single quiet section rather than disappearing — epistemic honesty applies to
  silence too, and "42 known boundaries unchanged" is a claim the user can expand and
  audit.
- The ratchet: a baseline only shrinks when a boundary genuinely disappears from the
  atlas. Removing something from the baseline to re-surface it is a triage action (§4),
  not an edit of history.

## 4. Per-boundary triage and discussion

Reviews are immutable records and stay that way. Triage is a **standing decision** — a
new domain object attached to `(branch_id, boundary_fingerprint)`, not to any single run:

- **States:** `accepted` (we agree, and intend to act or have acted), `waived` (we
  disagree or accept the debt; carries a mandatory reason), `parked` (seen, undecided).
  Absence of a decision is its own state: *unreviewed*.
- Every decision carries a free-text author name, a timestamp, and a reason. No auth
  yet — the name field is honest about being self-reported, and the schema is exactly
  what an authenticated identity drops into later. Designing the object now and the
  login later is the point of deferring auth.
- **Discussion** is an append-only thread of comments under the same key, so a teammate
  can argue with a waiver before it hardens. Same append-only discipline as the existing
  `report_conversation_messages` tables; no edits, no deletes.
- The next run *displays* standing decisions on their boundaries ("waived by Deniz,
  2026-08-02: intentional seam for the billing split") but never lets them touch the
  verdict itself. The model judges; the team disposes. A waived boundary with a changed
  fingerprint re-surfaces as changed — the waiver names a specific structural state, not
  a region of the codebase.

This section is the product's answer to "an advisor that only ever recommends change is
an advocate": the team's recorded disagreement is a first-class outcome, displayed with
the same prominence as the verdict it disputes.

## 5. Non-interactive mode and the CI/PR run

Reviews may pause mid-run to ask clarifying questions. CI cannot answer. The CI mode's
contract:

- Carry forward the case's existing QA pairs (they are first-class on the case already).
- A boundary whose judgement would need a new answer is reported as **holding** — the
  existing vocabulary — and is non-blocking. The question itself goes into the output so
  a human can answer it in the workspace, which is also the funnel back into the product.
- Exit code semantics: nonzero only for *new* boundaries with adverse verdicts that are
  neither baselined nor waived. Everything else is information, not failure. Teams must
  be able to start with the check as non-blocking and ratchet it to blocking later.

The PR surface, in order of build:

1. `archcompass ci` — headless run against the checkout, diff-scoped: only boundaries
   whose fingerprint is new or changed relative to the base branch's baseline are
   reported. Output: human-readable summary plus a JSON report.
2. A GitHub Action wrapping it, posting one sticky PR comment (edited in place on each
   push, never a comment per run). The comment carries verdict + reasoning excerpt per
   boundary and a deep link into the workspace for triage and discussion.
3. PR-branch runs read the base branch's baseline and decisions but write their own
   lineage; merging the PR is the natural moment its accepted decisions fold into the
   base branch. V1 keeps this manual ("adopt decisions from merged branch"), automation
   comes later.

**Constraint carried from the product principles:** the PR comment quotes the server's
words verbatim and attributes carried-forward verdicts as cached. No summarising
paraphrase that could drift from what the review actually said.

## 6. The demo script this enables

1. Open the workspace on the example repo, run a full review. Boundaries land; baseline
   everything in one action.
2. Waive one verdict with a written reason; accept another. Show the discussion thread.
3. Make a small structural change on a branch; open a PR. The Action posts one comment:
   one new boundary, one changed, forty-one known and silent, the waived one silent with
   its waiver named.
4. Answer a holding boundary's question in the workspace; re-run; the verdict moves and
   the workspace attributes the movement to the answer — the existing second-pass
   behaviour, now visible in the team loop.

Each stage of the dependency chain is independently demoable; the plan does not require
finishing everything before showing anything.

## Deferred, deliberately

- **Auth and multi-user hosting.** The triage schema (§4) is designed so identity slots
  in without migration pain. Until then: self-reported names, single shared workspace.
- **Languages beyond Python.** The largest adoption blocker for real companies, and the
  most expensive item on the board — the detectors and atlas are where the cost lives.
  Nothing in this plan makes it harder; the fingerprint and identity model are
  language-agnostic by construction.
- **Cost controls, quotas, spend visibility.** Partially started in the provider
  registry redesign; becomes urgent with CI-triggered runs, so §5's Action ships with a
  crude per-run cap from day one and the real controls come with hosting.
- **Data-handling story** (BYO-key, no-retention, on-prem via Ollama), **notifications**,
  **MCP**, **continuous monitoring**: all post-demo.
