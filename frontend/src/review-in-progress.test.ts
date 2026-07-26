import { progressFromSummary, watchedProgress } from "./review-in-progress";
import type { BoundaryReviewSummary } from "./types";
import type { RunState } from "./run-progress";

function running(fields: Partial<BoundaryReviewSummary>): BoundaryReviewSummary {
  return {
    review_id: "rev_1",
    case_id: "case_a",
    case_revision: 1,
    atlas_version_id: "atlas_1",
    status: "running",
    boundaries_detected: 6,
    boundaries_reviewed: 2,
    boundaries_material: 1,
    created_at: "2026-07-26T10:00:00Z",
    updated_at: "2026-07-26T10:01:00Z",
    case_title: "Task scheduler",
    ...fields,
  };
}

describe("progressFromSummary", () => {
  it("draws the run from the counts it writes to its own record", () => {
    // What a second tab, a reload, or a run started from the CLI has to work from.
    expect(progressFromSummary(running({}))).toEqual({
      total: 6,
      boundaries: [],
      verdicts: [null, null, null, null, null, null],
      judged: 2,
      summarising: false,
    });
  });

  it("knows nothing before the sweep has finished", () => {
    // Not zero: "the sweep found none" is a different statement from "the sweep is still
    // running", and a flow drawn from a zero would claim the first.
    expect(progressFromSummary(running({ boundaries_detected: null }))).toBeNull();
    expect(progressFromSummary(undefined)).toBeNull();
  });

  it("reaches the last stage when every boundary has been judged", () => {
    expect(progressFromSummary(running({ boundaries_reviewed: 6 }))?.summarising).toBe(true);
  });
});

describe("watchedProgress", () => {
  const live: RunState = {
    total: 6,
    boundaries: ["ports.Clock"],
    verdicts: [true, null, null, null, null, null],
    judged: 1,
    summarising: false,
  };

  it("prefers the stream, which is the only source that knows the boundary names", () => {
    expect(watchedProgress(live, running({}))).toBe(live);
  });

  it("falls back to the record when this tab is not the one running it", () => {
    expect(watchedProgress(undefined, running({}))?.judged).toBe(2);
  });

  it("has nothing to draw when neither source knows anything yet", () => {
    expect(watchedProgress(undefined, undefined)).toBeNull();
  });
});
