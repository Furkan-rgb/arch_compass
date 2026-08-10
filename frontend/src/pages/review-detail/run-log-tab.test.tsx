import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import { RunLogTab } from "./run-log-tab";
import type { ReviewDetail } from "../../types";

const LOOKED = {
  lookups: [
    { tool: "search_source", arguments: { query: "RETRY_LIMIT" }, result: "one hit" },
  ],
  prompt_identity: "investigate-usage:v2:abc123def456",
};

function review(overrides: Partial<ReviewDetail>): ReviewDetail {
  return {
    review_id: "rev_2",
    status: "succeeded",
    case_id: "case_1",
    case_revision: 2,
    atlas_version_id: "atlas_1",
    reasoning_model: "fake:model",
    prompt_identity: "judge-finding-candidate:v12:abc123def456",
    ...overrides,
  } as ReviewDetail;
}

function renderTab(detail: ReviewDetail) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <RunLogTab
        review={detail}
        progress={null}
        reviewed={[]}
        watching={false}
        holding={false}
        running={false}
        openQuestionCount={0}
        answered={0}
        caseRevision={detail.case_revision}
      />
    </QueryClientProvider>,
  );
}

describe("RunLogTab", () => {
  it("shows a second pass the checking of the pass that asked", async () => {
    // A second pass never investigates — it judges answers and concludes — so its log
    // carries the record behind the questions it answers, said to be exactly that.
    vi.spyOn(api, "review").mockResolvedValue(
      review({ review_id: "rev_1", investigation: LOOKED }) as never,
    );

    renderTab(review({ elicited_from: "rev_1" }));

    expect(await screen.findByText("1 lookup")).toBeInTheDocument();
    expect(screen.getByText("from the pass that asked")).toBeInTheDocument();
    expect(api.review).toHaveBeenCalledWith("rev_1");
  });

  it("asks nothing extra when the review carries its own record", () => {
    const fetched = vi.spyOn(api, "review");

    renderTab(review({ investigation: LOOKED }));

    expect(screen.getByText("1 lookup")).toBeInTheDocument();
    expect(screen.queryByText("from the pass that asked")).not.toBeInTheDocument();
    expect(fetched).not.toHaveBeenCalled();
  });
});
