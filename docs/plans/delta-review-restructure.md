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

### Phase B, as built — the choices the doc did not make

Five, recorded here because mechanics forced them and the architecture doc is silent:

1. **The default branch is the name, not a lookup.** A branch lineage's base is set to
   `DEFAULT_BRANCH_NAME` (`main`) when both lineages exist, resolved lazily on every index
   rather than only at creation, so "index main first" and "index the feature branch first"
   reach the same place. `origin/HEAD` was rejected: it is a local cache of a remote's
   opinion, absent from most clones and from every checkout with no remote, and attaching a
   team's inheritance to the wrong branch is worse than attaching it to none. A team on
   `trunk` or `develop` therefore inherits nothing until a branch's base is something a
   person can state.
2. **Parking silences.** `needs_attention = material AND no standing decision` is taken
   literally, so accepted, waived *and* parked all make a boundary quiet — decision 4's own
   list. This reverses the old CI rule, where parked still blocked.
3. **The standing lookup follows a succession.** A boundary reads its own fingerprint first
   and then the fingerprint it `succeeds`. Without it, renaming a participant would re-open a
   decided boundary, and "the standing carries across" would be recorded and never applied.
4. **A succeeded boundary never blocks**, for the same reason a carried one does not: the
   rename is not what this change introduced, and the succession lookup above is what stops
   that being a way to dodge the check.
5. **The case reads through, the delta does not.** A branch inherits its base's case (the
   backbone — re-asking answered questions is the failure continuity exists to prevent) and
   never its line of revisions. `test_two_branches_of_one_repository_are_two_lines` was
   written in Phase A asserting the opposite about the case and is updated here.

Also: the CI document is `schema_version: 2`. `new`/`changed`/`known` and `baseline_size`
were not renamed, they stopped being true.

## Phase C — frontend (main session, after A and B)

Repositories-first navigation: a repositories surface; a repository page with branch
dropdown, revision picker (`latest` tag), **New revision** button (managed checkouts
refresh first), the partition as the page's headline, standings UI carried over, bulk
decide, BaselineBar removed, carried-row restyle. `/reviews` demotes to history or goes.

### Phase C, 2026-08-05 — a revision that would change nothing is reported, not recorded

**New revision** always runs the check. When nothing would move — the same boundaries, every
one of them carrying (shape fp + content fp + corpus + case + model + prompt all unchanged),
none appearing, vanishing, succeeding or resurfacing — **no case revision and no review are
created**. The client is told "nothing changed since revision N" and shows a quiet notice. A
real delta proceeds exactly as before.

The check is the run's own first decision, taken early: re-index, resolve the branch's
would-be case *without creating one*, detect, and partition against the branch's latest
revision. All of it is deterministic and local, so the answer is exact and costs no model
call. `POST /api/repositories/preflight` {root_path} → {changed, current_against, judged,
addressed, resurfaced, succeeded}. A branch with no prior review answers `changed: true`,
`current_against: null` — a first revision is real by definition.

Three choices the decision did not make:

1. **The revision *number* stays client-side.** The response names the review the repository
   is current against and not its position on the line; the page already computes "Revision
   n" from the listing, and a second numbering computed server-side could disagree with the
   one on screen.
2. **Re-indexing still writes an atlas.** It is how the check knows what the code says now,
   and it is a derived artefact of the code rather than a statement about the review. What is
   read-only is everything the review path owns: no case revision, no review row, no
   `boundary_lines` event.
3. **A previous revision left `awaiting_answers` is not special-cased.** The rule is taken
   literally, so pressing New revision over untouched code on a held branch now reports
   "nothing changed" where it used to produce a concluding pass. Answering the questions is
   the flow that moves that branch; if skipping them is meant to stay possible it needs its
   own gesture rather than a side effect of this button.

## Ownership and merge order

A and B are sequential (both live in reviews/app/persistence). The main session merges
each phase branch after gates: `uv run pytest -q`, `uv run ruff check .`,
`make typecheck`, `make api-types`, `pnpm run check`. Migration numbers are pre-assigned
above; nobody renumbers.
