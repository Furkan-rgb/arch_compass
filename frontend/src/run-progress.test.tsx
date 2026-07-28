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

/**
 * The one stage that does not end on its own.
 *
 * Every other step here finishes because the application finished it. This one is waiting
 * on a person, so it has to read as held rather than as done — and because it is derived
 * from the stored review rather than from page state, it is still held when the reader
 * comes back to it.
 */
describe("RunProgress waiting on answers", () => {
  it("names the step before there is anything to say about it", () => {
    render(<RunProgress progress={null} />);

    // Present from the first frame, so a reader knows the run may ask before it does.
    expect(screen.getByRole("status")).toHaveTextContent("Answer what the case does not say");
  });

  it("holds while questions are outstanding, and says how many", () => {
    render(
      <RunProgress
        progress={{ ...detected, verdicts: [false, true, false], judged: 3, summarising: true }}
        awaiting={2}
      />,
    );

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("2 questions are waiting on you");
    expect(status).toHaveTextContent("The review carries on against your answers");
  });

  it("counts one question without pluralising it", () => {
    render(
      <RunProgress
        progress={{ ...detected, verdicts: [false, true, false], judged: 3, summarising: true }}
        awaiting={1}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("1 question is waiting on you");
  });

  it("reports nothing left open as a result rather than a blank", () => {
    render(
      <RunProgress
        progress={{ ...detected, verdicts: [false, true, false], judged: 3, summarising: true }}
        awaiting={0}
      />,
    );

    // A run that asked nothing is a finding: every verdict stood on what the case said.
    expect(screen.getByRole("status")).toHaveTextContent("Nothing was left open");
    expect(screen.getByRole("status")).not.toHaveTextContent("waiting on you");
  });
});
