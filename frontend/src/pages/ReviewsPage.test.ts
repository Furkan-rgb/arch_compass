import { anyRunning, groupByCase } from "./ReviewsPage";
import type { BoundaryReviewSummary } from "../types";

function review(fields: Partial<BoundaryReviewSummary>): BoundaryReviewSummary {
  return {
    review_id: "rev_1",
    case_id: "case_a",
    case_revision: 1,
    atlas_version_id: "atlas_1",
    status: "succeeded",
    boundaries_reviewed: 6,
    boundaries_material: 2,
    created_at: "2026-07-26T10:00:00Z",
    updated_at: "2026-07-26T10:00:00Z",
    boundaries_detected: 6,
    case_title: "Task scheduler",
    ...fields,
  };
}

describe("groupByCase", () => {
  it("keeps the order the listing arrived in, for cases and for rows", () => {
    // The API answers newest first, so insertion order is already the order to render:
    // a group's first row is its latest review, and the first group is the case reviewed
    // most recently.
    const grouped = groupByCase([
      review({ review_id: "rev_3", case_id: "case_b" }),
      review({ review_id: "rev_2", case_id: "case_a", case_revision: 2 }),
      review({ review_id: "rev_1", case_id: "case_a", case_revision: 1 }),
    ]);

    expect(grouped.map((group) => group.caseId)).toEqual(["case_b", "case_a"]);
    expect(grouped[1].reviews.map((item) => item.review_id)).toEqual(["rev_2", "rev_1"]);
  });

  it("takes the title from whichever review recorded one", () => {
    // A review that failed before composing a report has no title to carry, and an older
    // row of the same case is a better answer than a placeholder.
    const grouped = groupByCase([
      review({ review_id: "rev_2", case_title: null }),
      review({ review_id: "rev_1", case_title: "Task scheduler" }),
    ]);

    expect(grouped[0].title).toBe("Task scheduler");
  });

  it("has no title when no review of the case recorded one", () => {
    const grouped = groupByCase([review({ case_title: null })]);

    expect(grouped[0].title).toBeNull();
  });
});

describe("anyRunning", () => {
  it("is true only while something is still being produced", () => {
    // What decides whether the page polls at all. A listing of finished reviews cannot
    // change, so asking again would keep a local model's machine busy for nothing.
    expect(anyRunning([review({ status: "succeeded" })])).toBe(false);
    expect(anyRunning([review({ status: "failed" })])).toBe(false);
    expect(
      anyRunning([review({ status: "succeeded" }), review({ status: "running" })]),
    ).toBe(true);
    expect(anyRunning([])).toBe(false);
  });
});
