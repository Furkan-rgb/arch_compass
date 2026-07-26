import { render, screen } from "@testing-library/react";

import { RunProgress, applyProgress, type RunState } from "./run-progress";

const BOUNDARIES = ["ports.TaskFormatter", "ports.Clock", "ports.TaskStore"];

const detected: RunState = {
  total: 3,
  boundaries: BOUNDARIES,
  verdicts: [null, null, null],
  judged: 0,
  summarising: false,
};

describe("applyProgress", () => {
  it("records a verdict at the position the stream gave it", () => {
    const state = applyProgress(detected, {
      event: "judged",
      position: 2,
      total: 3,
      abstraction: "ports.Clock",
      material: true,
    });

    // Position, not name: two boundaries can share a name and their positions cannot
    // collide, so a verdict written by name could land on the wrong row.
    expect(state?.verdicts).toEqual([null, true, null]);
    expect(state?.judged).toBe(2);
  });

  it("leaves the flow alone when the stream announces the review's identity", () => {
    // `started` is for navigation, not for the flow: it arrives before the sweep, when
    // there is genuinely nothing to draw yet.
    expect(
      applyProgress(null, {
        event: "started",
        review_id: "rev_1",
        case_id: "case_a",
        case_revision: 1,
      }),
    ).toBeNull();
  });

  it("ignores a verdict that arrives before detection said how many there are", () => {
    expect(
      applyProgress(null, {
        event: "judged",
        position: 1,
        total: 3,
        abstraction: "ports.Clock",
        material: false,
      }),
    ).toBeNull();
  });
});

describe("RunProgress", () => {
  it("shows the sweep running before detection has said how much there is", () => {
    render(<RunProgress progress={null} />);

    expect(screen.getByRole("status")).toHaveTextContent("Sweep the atlas");
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("names every boundary and marks the one under judgement", () => {
    render(<RunProgress progress={{ ...detected, verdicts: [false, null, null], judged: 1 }} />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("1 of 3 judged");
    // A landed verdict is worth reading before the review page exists.
    expect(status).toHaveTextContent("earning its place");
    expect(status).toHaveTextContent("judging…");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
  });

  it("moves on to the last stage rather than counting past the end", () => {
    render(
      <RunProgress
        progress={{ ...detected, verdicts: [false, true, false], judged: 3, summarising: true }}
      />,
    );

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Read the verdicts as a set");
    expect(status).not.toHaveTextContent("4 of 3");
    expect(status).not.toHaveTextContent("judging…");
  });

  it("reports an empty sweep as a result rather than as a stalled run", () => {
    render(
      <RunProgress
        progress={{ total: 0, boundaries: [], verdicts: [], judged: 0, summarising: false }}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Nothing to judge in this repository");
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});
