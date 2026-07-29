import { render, screen } from "@testing-library/react";

import { RunProgress, applyProgress, type RunState } from "./run-progress";

const BOUNDARIES = ["ports.TaskFormatter", "ports.Clock", "ports.TaskStore"];

const detected: RunState = {
  total: 3,
  boundaries: BOUNDARIES,
  verdicts: [null, null, null],
  judged: 0,
  eliciting: false,
  summarising: false,
};

const judged: RunState = {
  ...detected,
  verdicts: [false, true, false],
  judged: 3,
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

  it("keeps the two set-wide calls apart, because they are different stages", () => {
    // One ends in a conclusion and the other may end in a run that stops and waits for a
    // person. A single "the last call is running" flag could not tell the reader which.
    expect(applyProgress(detected, { event: "eliciting", total: 3 })).toMatchObject({
      eliciting: true,
      summarising: false,
      judged: 3,
    });
    expect(applyProgress(detected, { event: "summarising", total: 3 })).toMatchObject({
      eliciting: false,
      summarising: true,
      judged: 3,
    });
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

  it("moves on to the asking stage rather than counting past the end", () => {
    render(<RunProgress progress={{ ...judged, eliciting: true }} />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Ask what it needs to know");
    expect(status).not.toHaveTextContent("4 of 3");
    expect(status).not.toHaveTextContent("judging…");
  });

  it("reports an empty sweep as a result rather than as a stalled run", () => {
    render(
      <RunProgress
        progress={{
          total: 0,
          boundaries: [],
          verdicts: [],
          judged: 0,
          eliciting: false,
          summarising: false,
        }}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Nothing to judge in this repository");
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});

/**
 * Seven stages across two runs, drawn as one journey.
 *
 * That is what the reader experiences: they point at a repository, it judges, it asks, they
 * answer, it judges again and concludes. Each pass is its own immutable review pinned to its
 * own case revision, so the second cannot be a continuation of the first as a record — but
 * drawing them as two unrelated three-stage runs would hide the only part that needs
 * explaining, which is the middle the reader has to supply.
 */
describe("RunProgress across the two passes", () => {
  it("names every stage of the journey from the first frame", () => {
    render(<RunProgress progress={null} />);

    // Present before any of them has anything to report, so a reader knows what they are
    // in for — including that they will be asked, and that nothing is reported until then.
    const status = screen.getByRole("status");
    for (const stage of [
      "Sweep the atlas",
      "Judge each boundary",
      "Ask what it needs to know",
      "Answer the questions",
      "Write the case from your answers",
      "Judge each boundary again",
      "Read the verdicts as a set",
    ]) {
      expect(status).toHaveTextContent(stage);
    }
  });

  it("says outright that nothing is reported until the questions are settled", () => {
    render(<RunProgress progress={null} />);

    // The reason for the hold, stated where the hold is drawn. Without it, a reader who
    // reaches the questions and no results reasonably reads the run as broken.
    expect(screen.getByRole("status")).toHaveTextContent(
      "Nothing is reported until these are settled",
    );
  });

  it("holds while questions are outstanding, and says how many", () => {
    render(<RunProgress progress={{ ...judged, eliciting: true }} awaiting={2} />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("2 questions are waiting on you");
    expect(status).toHaveTextContent("Answer what you know and leave the rest");
  });

  it("counts one question without pluralising it", () => {
    render(<RunProgress progress={{ ...judged, eliciting: true }} awaiting={1} />);

    expect(screen.getByRole("status")).toHaveTextContent("1 question is waiting on you");
  });

  it("reports nothing left open as a result rather than a blank", () => {
    render(<RunProgress progress={{ ...judged, eliciting: true }} awaiting={0} />);

    // A run that asked nothing is a finding: every verdict stood on what the case said.
    expect(screen.getByRole("status")).toHaveTextContent("Nothing to ask");
    expect(screen.getByRole("status")).not.toHaveTextContent("waiting on you");
  });

  it("draws the first pass as history once the second one is running", () => {
    render(
      <RunProgress
        progress={{ ...detected, verdicts: [false, null, null], judged: 1 }}
        pass={2}
        answersRecorded={2}
      />,
    );

    const status = screen.getByRole("status");
    // The second pass counts its own re-judging, and says the earlier stages happened
    // rather than hiding them — otherwise the word "again" has nothing to refer back to.
    expect(status).toHaveTextContent("1 of 3 re-judged");
    expect(status).toHaveTextContent("The questions you answered were composed here");
    expect(status).toHaveTextContent("Recorded as revision 2 of the case");
  });
});
