/**
 * The ledger: the verdicts as an instrument rather than as a scroll.
 *
 * Two things are defended here. The counts have to be readable without reading anything —
 * they were previously only learnable by scrolling to the end of six essays — and while a
 * run is holding they must say how far it got and not how it went, because the verdicts of a
 * first pass are stored but withheld.
 *
 * And the loud mark goes to the exception. A column of filled badges emphasises nothing; on
 * a report where five of six boundaries should change, the one that earned its place is the
 * thing a reader is scanning for.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "./api";
import { FindingsLedger, JudgingLedger, VerdictBand } from "./review-ledger";
import type { ReviewedBoundary } from "./types";

function boundary(reference: string, name: string, material: boolean): ReviewedBoundary {
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
          location: { path: `src/${name.toLowerCase()}.py`, start_line: 12, end_line: 30 },
        },
      ],
      limitations: "A static count cannot see runtime registration.",
    },
    material,
    rationale: `Why ${name} came out the way it did.`,
    verdict_label: material ? "Not earning its place" : "Earning its place",
    policy_bearings: [
      { policy_id: "one-writer", policy_title: "One writer per store", how: "Two writers." },
    ],
  };
}

const REVIEWED = [
  boundary("BR-001", "Feed", true),
  boundary("BR-002", "Ledger", true),
  boundary("BR-003", "Digest", false),
];

function renderLedger(open: string | null = null) {
  // The excerpts request is what a row's evidence makes; it is not what these are about.
  vi.spyOn(api, "reviewSource").mockResolvedValue([]);
  const onOpen = vi.fn();
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <FindingsLedger
        reviewed={REVIEWED}
        policyCount={7}
        reviewId="rev_1"
        open={open}
        onOpen={onOpen}
        onShowInAtlas={null}
      />
    </QueryClientProvider>,
  );
  return onOpen;
}

describe("VerdictBand", () => {
  it("states the split as the first thing on the page", () => {
    render(
      <VerdictBand
        material={5}
        cleared={1}
        judged={6}
        total={6}
        mode="settled"
        facts={[{ label: "Policies", value: "27 weighed" }]}
      />,
    );

    const band = screen.getByLabelText("Verdicts");
    expect(band).toHaveTextContent("5");
    expect(band).toHaveTextContent("should change");
    expect(band).toHaveTextContent("sound");
    expect(band).toHaveTextContent("27 weighed");
  });

  it("says how far a held run got, and not how it went", () => {
    // The counterweight to withholding: a page that asked for information while saying
    // nothing about what it had found would charge the reader before showing them anything.
    // What it must not do is report the split, which is the thing being withheld.
    render(
      <VerdictBand
        material={3}
        cleared={1}
        judged={4}
        total={4}
        mode="counted"
        facts={[
          { label: "Policies", value: "7 weighed" },
          { label: "Rests on", value: "2 unanswered" },
        ]}
      />,
    );

    const band = screen.getByLabelText("Verdicts");
    expect(band).toHaveTextContent("4");
    expect(band).toHaveTextContent("boundaries judged");
    expect(band).toHaveTextContent("2 unanswered");
    expect(band).not.toHaveTextContent("should change");
    expect(band).not.toHaveTextContent("sound");
  });
});

describe("FindingsLedger", () => {
  it("stamps every row's verdict as a label in its own hue", () => {
    renderLedger();

    // Both verdicts wear the chip now: two answers read as two stamps, and the hue is
    // what separates them at a glance.
    const cleared = screen.getByText("sound");
    expect(cleared.dataset.slot).toBe("badge");
    expect(cleared.dataset.variant).toBe("cleared");
    for (const material of screen.getAllByText("should change")) {
      expect(material.dataset.slot).toBe("badge");
      expect(material.dataset.variant).toBe("material");
    }
  });

  it("lists every boundary examined, cleared ones included", () => {
    renderLedger();

    // A report that showed only problems would look identical whether every boundary was
    // examined or none ever was.
    expect(screen.getByText("package.Digest")).toBeTruthy();
    expect(screen.getAllByRole("button", { expanded: false })).toHaveLength(3);
  });

  it("filters to one verdict without changing what the counts said", () => {
    renderLedger();

    // A closed set where one answer is already true, so it announces itself as a radio
    // group rather than as three things you may press.
    fireEvent.click(screen.getByRole("radio", { name: "Earns its place" }));

    expect(screen.getByText("package.Digest")).toBeTruthy();
    expect(screen.queryByText("package.Feed")).toBeNull();
  });

  it("opens one row into the reasoning that was there before", () => {
    const onOpen = renderLedger("BR-001");

    // The essay is not gone, it is one click deep — and the row says it is the open one.
    // Every row carries its detail so a citation can open any of them; only one is shown.
    const opened = within(document.getElementById("BR-001") as HTMLElement);
    expect(opened.getByText("Why Feed came out the way it did.")).toBeTruthy();
    expect(opened.getByText("One writer per store")).toBeTruthy();
    expect(screen.getAllByRole("button", { expanded: true })).toHaveLength(1);

    // Clicking the open row closes it: one finding at a time, and the page holds which.
    fireEvent.click(screen.getAllByRole("button", { expanded: true })[0]);
    expect(onOpen).toHaveBeenCalledWith(null);
  });
});

describe("JudgingLedger", () => {
  it("fills as the stream announces each verdict, and names what is next", () => {
    render(
      <JudgingLedger
        progress={{
          total: 3,
          boundaries: ["ports.Feed", "ports.Ledger", "ports.Digest"],
          verdicts: [true, null, null],
          judged: 1,
          eliciting: false,
          summarising: false,
          concluded: false,
        }}
      />,
    );

    const ledger = screen.getByLabelText("Boundaries examined");
    expect(ledger).toHaveTextContent("1 of 3 judged");
    expect(ledger).toHaveTextContent("should change");
    expect(ledger).toHaveTextContent("judging…");
    expect(ledger).toHaveTextContent("queued");
  });

  it("says which verdicts were carried, while the run is still going", () => {
    // A carried verdict was looked up, not reached, and a row that said nothing about it
    // would have the run claim a model call it never made. The count says the same thing
    // about the run as a whole, which is what explains it finishing as fast as it does.
    render(
      <JudgingLedger
        progress={{
          total: 3,
          boundaries: ["ports.Feed", "ports.Ledger", "ports.Digest"],
          verdicts: [true, false, null],
          carriedFrom: ["rev_earlier", null, null],
          carried: 1,
          judged: 2,
          eliciting: false,
          summarising: false,
          concluded: false,
        }}
        bearings={["3/53", "2/53", "4/53"]}
      />,
    );

    const rows = within(screen.getByLabelText("Boundaries examined")).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("carried from an earlier run");
    // In place of the bearings, which are a count of what bore on it here: nothing did.
    expect(rows[0]).not.toHaveTextContent("3/53");
    expect(rows[1]).toHaveTextContent("2/53");
    expect(rows[1]).not.toHaveTextContent("carried");
    expect(screen.getByLabelText("Boundaries examined")).toHaveTextContent("1 carried");
  });

  it("draws unnamed rows for a run it is only reading the counts of", () => {
    // The detected order is known only to the run that swept for them, so a watcher reading
    // the stored record gets the shape of the answer rather than invented labels.
    render(
      <JudgingLedger
        progress={{
          total: 2,
          boundaries: [],
          verdicts: [null, null],
          judged: 1,
          eliciting: false,
          summarising: false,
          concluded: false,
        }}
      />,
    );

    expect(screen.getByLabelText("Boundaries examined")).toHaveTextContent(
      "not in its record",
    );
  });

  it("counts bearings only where the caller knows them, and only once a verdict has landed", () => {
    // The stream reports that a boundary was judged and which way, never how many policies
    // bore on it. A caller that does know — a page replaying a run it wrote itself — hands
    // them in; a caller that does not gets an empty column rather than a guess.
    const progress = {
      total: 3,
      boundaries: ["ports.Feed", "ports.Ledger", "ports.Digest"],
      verdicts: [true, null, null],
      judged: 1,
      eliciting: false,
      summarising: false,
      concluded: false,
    };
    const { rerender } = render(<JudgingLedger progress={progress} />);
    expect(screen.getByLabelText("Boundaries examined")).not.toHaveTextContent("/53");

    rerender(<JudgingLedger progress={progress} bearings={["3/53", "2/53", "4/53"]} />);
    const rows = within(screen.getByLabelText("Boundaries examined")).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("3/53");
    expect(rows[1]).not.toHaveTextContent("2/53");
    expect(rows[2]).not.toHaveTextContent("4/53");
  });

  it("takes the caller's sentence about what its rows do not contain", () => {
    // The one it writes itself is true of a run in flight and of nothing else, so a ledger
    // drawn over a set that is already named states the sentence that is true there.
    render(
      <JudgingLedger
        progress={{
          total: 1,
          boundaries: ["ports.Feed"],
          verdicts: [true],
          judged: 1,
          eliciting: false,
          summarising: false,
          concluded: false,
        }}
        foot="Cleared boundaries keep their rows."
      />,
    );

    expect(screen.getByLabelText("Boundaries examined")).toHaveTextContent(
      "Cleared boundaries keep their rows.",
    );
  });
});
