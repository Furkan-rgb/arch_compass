/**
 * Triage on the ledger: the team's standing beside the model's verdict, never over it.
 *
 * What is defended: an unreviewed boundary is silent (absence is the unreviewed state);
 * a waiver cannot be recorded without a reason; a decision taken against an earlier
 * verdict announces that the ground moved instead of inheriting approval; and the
 * discussion thread loads only when opened, because most boundaries are never discussed.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";
import { DecisionMark, DispositionChip, StandingFooter } from "./triage";
import type { BoundaryTriage, ReviewedBoundaryDetail } from "./types";

const BOUNDARY: ReviewedBoundaryDetail = {
  reference: "BR-001",
  candidate: {
    pattern: "sole_implementation",
    summary: "package.Port is implemented only by package.Adapter.",
    participants: [
      {
        node_id: "port",
        qualified_name: "package.Port",
        role: "Declares the abstraction.",
      },
    ],
    limitations: "A static count cannot see runtime registration.",
  },
  fingerprint: "bdry_abc",
  material: true,
  rationale: "Argued from the case.",
  verdict_label: "Not earning its place",
};

function triage(overrides: Partial<BoundaryTriage> = {}): BoundaryTriage {
  return {
    reference: "BR-001",
    fingerprint: "bdry_abc",
    decision: null,
    comment_count: 0,
    ...overrides,
  };
}

function decided(taken: boolean): BoundaryTriage {
  return triage({
    decision: {
      decision_id: "dec_1",
      state: "waived",
      author: "Deniz",
      reason: "Intentional seam for the billing split.",
      decided_at: "2026-08-04T10:00:00Z",
      taken_on_current_verdict: taken,
    },
  });
}

function renderFooter(entry: BoundaryTriage, branchId: string | null = "branch_1") {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <StandingFooter
        boundary={BOUNDARY}
        triage={entry}
        branchId={branchId}
        reviewId="rev_1"
      />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("DecisionMark", () => {
  it("is silent for an undecided boundary — absence is the unreviewed state", () => {
    const { container } = render(<DecisionMark triage={triage()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("names the state, and warns when the verdict moved underneath it", () => {
    render(<DecisionMark triage={decided(false)} />);
    const mark = screen.getByText("Waived");
    expect(mark.title).toMatch(/against an earlier verdict/i);
  });
});

describe("DispositionChip", () => {
  it("speaks only for new and changed — known is the quiet resting state", () => {
    const { container, rerender } = render(<DispositionChip disposition="known" />);
    expect(container).toBeEmptyDOMElement();
    rerender(<DispositionChip disposition="new" />);
    expect(screen.getByText("new")).toBeInTheDocument();
  });
});

describe("StandingFooter", () => {
  it("refuses to record a waiver without a reason", () => {
    renderFooter(triage());
    fireEvent.click(screen.getByRole("radio", { name: "Waive" }));
    fireEvent.change(screen.getByLabelText("Decided by"), {
      target: { value: "Deniz" },
    });
    expect(screen.getByRole("button", { name: "Record" })).toBeDisabled();
    expect(screen.getByText("A waiver has to say why.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "Intentional seam." },
    });
    expect(screen.getByRole("button", { name: "Record" })).toBeEnabled();
  });

  it("sends the verdict context with the decision", async () => {
    const post = vi.spyOn(api, "postDecision").mockResolvedValue({
      decision_id: "dec_2",
      branch_id: "branch_1",
      boundary_fingerprint: "bdry_abc",
      state: "accepted",
      author: "Deniz",
      decided_at: "2026-08-04T10:00:00Z",
      review_id: "rev_1",
      boundary_reference: "BR-001",
      material: true,
      verdict_label: "Not earning its place",
    });
    renderFooter(triage());
    fireEvent.click(screen.getByRole("radio", { name: "Accept" }));
    fireEvent.change(screen.getByLabelText("Decided by"), {
      target: { value: "Deniz" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Record" }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][0]).toMatchObject({
      state: "accepted",
      boundary_reference: "BR-001",
      material: true,
      verdict_label: "Not earning its place",
    });
  });

  it("announces a decision the current verdict has moved away from", () => {
    renderFooter(decided(false));
    expect(screen.getByText(/Decided against an earlier verdict/)).toBeInTheDocument();
  });

  it("explains itself instead of guessing on a review with no branch", () => {
    renderFooter(triage(), null);
    expect(screen.getByText(/predates branch lineages/)).toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });

  it("loads the thread only when the discussion is opened", async () => {
    const comments = vi.spyOn(api, "decisionComments").mockResolvedValue([]);
    renderFooter(triage());
    expect(comments).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Discuss this boundary/ }));
    await waitFor(() => expect(comments).toHaveBeenCalledWith("branch_1", "bdry_abc"));
  });
});
