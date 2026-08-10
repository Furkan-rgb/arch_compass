/** The branch and revision this page is showing, with the control that appends the next one. */

import { ChevronDown, GitBranch, Play } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import { formatDate } from "../../components";
import { groupIntoChains } from "../ReviewsPage";
import type {
  BoundaryReviewSummary,
  RepositoryBranch,
  ReviewDetail,
} from "../../types";

/**
 * The branch and the revision this page is showing, and the way to make the next one.
 *
 * The repository model made visible where the reader stands: a branch carries one living
 * review, each run is a revision on its line, and this strip says which line and which
 * point. The button appends to the line — re-analyse the code, judge what changed, ask
 * only about that — which is why it lives here and not on the start step: a next revision
 * is something done *to this branch*, not a fresh errand.
 *
 * It does not always append. The run itself refuses a revision that would change nothing —
 * a repository nothing has touched since this revision earns a floating notice saying so,
 * from the run's own holder, rather than a second revision repeating the first: the line is
 * a history of what happened to the code, not of who pressed what.
 *
 * A picker with one option renders as a plain label: a control that opens a menu of the
 * thing already on screen is furniture.
 */
export function RevisionStrip({
  review,
  currentId,
  reviews,
  branches,
  onNewRevision,
  starting,
  startError,
}: {
  review: ReviewDetail;
  currentId: string;
  reviews: BoundaryReviewSummary[];
  branches: RepositoryBranch[];
  onNewRevision: () => void;
  starting: boolean;
  startError: Error | null;
}) {
  const navigate = useNavigate();
  const branchId = review.branch_id ?? null;
  const repoId = review.repo_id ?? null;
  if (!branchId) return null;

  const chains = groupIntoChains(reviews.filter((item) => item.branch_id === branchId));
  const position = chains.findIndex((chain) =>
    chain.passes.some((pass) => pass.review_id === currentId),
  );
  // Branches of this repository that have a line to show. A branch with no reviews has
  // no page to land on, so it is not offered rather than offered and refused.
  const linesOn = new Set(
    reviews.filter((item) => item.repo_id === repoId).map((item) => item.branch_id),
  );
  const branchOptions = branches.filter(
    (item) => item.branch.repo_id === repoId && linesOn.has(item.branch.branch_id),
  );
  const branchName = branches.find((item) => item.branch.branch_id === branchId)?.branch
    .branch_name;

  const staticLabel = "inline-flex items-center gap-1.5 font-mono text-meta text-ink-2";
  const openBranch = (targetBranchId: string) => {
    const tip = groupIntoChains(
      reviews.filter((item) => item.branch_id === targetBranchId),
    )[0]?.tip;
    if (tip) navigate(`/reviews/${tip.review_id}`);
  };

  return (
    <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-2">
      {branchName ? (
        branchOptions.length > 1 ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" aria-label={`Branch ${branchName} — switch branch`}>
                <GitBranch size={13} aria-hidden /> {branchName}
                <ChevronDown size={13} aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              {branchOptions.map((option) => (
                <DropdownMenuItem
                  key={option.branch.branch_id}
                  disabled={option.branch.branch_id === branchId}
                  onSelect={() => openBranch(option.branch.branch_id)}
                >
                  {option.branch.branch_name}
                  {option.branch.branch_id === branchId ? " — viewing" : ""}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <span className={staticLabel}>
            <GitBranch size={13} aria-hidden /> {branchName}
          </span>
        )
      ) : null}
      {position !== -1 ? (
        chains.length > 1 ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                aria-label={`Revision ${chains.length - position} of ${chains.length} — switch revision`}
              >
                Revision {chains.length - position}
                {position === 0 ? (
                  <span className="text-micro tracking-[.06em] uppercase text-accent-ink">
                    latest
                  </span>
                ) : null}
                <ChevronDown size={13} aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              {chains.map((chain, index) => (
                <DropdownMenuItem
                  key={chain.tip.review_id}
                  disabled={index === position}
                  onSelect={() => navigate(`/reviews/${chain.tip.review_id}`)}
                >
                  Revision {chains.length - index} · {formatDate(chain.tip.created_at)}
                  {index === 0 ? " · latest" : ""}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <span className={staticLabel}>Revision {chains.length - position}</span>
        )
      ) : null}
      <span className="ml-auto" />
      <Button
        type="button"
        disabled={starting}
        onClick={onNewRevision}
        title="Re-analyse the code and judge what changed. Unchanged boundaries carry; only what moved can be asked about."
      >
        {starting ? <Spinner /> : <Play size={13} aria-hidden />}{" "}
        {starting ? "Starting…" : "New revision"}
      </Button>
      {startError ? (
        <p role="alert" className="m-0 w-full text-meta text-material">
          {startError.message}
        </p>
      ) : null}
    </div>
  );
}
