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
import {
  Ledger,
  LedgerBar,
  LedgerCount,
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
import type { BoundaryReviewSummary } from "../types";

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
  onCancel,
  onDelete,
  busy,
}: {
  review: BoundaryReviewSummary;
  onCancel: () => void;
  onDelete: () => void;
  busy: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  const running = review.status === "running";

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
            aria-label={`More actions for the review of ${
              review.case_title || review.review_id
            }`}
          >
            <MoreVertical size={16} aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent data-slot="row-menu">
          {confirming ? (
            <>
              {/* Confirmed in place rather than by a browser dialog: the row being deleted
                  stays visible behind the question, which is the one detail that makes the
                  answer meaningful. */}
              <DropdownMenuLabel data-slot="row-menu-ask">
                Delete this review? Its question threads go with it.
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

/**
 * Every review this workspace has run, kept off the start step.
 *
 * Grouped by case rather than listed flat. Revising a case and reviewing again is the loop
 * this tool is built around, so successive runs of one case are one history: read as a
 * flat list they look like unrelated results, and the reader has to reconstruct which of
 * two reviews came after which revision.
 */
export function CaseHistory({
  caseId,
  title,
  reviews,
  onCancel,
  onDelete,
  busy,
}: {
  caseId: string;
  title: string | null;
  reviews: BoundaryReviewSummary[];
  onCancel: (reviewId: string) => void;
  onDelete: (reviewId: string) => void;
  busy: boolean;
}) {
  return (
    <section data-slot="case-history" className={ledgerSheet}>
      <LedgerBar>
        <strong>{title || <code>{shortId(caseId)}</code>}</strong>
        <LedgerCount>
          {reviews.length} {reviews.length === 1 ? "review" : "reviews"}
        </LedgerCount>
      </LedgerBar>
      <Ledger>
        {reviews.map((review, index) => (
          <LedgerItem key={review.review_id}>
            {/* The hover sits on the wrapper rather than on the row, because the row's
                controls are its siblings: the highlight belongs to the record, not to the
                link that opens it. */}
            <div
              data-slot="review-row"
              className="grid grid-cols-[minmax(0,1fr)_auto] items-center rounded-[var(--row-radius)] hover:bg-sunken"
            >
              <Link
                to={`/reviews/${review.review_id}`}
                {...rowProps({ kind: "review" })}
                // Named for what it is here: the record is the wrapper above, and this is
                // the one of its two children that opens the review.
                data-slot="review-link"
              >
                <RowStripe verdict={verdictFamily(review)} />
                <span className={rowName}>{formatDate(review.created_at)}</span>
                {/* Which revision was judged is the fact that separates two reviews of one
                    case. Without it the rows differ only by timestamp, and the reader
                    cannot tell a re-run from a review of a changed case. */}
                <span className={rowWhere}>case rev {review.case_revision}</span>
                {index === 0 && reviews.length > 1 ? (
                  <span className="font-mono text-micro tracking-[.06em] uppercase text-accent-ink max-[860px]:hidden">
                    latest
                  </span>
                ) : (
                  <span />
                )}
                <Outcome review={review} />
                <ArrowRight
                  size={13}
                  aria-hidden
                  className="text-ink-3 max-[860px]:hidden"
                />
              </Link>
              <RowActions
                review={review}
                busy={busy}
                onCancel={() => onCancel(review.review_id)}
                onDelete={() => onDelete(review.review_id)}
              />
            </div>
          </LedgerItem>
        ))}
      </Ledger>
    </section>
  );
}

/** Newest first within a case, and cases ordered by their most recent review. */
export function groupByCase(reviews: BoundaryReviewSummary[]) {
  const groups = new Map<string, BoundaryReviewSummary[]>();
  // The listing already arrives newest first, so insertion order is both the order of the
  // rows inside a group and the order of the groups themselves.
  for (const review of reviews) {
    groups.set(review.case_id, [...(groups.get(review.case_id) || []), review]);
  }
  return [...groups.entries()].map(([caseId, items]) => ({
    caseId,
    // The title comes from the review that recorded it. A review that failed before
    // composing a report has none, and an older row is a better answer than a placeholder.
    title: items.find((item) => item.case_title)?.case_title || null,
    reviews: items,
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
  const grouped = useMemo(() => groupByCase(reviews.data || []), [reviews.data]);

  const refresh = () => client.invalidateQueries({ queryKey: ["reviews"] });
  const cancel = useMutation({ mutationFn: api.cancelReview, onSuccess: refresh });
  const remove = useMutation({ mutationFn: api.deleteReview, onSuccess: refresh });
  const busy = cancel.isPending || remove.isPending;

  return (
    <div className={page}>
      <PageHeader
        title="Reviews"
        meta={
          reviews.data?.length ? (
            <Badge>
              {reviews.data.length} across {grouped.length}{" "}
              {grouped.length === 1 ? "case" : "cases"}
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
      {reviews.isError ? <ErrorPanel error={reviews.error} /> : null}
      {/* The server's own words. Cancelling a review that has just finished, or deleting
          one still running, are both refusals worth reading rather than paraphrasing. */}
      {cancel.isError ? <ErrorPanel error={cancel.error} /> : null}
      {remove.isError ? <ErrorPanel error={remove.error} /> : null}
      {reviews.data && reviews.data.length === 0 ? (
        <EmptyState
          title="No reviews yet"
          description="Pick a repository on the start step and run one. A case is optional."
          action={
            <Button asChild variant="primary">
              <Link to="/">
                Start a review <ArrowRight size={13} aria-hidden />
              </Link>
            </Button>
          }
        />
      ) : null}

      {grouped.map((group) => (
        <CaseHistory
          key={group.caseId}
          caseId={group.caseId}
          title={group.title}
          reviews={group.reviews}
          busy={busy}
          onCancel={(reviewId) => cancel.mutate(reviewId)}
          onDelete={(reviewId) => remove.mutate(reviewId)}
        />
      ))}
    </div>
  );
}
