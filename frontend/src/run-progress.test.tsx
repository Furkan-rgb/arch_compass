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
  concluded: false,
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

  it("keeps a carried verdict distinguishable from one this run reached", () => {
    // A re-run over an unchanged question reuses every verdict it can and is over in
    // seconds. Folded as a plain verdict, that is a run that appears to have judged a
    // repository faster than a model can answer — so the origin lands with the verdict,
    // and the tally beside it is what a caller reads to say "3 of 3 carried".
    // Folded from the stream's own first line rather than from the fixture above, because
    // detection is what gives the run a row per boundary to write an origin into.
    const swept = applyProgress(null, {
      event: "detected",
      total: 3,
      boundaries: BOUNDARIES,
    });
    const first = applyProgress(applyProgress(swept, {
      event: "judged",
      position: 1,
      total: 3,
      abstraction: "ports.TaskFormatter",
      material: false,
      verdict_reused_from: "rev_earlier",
      carried: 1,
    }), {
      event: "judged",
      position: 2,
      total: 3,
      abstraction: "ports.Clock",
      material: true,
    });

    expect(first?.carriedFrom).toEqual(["rev_earlier", null, null]);
    expect(first?.carried).toBe(1);
  });

  it("holds every boundary the run has handed to the model at once", () => {
    // Not one. Judging overlaps up to what the provider allows, and a flow that could mark
    // only the row after the last verdict was drawing a slower run than the one happening.
    const state = applyProgress(
      applyProgress(detected, { event: "judging", position: 1, total: 3 }),
      { event: "judging", position: 2, total: 3 },
    );

    expect(state?.judging).toEqual([1, 2]);
  });

  it("clears everything a verdict has overtaken, and leaves the rest in flight", () => {
    // Verdicts are reported in submission order, so a verdict at position 2 settles that
    // nothing before position 2 is still under the model — whatever order the announcements
    // arrived in. A later boundary already announced stays where it is.
    const state = applyProgress(
      [1, 2, 4].reduce<RunState>(
        (current, position) =>
          applyProgress(current, { event: "judging", position, total: 3 }),
        detected,
      ),
      { event: "judged", position: 2, total: 3, abstraction: "ports.Clock", material: true },
    );

    expect(state?.judging).toEqual([4]);
  });

  it("empties the in-flight set once judging is over, whichever way it ended", () => {
    const judging = applyProgress(detected, { event: "judging", position: 3, total: 3 });

    expect(applyProgress(judging, { event: "eliciting", total: 3 })?.judging).toEqual([]);
    expect(applyProgress(judging, { event: "summarising", total: 3 })?.judging).toEqual([]);
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

  it("spins every boundary that is under the model, not only the next one", () => {
    render(
      <RunProgress
        progress={{ ...detected, verdicts: [null, null, null], judging: [1, 3] }}
      />,
    );

    const status = screen.getByRole("status");
    // Two spinning rows, because two boundaries are genuinely being judged. The row after
    // the last verdict is *not* one of them here — position 2 was never announced.
    expect(screen.getAllByText("judging…")).toHaveLength(2);
    expect(status).toHaveTextContent("waiting");
  });

  it("marks nothing while a live run has announced nothing yet", () => {
    // The moment between detection and the first handover. An empty set is a statement —
    // the run is not judging anything — and it is different from having no set at all.
    render(<RunProgress progress={{ ...detected, judging: [] }} />);

    expect(screen.queryByText("judging…")).toBeNull();
  });

  it("falls back to the single mark where nothing said what is in flight", () => {
    // A watcher reading the run's stored record: the counts say how many verdicts landed
    // and nothing about handovers, so the row after the last one is marked, as before.
    render(<RunProgress progress={{ ...detected, verdicts: [false, null, null], judged: 1 }} />);

    expect(screen.getAllByText("judging…")).toHaveLength(1);
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
          concluded: false,
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

  it("closes the last stage on the run's sign-off, which is the only line that can", () => {
    // The stage *is* the concluding call, so it cannot report its own end: waiting for
    // `summarising` to clear left a finished review spinning for as long as the page was open.
    const state = applyProgress(
      { ...judged, summarising: true },
      {
        event: "completed",
        review: {
          status: "succeeded",
          case_id: "case_a",
          case_revision: 2,
          atlas_version_id: "atlas_1",
          reasoning_model: "qwen3",
          prompt_identity: "p1",
        },
      },
    );
    expect(state).toMatchObject({ concluded: true, summarising: false, judged: 3 });

    render(<RunProgress progress={state} pass={2} awaiting={0} />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Read the verdicts as a set");
    expect(status.querySelector(".spin")).toBeNull();
    // A full bar over a run making no more progress is a claim about progress.
    expect(screen.queryByRole("progressbar")).toBeNull();
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
