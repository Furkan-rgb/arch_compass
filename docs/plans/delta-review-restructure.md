# The delta-review restructure

Implements the decisions in `docs/architecture.md` ("Under discussion", 2026-08-05, all
three rounds). This plan is binding on sequencing and surface; the architecture doc is
binding on meaning. Nothing here re-litigates a decision — where mechanics force a choice
the doc doesn't make, the choice is recorded here.

## The target, in one paragraph

Repository → branch → one living review. The branch owns the case (the backbone, iterated
through questions) and the standings (accept / waive / park — the memory; the baseline
object dies). A new revision re-analyses the code and judges only the delta: a boundary
whose inputs — shape fingerprint, participants' content fingerprint, policy corpus, case
revision, model, prompt — are unchanged carries silently; a changed or new boundary is
judged and only it may earn a question. Shape moves are followed by succession matching
(auto-carry with a visible mark); disappearances close the line as `addressed`, loudly,
with resurrection when a fingerprint returns. Needs-attention = material + undecided,
read through to the base branch; CI blocks on exactly that.

## Phase A — the line and the delta (backend, Opus agent, branch `wA-delta-engine`)

1. **Fold in `w1-case-continuity`** (merge it first), then adapt: continuity is per
   **branch**, not per repo — the newest case reviewed on this `branch_id`; `start_clean`
   opt-out survives.
2. **Content fingerprint**: a boundary's participants' source spans, hashed — derived
   from the atlas at detection time and stored on the reviewed boundary. The inputs
   identity of a boundary = shape fp + content fp + corpus fp + case revision + model +
   prompt.
3. **Verdict cache** keys on the inputs identity (new key prefix; old rows go cold, no
   migration of cache contents). `case_id` leaves the key — the branch's case lineage
   replaces it (continuity makes revision meaningful across runs).
4. **Delta partition** in `ReviewService`, per run, against the branch's previous
   revision: `carried` (inputs unchanged — no model call) · `judged` (new shape, or
   content/case/corpus/model moved) · `succeeded` (shape moved, matched: same pattern +
   majority participant overlap) · `addressed` (no match — line closed). Elicitation runs
   only over the judged subset. The partition is stored on the review, not joined later.
5. **Migration 029** — `boundary_lines` (branch_id, fingerprint, event, review_id,
   details): the append-only ledger of successions, addressed closures, resurrections.
   Resurrection is a lookup consequence (standings are never deleted) plus an event row.
6. Tests: rename carries standing with mark; internal rewrite with stable names is
   re-judged (the content-dimension gap test); vanished boundary closes as addressed;
   reappearing fingerprint resurfaces its standing and thread; unchanged repo re-run =
   zero model calls, zero questions.

## Phase B — standings as the memory, read-through, CI (backend, Opus agent, after A)

1. **Migration 030** — `branch_lineages.base_branch_id` (nullable). Default: the repo's
   default branch's lineage.
2. Standing and case lookups read through branch → base chain; a branch's own record
   always wins.
3. **Bulk decide**: one endpoint taking many fingerprints and one decision, author
   required — replaces bulk baselining.
4. **Retire the baseline**: endpoints, `BaselineService` wiring, and `baseline_summary`
   leave the web surface; `branch_baselines` (027) goes dormant, not migrated.
   `ReviewDetailResponse` carries the partition summary instead.
5. CI blocks on material + undecided (through read-through) and speaks the partition
   (attention / quiet / succeeded / addressed) in its comment.

## Phase C — frontend (main session, after A and B)

Repositories-first navigation: a repositories surface; a repository page with branch
dropdown, revision picker (`latest` tag), **New revision** button (managed checkouts
refresh first), the partition as the page's headline, standings UI carried over, bulk
decide, BaselineBar removed, carried-row restyle. `/reviews` demotes to history or goes.

## Ownership and merge order

A and B are sequential (both live in reviews/app/persistence). The main session merges
each phase branch after gates: `uv run pytest -q`, `uv run ruff check .`,
`make typecheck`, `make api-types`, `pnpm run check`. Migration numbers are pre-assigned
above; nobody renumbers.
