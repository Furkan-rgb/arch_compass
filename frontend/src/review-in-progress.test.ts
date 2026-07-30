import { progressFromSummary, runCrawl, watchedProgress } from "./review-in-progress";
import type { BoundaryReviewSummary, ReviewedBoundary } from "./types";
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
      eliciting: false,
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
    // Which of the two set-wide calls that is, is not in the counts — but the row does say
    // which pass this is, and a first pass asks where a second concludes.
    const first = progressFromSummary(running({ boundaries_reviewed: 6 }));
    expect(first?.eliciting).toBe(true);
    expect(first?.summarising).toBe(false);

    const second = progressFromSummary(
      running({ boundaries_reviewed: 6, elicited_from: "rev_0" }),
    );
    expect(second?.summarising).toBe(true);
    expect(second?.eliciting).toBe(false);
  });
});

describe("watchedProgress", () => {
  const live: RunState = {
    total: 6,
    boundaries: ["ports.Clock"],
    verdicts: [true, null, null, null, null, null],
    judged: 1,
    eliciting: false,
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

/**
 * The run's own log, from whichever record still has it.
 *
 * A finished review carries every verdict it reached, so its log outlives the stream that
 * produced it; a running one has only what the stream has said so far.
 */
describe("runCrawl", () => {
  const judgedBoundary = (reference: string, name: string, material: boolean): ReviewedBoundary => ({
    reference,
    candidate: {
      pattern: "sole_implementation",
      summary: `package.${name} is implemented once.`,
      participants: [
        { node_id: name, qualified_name: `package.${name}`, role: "Declares it." },
      ],
      limitations: "A static count cannot see runtime registration.",
    },
    material,
    rationale: "Argued from the case.",
    verdict_label: material ? "Not earning its place" : "Earning its place",
  });

  it("reads a finished run off the verdicts it reached", () => {
    expect(
      runCrawl(null, [judgedBoundary("BR-001", "Feed", true), judgedBoundary("BR-002", "Clock", false)]),
    ).toEqual([
      { position: 1, label: "package.Feed", verdict: true, live: false },
      { position: 2, label: "package.Clock", verdict: false, live: false },
    ]);
  });

  it("marks the boundary under the model right now while one is running", () => {
    const crawl = runCrawl(
      {
        total: 3,
        boundaries: ["ports.Feed", "ports.Clock", "ports.Store"],
        verdicts: [true, null, null],
        judged: 1,
        eliciting: false,
        summarising: false,
      },
      [],
    );

    expect(crawl.map((entry) => entry.live)).toEqual([false, true, false]);
    expect(crawl[0]).toEqual({ position: 1, label: "ports.Feed", verdict: true, live: false });
  });

  it("stops naming one as live once the set-wide call has started", () => {
    // Every boundary is judged by then, so a row still saying "judging" would be claiming a
    // model call that is not happening.
    const crawl = runCrawl(
      {
        total: 1,
        boundaries: ["ports.Feed"],
        verdicts: [false],
        judged: 1,
        eliciting: true,
        summarising: false,
      },
      [],
    );

    expect(crawl.every((entry) => !entry.live)).toBe(true);
  });

  it("names the boundaries of a held run without saying how they came out", () => {
    // The verdicts are in the report this reads, and the whole of the holding state is that
    // they are not reported yet. Printing them in the log would be the reveal, taken out of
    // the reader's hands.
    const crawl = runCrawl(null, [judgedBoundary("BR-001", "Feed", true)], false);

    expect(crawl[0].label).toBe("package.Feed");
    expect(crawl[0].verdict).toBeNull();
  });

  it("has nothing to draw before either record knows anything", () => {
    expect(runCrawl(null, [])).toEqual([]);
  });
});
