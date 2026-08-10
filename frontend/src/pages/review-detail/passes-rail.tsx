/** The strip of links across the passes of one run, saying what each pass did. */

import { Link } from "react-router-dom";

import type { BoundaryReviewSummary } from "../../types";

/** The word a pass wears in the rail: what it did, or what it is doing. */
function passWord(status: BoundaryReviewSummary["status"]): string {
  if (status === "awaiting_answers") return "asked";
  if (status === "running") return "running";
  if (status === "succeeded") return "judged";
  return status;
}

/**
 * The way between the passes of one run.
 *
 * The listing folds a run to its latest pass, so this rail is where the earlier ones remain
 * reachable — the first pass holds the questions as they were asked, and the second holds
 * what the answers changed. Absent on a run of one pass: a rail with one stop is furniture.
 */
export function PassesRail({
  chain,
  currentId,
}: {
  chain: BoundaryReviewSummary[];
  currentId: string;
}) {
  if (chain.length < 2) return null;
  return (
    <nav
      aria-label="Passes of this run"
      className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-micro"
    >
      <span className="tracking-[.09em] uppercase text-ink-3">Passes</span>
      {chain.map((pass, index) => {
        const label = `${index + 1} · ${passWord(pass.status)}`;
        return pass.review_id === currentId ? (
          <span key={pass.review_id} aria-current="page" className="font-[650] text-ink">
            {label}
          </span>
        ) : (
          <Link
            key={pass.review_id}
            to={`/reviews/${pass.review_id}`}
            className="text-accent-ink"
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
