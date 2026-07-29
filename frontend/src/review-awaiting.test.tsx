/**
 * The surface that replaces the results screen while questions are open.
 *
 * What is defended here is a product decision, not a layout: verdicts exist and are stored,
 * and this page does not present them as findings. That was measured rather than assumed —
 * on the bundled `warehouse-sync` example four of five first-pass verdicts moved once these
 * questions were answered, and the one that held was not the one carrying a hinge, so
 * "show the confident ones" is not a safe refinement either.
 *
 * The reveal is the counterweight and is tested just as hard. Someone reviewing unfamiliar
 * code may genuinely not be able to answer, and withholding unconditionally would rebuild
 * the adoption tax in a new shape. Revealing resolves nothing: the record still says the
 * questions went unanswered, because they did.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AwaitingAnswers, contingentCount } from "./review-awaiting";
import type { BoundaryReview, ReviewedBoundary } from "./types";

function boundary(reference: string, name: string, hinged: boolean): ReviewedBoundary {
  return {
    reference,
    candidate: {
      pattern: "sole_implementation",
      summary: `package.${name} is implemented only by package.${name}Adapter.`,
      participants: [
        {
          node_id: name.toLowerCase(),
          qualified_name: `package.${name}`,
          role: "Declares the abstraction.",
        },
      ],
      limitations: "A static count cannot see runtime registration.",
    },
    material: false,
    rationale: "Argued from the case.",
    verdict_label: "Earning its place",
    hinge: hinged
      ? {
          unknown: "The case does not say whether a second warehouse is coming.",
          if_confirmed: "The boundary absorbs a change that is coming.",
          if_denied: "Nothing arrives to justify the indirection.",
        }
      : undefined,
  };
}

const REVIEWED = [
  boundary("BR-001", "Feed", true),
  boundary("BR-002", "Ledger", false),
  boundary("BR-003", "Digest", true),
];

const REVIEW = {
  review_id: "rev_1",
  status: "awaiting_answers",
  case_id: "case_a",
  case_revision: 1,
  atlas_version_id: "atlas_1",
  reasoning_model: "ollama:gemma4:26b",
  prompt_identity: "judge-finding-candidate:v10:abc123456789",
  created_at: "2026-07-27T10:00:00Z",
  report: { case_title: "Keeping stock in step with the warehouse" },
} as unknown as BoundaryReview;

function renderAwaiting(questionCount = 2) {
  return render(
    <MemoryRouter>
      <AwaitingAnswers
        review={REVIEW}
        questionCount={questionCount}
        reviewed={REVIEWED}
        policyCount={7}
        findings={<p>the held verdicts</p>}
      >
        <p>the questions</p>
      </AwaitingAnswers>
    </MemoryRouter>,
  );
}

describe("contingentCount", () => {
  it("counts the verdicts that said outright they turn on something unstated", () => {
    expect(contingentCount(REVIEWED)).toBe(2);
  });
});

describe("AwaitingAnswers", () => {
  it("leads with the questions and withholds the verdicts", () => {
    renderAwaiting();

    expect(screen.getByText("the questions")).toBeTruthy();
    expect(screen.queryByText("the held verdicts")).toBeNull();
  });

  it("says what was done, so the questions are worth answering", () => {
    // The counterweight to withholding. A page that asked for information while saying
    // nothing about what it had found would charge the reader before showing them anything,
    // which is the tax this whole mechanism exists to remove.
    renderAwaiting();

    const head = screen.getByText(/boundaries judged/);
    expect(head.textContent).toContain("3");
    expect(head.textContent).toContain("7");
    expect(head.textContent).toContain("2");
  });

  it("reveals the verdicts on request, under a warning about what they are", () => {
    // Not hidden, because someone who cannot answer has to be able to get something.
    renderAwaiting();

    fireEvent.click(screen.getByRole("button", { name: /provisional verdicts/ }));

    expect(screen.getByText("the held verdicts")).toBeTruthy();
    expect(screen.getByText(/These verdicts are provisional/)).toBeTruthy();
    // The measurement, not an adjective: a reader deciding whether to act on these is owed
    // the actual rate at which they moved.
    expect(screen.getByText(/four of five verdicts came out differently/)).toBeTruthy();
  });

  it("keeps the run's own stages on screen, still holding", () => {
    renderAwaiting(1);

    // The journey is not over, and drawing it as finished would present a review as
    // complete while it is still waiting on a person.
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("1 question is waiting on you");
    expect(status).toHaveTextContent("Judge each boundary again");
  });
});
