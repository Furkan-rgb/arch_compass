import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, MoreVertical, Square, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  Ledger,
  LedgerItem,
  RowStripe,
  VerdictText,
  rowJudging,
  rowName,
  rowProps,
  rowWhere,
  type Stripe,
  ledgerSheet,
} from "@/components/ledger";

import { api } from "../api";
import {
  EmptyState,
  ErrorPanel,
  Loading,
  PageHeader,
  formatDate,
  page,
  shortId,
} from "../components";
import { deletion } from "../review-capabilities";
import type { BoundaryReviewSummary, RepositorySummary } from "../types";

/** True while any listed review is still being produced. */
export function anyRunning(reviews: BoundaryReviewSummary[]) {
  return reviews.some((review) => review.status === "running");
}

/**
 * The verdict family a row's stripe belongs to, or none.
 *
 * The same three-pixel stripe the findings ledger uses, carrying the same meaning: a review
 * that found something to change is revision magenta, one that cleared everything it looked
 * at is field green, and a run with no verdict yet is the neutral rule. It is what makes a
 * column of reviews scannable without reading a word of any of them.
 */
function verdictFamily(review: BoundaryReviewSummary): Stripe {
  if (review.status === "running") return "judging";
  if (review.status !== "succeeded") return "none";
  if (review.boundaries_material > 0) return "material";
  return review.boundaries_reviewed > 0 ? "cleared" : "none";
}

/**
 * What a row amounts to: the verdict split, or how far a run has got.
 *
 * A running review has no verdict to report, so it reports its position instead. Before
 * detection finishes it cannot even do that — the length is genuinely unknown, and a "0 of
 * 0" would read as a sweep that found nothing rather than one that has not finished.
 *
 * A settled verdict is quiet text in its own hue, exactly as in the findings ledger; only
 * the states that are not verdicts at all — cancelled, failed, waiting on a person — wear a
 * chip, because those are the rows a reader is scanning this list for.
 */
export function Outcome({ review }: { review: BoundaryReviewSummary }) {
  if (review.status === "running") {
    return (
      <span className={rowJudging}>
        {review.boundaries_detected === null || review.boundaries_detected === undefined
          ? "sweeping the atlas"
          : `judging ${Math.min(
              review.boundaries_reviewed + 1,
              review.boundaries_detected,
            )} of ${review.boundaries_detected}`}
      </span>
    );
  }
  if (review.status === "awaiting_answers") {
    // The whole reason this status exists. A first pass whose questions nobody has answered
    // used to be stored as succeeded, so it sat in this listing reporting a verdict split —
    // for ever — over verdicts the run itself said it could not settle. It reports what it
    // is instead: unfinished, and unfinished by the reader rather than by the machine.
    return <Badge variant="accent">waiting on your answers</Badge>;
  }
  if (review.status === "cancelled") {
    // Not shown as a failure. A review nobody wanted any more is not a review that broke,
    // and colouring them alike would have the reader looking for a problem.
    return <Badge variant="neutral">cancelled</Badge>;
  }
  if (review.status === "failed") {
    return <Badge variant="material">failed, nothing judged</Badge>;
  }
  if (review.boundaries_material > 0) {
    return (
      <VerdictText verdict="material" tone="sentence">
        {review.boundaries_material} of {review.boundaries_reviewed} should change
      </VerdictText>
    );
  }
  return (
    <VerdictText verdict="cleared" tone="sentence">
      {review.boundaries_reviewed === 0
        ? "no boundaries to examine"
        : `all ${review.boundaries_reviewed} left as they are`}
    </VerdictText>
  );
}

/**
 * What can be done to one row: stop it, or remove it.
 *
 * Outside the row's link rather than inside it. A button nested in an anchor is neither
 * reliably clickable nor announced as its own control, and "delete" is the last action that
 * should depend on a click landing where the reader meant it.
 *
 * The menu itself was hand-built — an absolutely positioned span, a `role="menu"` written by
 * hand, and a focus loop borrowed from the dialog helper. What that spelling never had is
 * what a menu is actually judged on: arrow keys, typeahead, dismissal on a click anywhere
 * else on the page, and the collision handling that keeps the last row's menu from opening
 * off the bottom of the window. Those come with the primitive.
 */
function RowActions({
  review,
  title,
  passCount,
  onCancel,
  onDelete,
  busy,
}: {
  review: BoundaryReviewSummary;
  title: string;
  /** How many passes the row folds. Deleting the row deletes all of them. */
  passCount: number;
  onCancel: () => void;
  onDelete: () => void;
  busy: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  const running = review.status === "running";
  // The same rules module the ask button reads, so the menu refuses exactly what the server
  // refuses. Deleting used to be offered on a running row and answered with a 409 the reader
  // had done nothing to earn.
  const refusal = deletion(review.status);

  return (
    <span data-slot="row-actions" className="flex items-center gap-1 pr-2">
      {running ? (
        <Button
          type="button"
          variant="destructive"
          disabled={busy}
          onClick={onCancel}
        >
          <Square size={13} aria-hidden fill="currentColor" /> Cancel
        </Button>
      ) : null}
      <DropdownMenu
        // The question is asked inside the menu, so a menu that closes has un-asked it. Half
        // a confirmation left standing is the one state this must never reopen into.
        onOpenChange={(next) => {
          if (!next) setConfirming(false);
        }}
      >
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            size="icon"
            aria-label={`More actions for the review of ${title}`}
          >
            <MoreVertical size={16} aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent data-slot="row-menu">
          {refusal ? (
            <Tooltip>
              {/* The span is load-bearing, as on the ask button: a disabled item takes no
                  pointer events, so the reason has to hang off something above it that does.
                  It takes no tab stop, unlike that button's wrapper — the menu owns focus
                  while it is open and Radix skips disabled items on the arrow keys, so there
                  is no stop here to inherit. A reader on the keyboard meets the row's own
                  Cancel button instead, which is what the sentence sends them to. */}
              <TooltipTrigger asChild>
                <span className="block">
                  <DropdownMenuItem variant="destructive" disabled>
                    <Trash2 size={14} aria-hidden /> Delete
                  </DropdownMenuItem>
                </span>
              </TooltipTrigger>
              <TooltipContent>{refusal}</TooltipContent>
            </Tooltip>
          ) : confirming ? (
            <>
              {/* Confirmed in place rather than by a browser dialog: the row being deleted
                  stays visible behind the question, which is the one detail that makes the
                  answer meaningful. */}
              <DropdownMenuLabel data-slot="row-menu-ask">
                {passCount > 1
                  ? `Delete this run? Its ${passCount} passes and their question threads go with it.`
                  : "Delete this review? Its question threads go with it."}
              </DropdownMenuLabel>
              <DropdownMenuItem
                variant="destructive"
                disabled={busy}
                onSelect={onDelete}
              >
                <Trash2 size={14} aria-hidden /> Delete permanently
              </DropdownMenuItem>
              <DropdownMenuItem>Keep it</DropdownMenuItem>
            </>
          ) : (
            <DropdownMenuItem
              variant="destructive"
              // The one item here that does not dismiss the menu: it replaces the menu's
              // contents with the question, and closing would throw away the thing it asked.
              onSelect={(event) => {
                event.preventDefault();
                setConfirming(true);
              }}
            >
              <Trash2 size={14} aria-hidden /> Delete
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </span>
  );
}

/** One run of a review: every pass of it, newest first, worn as a single row. */
export interface ReviewChain {
  /** The latest pass — the one the row links to and reports the outcome of. */
  tip: BoundaryReviewSummary;
  /** All passes, newest first; `passes[0]` is the tip. */
  passes: BoundaryReviewSummary[];
  title: string | null;
}

/**
 * One row per run, not one per pass.
 *
 * A run is a chain of passes linked by `elicited_from` — the first pass asks its questions,
 * the second judges the answered case — and the chain is one piece of work. Listed
 * separately, every finished run showed twice: once as its conclusion and once as a first
 * pass for ever "waiting on your answers" over questions that were answered minutes later.
 * So a pass another review answers folds behind that review, and a first pass stands alone
 * exactly as long as it really is waiting — which is when waiting is the row to show.
 */
export function groupIntoChains(reviews: BoundaryReviewSummary[]): ReviewChain[] {
  const byId = new Map(reviews.map((item) => [item.review_id, item]));
  const answered = new Set(
    reviews.map((item) => item.elicited_from).filter((id): id is string => Boolean(id)),
  );
  // The listing arrives newest first, so the tips keep that order without sorting.
  return reviews
    .filter((item) => !answered.has(item.review_id))
    .map((tip) => {
      const passes: BoundaryReviewSummary[] = [];
      // A pass whose predecessor has been deleted still lists: the walk simply ends where
      // the record does, and the chain is whatever survives.
      for (
        let pass: BoundaryReviewSummary | undefined = tip;
        pass;
        pass = pass.elicited_from ? byId.get(pass.elicited_from) : undefined
      ) {
        passes.push(pass);
      }
      return {
        tip,
        passes,
        // The title comes from whichever pass recorded one. A pass still running has none
        // yet, and the first pass's is a better answer than a placeholder.
        title: passes.find((item) => item.case_title)?.case_title || null,
      };
    });
}

/**
 * A repository's runs, newest first.
 *
 * One flat ledger rather than a sub-section per case: with passes folded, a case is almost
 * always exactly one run, and re-running a bundled example makes a *new* case with the same
 * title — two headings wearing identical words told the reader nothing the rows don't.
 */
export function RunLedger({
  chains,
  onCancel,
  onDelete,
  busy,
}: {
  chains: ReviewChain[];
  onCancel: (reviewId: string) => void;
  onDelete: (reviewIds: string[]) => void;
  busy: boolean;
}) {
  return (
    <section data-slot="run-ledger" className={ledgerSheet}>
      <Ledger>
        {chains.map((chain) => (
          <LedgerItem key={chain.tip.review_id}>
            {/* The hover sits on the wrapper rather than on the row, because the row's
                controls are its siblings: the highlight belongs to the record, not to the
                link that opens it. */}
            <div
              data-slot="review-row"
              className="grid grid-cols-[minmax(0,1fr)_auto] items-center rounded-[var(--row-radius)] hover:bg-sunken"
            >
              <Link
                to={`/reviews/${chain.tip.review_id}`}
                {...rowProps({ kind: "review" })}
                // Named for what it is here: the record is the wrapper above, and this is
                // the one of its two children that opens the review.
                data-slot="review-link"
              >
                <RowStripe verdict={verdictFamily(chain.tip)} />
                <span className={rowName}>
                  {chain.title || <code>{shortId(chain.tip.case_id)}</code>}
                </span>
                <span className={rowWhere}>
                  {"branchName" in chain && (chain as LedgerLine).branchName
                    ? `${(chain as LedgerLine).branchName} · `
                    : ""}
                  {formatDate(chain.tip.created_at)}
                </span>
                {/* The line's depth is worth a word; the revisions themselves live on the
                    page, behind its picker. */}
                {"revisions" in chain && (chain as LedgerLine).revisions > 1 ? (
                  <span className="font-mono text-micro tracking-[.06em] text-ink-3 max-[860px]:hidden">
                    {(chain as LedgerLine).revisions} revisions
                  </span>
                ) : chain.passes.length > 1 ? (
                  <span className="font-mono text-micro tracking-[.06em] text-ink-3 max-[860px]:hidden">
                    {chain.passes.length} passes
                  </span>
                ) : (
                  <span />
                )}
                <Outcome review={chain.tip} />
                <ArrowRight
                  size={13}
                  aria-hidden
                  className="text-ink-3 max-[860px]:hidden"
                />
              </Link>
              <RowActions
                review={chain.tip}
                title={chain.title || chain.tip.review_id}
                passCount={chain.passes.length}
                busy={busy}
                onCancel={() => onCancel(chain.tip.review_id)}
                // The whole run goes, not just the pass on show. A delete that left the
                // first pass behind would resurface it as a row "waiting on your answers"
                // — the exact ghost this listing folds away.
                onDelete={() => onDelete(chain.passes.map((pass) => pass.review_id))}
              />
            </div>
          </LedgerItem>
        ))}
      </Ledger>
    </section>
  );
}

/**
 * The listing's outer shape: one section per repository, cases grouped inside it,
 * newest run first throughout.
 *
 * The repository became the natural container the day reviews learned which one they
 * belong to — a `repo_id` derived from the root commit, so two runs on the same history
 * land in the same section whatever directory it was checked out in. Reviews from before
 * that identity existed carry no `repo_id` and are gathered honestly at the end under
 * their own heading rather than being guessed into a section.
 */
export function groupByRepository(
  reviews: BoundaryReviewSummary[],
  repositories: RepositorySummary[],
) {
  const groups = new Map<string | null, BoundaryReviewSummary[]>();
  for (const review of reviews) {
    const key = review.repo_id ?? null;
    groups.set(key, [...(groups.get(key) || []), review]);
  }
  const sections = [...groups.entries()]
    // The unplaced section reads last: it is history, not the working set.
    .sort(([a], [b]) => Number(a === null) - Number(b === null))
    .map(([repoId, items]) => {
      const indexed = repoId
        ? repositories.find((item) => item.repo_id === repoId)
        : undefined;
      const segments = indexed?.root_path.split("/").filter(Boolean) ?? [];
      const chains = groupIntoChains(items);
      return {
        repoId,
        // The directory's own basename, minus the content hash a managed checkout's
        // folder carries — the person pasted "audiobook_studio", not the digest. The
        // full path stays in the tooltip.
        name: segments.at(-1)?.replace(/-[0-9a-f]{12}$/, "") ?? null,
        segments,
        branchName: indexed?.branch_name ?? null,
        rootPath: indexed?.root_path ?? null,
        chains,
        count: chains.length,
      };
    });
  // Two projects can end in the same folder name — every bundled example's root is a
  // directory literally called "repository". A colliding name grows leftward one segment
  // at a time until it says which project it is; unique names stay short.
  for (let width = 2; width <= 6; width += 1) {
    const counts = new Map<string, number>();
    for (const section of sections) {
      if (section.name) counts.set(section.name, (counts.get(section.name) ?? 0) + 1);
    }
    let widened = false;
    for (const section of sections) {
      if (
        section.name &&
        (counts.get(section.name) ?? 0) > 1 &&
        section.segments.length >= width
      ) {
        section.name = section.segments.slice(-width).join("/");
        widened = true;
      }
    }
    if (!widened) break;
  }
  return sections;
}

/**
 * One row per branch: the branch's line, worn as its newest run.
 *
 * A branch carries one living review, so listing every revision here would repeat the
 * revision picker as clutter — the row is the line's current state, the branch's name
 * rides inside the row, and older revisions are one click away on the page itself.
 */
export type LedgerLine = ReviewChain & {
  branchName: string | null;
  revisions: number;
};

export function foldToLines(
  chains: ReviewChain[],
  branchNames: Map<string, string>,
): LedgerLine[] {
  const byBranch = new Map<string | null, ReviewChain[]>();
  for (const chain of chains) {
    const key = chain.tip.branch_id ?? null;
    byBranch.set(key, [...(byBranch.get(key) || []), chain]);
  }
  return [...byBranch.entries()].map(([branchId, items]) => ({
    ...items[0],
    branchName: (branchId && branchNames.get(branchId)) || null,
    revisions: items.length,
  }));
}

export function ReviewsPage() {
  const client = useQueryClient();
  const reviews = useQuery({
    queryKey: ["reviews"],
    queryFn: () => api.reviews(),
    // Polled only while something is actually running, and stopped the moment nothing is.
    // A run reports through its own request's stream; this page is a second reader with no
    // stream of its own, and one that polled for ever would keep a local model's machine
    // busy answering a question whose answer cannot change.
    refetchInterval: (query) => (anyRunning(query.state.data || []) ? 2000 : false),
  });
  // Names for the repo sections. The listing rows carry only the hashed id; the indexed
  // repositories are what turn it back into a directory a reader recognises.
  const repositories = useQuery({
    queryKey: ["repositories"],
    queryFn: api.repositories,
  });
  // Branch names for the sub-headings. Only consulted when a repository's runs span more
  // than one branch — the common single-branch section stays exactly as it was.
  const branchLineages = useQuery({ queryKey: ["branches"], queryFn: api.branches });
  const branchNames = new Map(
    (branchLineages.data || []).map((item) => [item.branch.branch_id, item.branch.branch_name]),
  );
  const grouped = useMemo(
    () => groupByRepository(reviews.data || [], repositories.data || []),
    [reviews.data, repositories.data],
  );

  const refresh = () => client.invalidateQueries({ queryKey: ["reviews"] });
  const cancel = useMutation({ mutationFn: api.cancelReview, onSuccess: refresh });
  const remove = useMutation({
    // A run's passes go together, one at a time: the server deletes one review per call,
    // and in order, so a failure part-way leaves whole records rather than a torn chain.
    mutationFn: async (reviewIds: string[]) => {
      for (const reviewId of reviewIds) await api.deleteReview(reviewId);
    },
    onSuccess: refresh,
  });
  const busy = cancel.isPending || remove.isPending;
  const runCount = grouped.reduce((total, section) => total + section.count, 0);

  return (
    <div className={page}>
      <PageHeader
        title="Reviews"
        meta={
          reviews.data?.length ? (
            <Badge>
              {runCount} {runCount === 1 ? "run" : "runs"} across {grouped.length}{" "}
              {grouped.length === 1 ? "repository" : "repositories"}
            </Badge>
          ) : undefined
        }
      />
      <p className="m-0 mb-4 max-w-[84ch] text-ui leading-[1.5] text-ink-2">
        Each one is immutable and pinned to the case revision and atlas version it judged,
        so an older review keeps saying what it said.
      </p>

      {reviews.isLoading ? (
        <div className={ledgerSheet}>
          <Loading
            label="Reading reviews…"
            rows={4}
            // The rows this list waits for are ledger rows, so the wait reserves their height.
            className="[&>[data-slot=skeleton-row]]:min-h-[var(--row-h)]"
          />
        </div>
      ) : null}
      {reviews.isError ? (
        <ErrorPanel
          error={reviews.error}
          onRetry={() => void reviews.refetch()}
          retrying={reviews.isFetching}
        />
      ) : null}
      {/* The server's own words. Cancelling a review that has just finished, or deleting
          one still running, are both refusals worth reading rather than paraphrasing.
          Each offers its own second attempt on the review it already named — the mutation
          still holds the id it was called with, so nothing has to be threaded back here. */}
      {cancel.isError ? (
        <ErrorPanel
          error={cancel.error}
          onRetry={
            cancel.variables ? () => cancel.mutate(cancel.variables!) : undefined
          }
          retrying={cancel.isPending}
          retryLabel="Cancel it again"
        />
      ) : null}
      {remove.isError ? (
        <ErrorPanel
          error={remove.error}
          onRetry={
            remove.variables ? () => remove.mutate(remove.variables!) : undefined
          }
          retrying={remove.isPending}
          retryLabel="Delete it again"
        />
      ) : null}
      {reviews.data && reviews.data.length === 0 ? (
        <EmptyState
          title="No reviews yet"
          description="Pick a repository on the start step and run one. A case is optional."
          action={
            <Button asChild variant="primary">
              <Link to="/start">
                Start a review <ArrowRight size={13} aria-hidden />
              </Link>
            </Button>
          }
        />
      ) : null}

      {grouped.map((section) => (
        <section
          key={section.repoId ?? "unplaced"}
          aria-label={section.name ?? "Reviews from before repository identity"}
        >
          {/* The section heading is the repository, worn the way the rows wear their
              facts: the directory's name in the mono face, the branch beside it, and the
              count at the end of the line. Sections from before repo identity say so
              rather than pretending to be one. */}
          <h2 className="mt-6 mb-2 flex flex-wrap items-baseline gap-x-2 text-sub font-[650] text-ink first:mt-0">
            {section.name ? (
              <>
                <code className="font-mono" title={section.rootPath ?? undefined}>
                  {section.name}
                </code>

              </>
            ) : section.repoId ? (
              <code className="font-mono text-meta" title={section.repoId}>
                {shortId(section.repoId)}
              </code>
            ) : (
              <span>Before repository identity</span>
            )}
            <span className="ml-auto text-meta font-normal text-ink-3">
              {section.count} {section.count === 1 ? "run" : "runs"}
            </span>
          </h2>
          <RunLedger
            chains={foldToLines(section.chains, branchNames)}
            busy={busy}
            onCancel={(reviewId) => cancel.mutate(reviewId)}
            onDelete={(reviewIds) => remove.mutate(reviewIds)}
          />
        </section>
      ))}
    </div>
  );
}
