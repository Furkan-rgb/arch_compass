/**
 * The surface a review shows while it is holding for answers.
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
import { describe, expect, it, vi } from "vitest";

import { HeldVerdicts, HoldBanner, contingentCount } from "./review-awaiting";
import type { ReviewedBoundary } from "./types";

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

describe("contingentCount", () => {
  it("counts the verdicts that said outright they turn on something unstated", () => {
    expect(contingentCount(REVIEWED)).toBe(2);
  });
});

describe("HoldBanner", () => {
  it("leads with the one thing left to do, and says where the answers go", () => {
    // A held review has exactly one next step. The banner is above everything the review
    // has to say because holding is the review's state, not one of its sections.
    const onAnswer = vi.fn();
    render(<HoldBanner questionCount={2} nextRevision={3} onAnswer={onAnswer} />);

    expect(screen.getByRole("status")).toHaveTextContent("2 questions need answers");
    expect(screen.getByRole("status")).toHaveTextContent("case revision 3");

    fireEvent.click(screen.getByRole("button", { name: "Answer 2 questions" }));
    expect(onAnswer).toHaveBeenCalledOnce();
  });

  it("counts one question without pluralising it", () => {
    render(<HoldBanner questionCount={1} nextRevision={2} onAnswer={vi.fn()} />);

    expect(screen.getByRole("status")).toHaveTextContent("One question needs an answer");
  });
});

describe("HeldVerdicts", () => {
  it("withholds the verdicts until they are asked for", () => {
    render(<HeldVerdicts reviewed={REVIEWED} findings={<p>the held verdicts</p>} />);

    expect(screen.queryByText("the held verdicts")).toBeNull();
  });

  it("reveals them on request, under a warning about what they are", () => {
    // Not hidden, because someone who cannot answer has to be able to get something.
    render(<HeldVerdicts reviewed={REVIEWED} findings={<p>the held verdicts</p>} />);

    fireEvent.click(screen.getByRole("button", { name: /provisional verdicts/ }));

    expect(screen.getByText("the held verdicts")).toBeTruthy();
    expect(screen.getByText(/These verdicts are provisional/)).toBeTruthy();
    // The measurement, not an adjective: a reader deciding whether to act on these is owed
    // the actual rate at which they moved.
    expect(screen.getByText(/four of five verdicts came out differently/)).toBeTruthy();
  });
});
