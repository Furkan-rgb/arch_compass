/** The facts band under the verdict count: what was judged, against what, and when. */

import { formatDate, shortId } from "../../components";
import { deltaFact } from "../../delta";
import { contingentCount } from "../../review-awaiting";
import type { BandFact } from "../../review-ledger";
import type { RunState } from "../../run-progress";
import type {
  BoundaryReviewSummary,
  RepositorySummary,
  ReviewDetail,
  ReviewedBoundary,
} from "../../types";

/** A run's length, in the units a reader counts model calls in. */
export function formatDuration(seconds: number | undefined): string | null {
  if (!seconds || seconds <= 0) return null;
  // A run that took less than a second still took some time, and "0s" reads as a bug.
  if (seconds < 1) return "<1s";
  const whole = Math.round(seconds);
  if (whole < 60) return `${whole}s`;
  return `${Math.floor(whole / 60)}m ${String(whole % 60).padStart(2, "0")}s`;
}

/**
 * The band's facts in the order they are read, which depends on where the run got to.
 *
 * A running review can say how far it has got and nothing about duration; a held one says
 * what it could not settle for itself; a concluded one says what the revision was and how
 * long it took. One list rather than three, because the first several facts are the same
 * in all three cases.
 */
export function verdictFacts({
  review,
  summary,
  indexedAtlas,
  repositoryRoot,
  reviewed,
  report,
  policyCount,
  progress,
  running,
  holding,
}: {
  review: ReviewDetail | undefined;
  /** The listing entry, which is where a finished run's end time lives. */
  summary: BoundaryReviewSummary | undefined;
  /** The indexed repository this review's atlas version belongs to, where it is still known. */
  indexedAtlas: RepositorySummary | undefined;
  repositoryRoot: string | null;
  reviewed: ReviewedBoundary[];
  report: ReviewDetail["report"] | null;
  policyCount: number;
  progress: RunState;
  running: boolean;
  holding: boolean;
}): BandFact[] {
  const atlasVersionId = review?.atlas_version_id;
  // The directory's own name, with the branch beside it: what a reader calls the repo,
  // where the atlas id below is what the workspace calls one snapshot of it.
  const repositoryName = repositoryRoot?.split("/").filter(Boolean).pop() ?? null;
  const facts: BandFact[] = [
    ...(repositoryName
      ? [
          {
            label: "Repository",
            value: `${repositoryName}${
              indexedAtlas?.branch_name ? ` · ${indexedAtlas.branch_name}` : ""
            }`,
            title: repositoryRoot ?? undefined,
          },
        ]
      : []),
    {
      label: "Atlas",
      value: `${shortId(atlasVersionId || "—")}${indexedAtlas ? " · indexed" : ""}`,
      title: atlasVersionId,
    },
    ...(report ? [{ label: "Policies", value: `${policyCount} weighed` }] : []),
    {
      label: "Model",
      value: review?.reasoning_model ?? "—",
      title: review?.prompt_identity,
    },
  ];
  // What this revision was, against the previous one — the partition in one line. Reviews
  // written before the delta existed fall back to the raw reuse count, which is the same
  // fact with less to say.
  const carried = reviewed.filter((item) => item.verdict_reused_from).length;
  if (!running && report?.delta) {
    facts.push({ label: "Revision", value: deltaFact(report.delta) });
  } else if (!running && carried > 0) {
    facts.push({ label: "Carried", value: `${carried} of ${reviewed.length} reused` });
  }
  if (running) {
    facts.push({
      label: "Judged",
      value: `${progress?.judged ?? 0} / ${progress?.total ?? 0}`,
    });
  } else if (holding) {
    // What the run could not settle for itself, which is what makes the questions worth
    // answering — and the only thing it says about verdicts it is withholding.
    facts.push({
      label: "Rests on the unstated",
      value: `${contingentCount(reviewed)} of ${reviewed.length} verdicts`,
    });
    facts.push({ label: "Judged", value: `${reviewed.length} · holding` });
  } else {
    const seconds = formatDuration(review?.duration_seconds);
    facts.push({
      label: "Finished",
      value: `${formatDate(summary?.updated_at || review?.created_at)}${
        seconds ? ` · ${seconds}` : ""
      }`,
    });
  }
  return facts;
}
