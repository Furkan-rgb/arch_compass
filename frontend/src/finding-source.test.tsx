/**
 * The code a finding was measured from, on the finding.
 *
 * The failure this fixes: asked to show the problematic code, the advisor answered that the
 * review "only contains the names of these modules". It always held the exact spans — what
 * was missing was showing them. These check that the lines appear, that they are labelled
 * with where they came from, and that a span which cannot be read says why rather than
 * leaving an empty panel.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";
import { FindingSource } from "./finding-source";
import type { BoundaryExcerpt } from "./types";

const READABLE: BoundaryExcerpt = {
  reference: "BR-007",
  qualified_name: "preflight.voices.BUILT_IN_VOICES",
  role: "States BUILT_IN_VOICES at this location.",
  location: { path: "preflight/voices.py", start_line: 9, end_line: 9 },
  text: '    9 | BUILT_IN_VOICES = ["serena", "ryan", "chelsie", "ethan"]',
  unavailable: "",
};

const UNREADABLE: BoundaryExcerpt = {
  reference: "BR-007",
  qualified_name: "narration.planning.BUILT_IN_VOICES",
  role: "States BUILT_IN_VOICES at this location.",
  location: { path: "narration/planning.py", start_line: 10, end_line: 10 },
  text: "",
  unavailable: "This repository has changed since the review ran.",
};

function renderSource(rows: BoundaryExcerpt[]) {
  const fetched = vi.spyOn(api, "reviewSource").mockResolvedValue(rows);
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <FindingSource reviewId="rev-1" reference="BR-007" />
    </QueryClientProvider>,
  );
  return fetched;
}

afterEach(() => vi.restoreAllMocks());

describe("FindingSource", () => {
  it("shows the lines, where they are, and what they contribute", async () => {
    renderSource([READABLE]);

    expect(
      await screen.findByText(/BUILT_IN_VOICES = \["serena", "ryan", "chelsie", "ethan"\]/),
    ).toBeTruthy();
    expect(screen.getByText("preflight/voices.py:9")).toBeTruthy();
    expect(screen.getByText("States BUILT_IN_VOICES at this location.")).toBeTruthy();
  });

  it("says why a span could not be read rather than showing nothing", async () => {
    renderSource([UNREADABLE]);

    expect(
      await screen.findByText("This repository has changed since the review ran."),
    ).toBeTruthy();
    // No empty code block standing in for the absence.
    expect(document.querySelector("[data-slot='source-excerpt'] pre")).toBeNull();
  });

  it("asks for the recorded span first, and for surrounding lines only on request", async () => {
    const fetched = renderSource([READABLE]);
    await screen.findByText(/9 \| BUILT_IN_VOICES/);

    // Open by default and unpadded: the substantiation is not hidden, and the span is small
    // by construction because the detector picks declarations.
    expect(fetched).toHaveBeenCalledWith("rev-1", "BR-007", 0);

    fireEvent.click(screen.getByRole("button", { name: /Show surrounding lines/ }));

    await waitFor(() => expect(fetched).toHaveBeenCalledWith("rev-1", "BR-007", 6));
  });

  it("renders nothing at all where the review recorded no spans", async () => {
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <FindingSource reviewId="rev-1" reference="BR-007" />
      </QueryClientProvider>,
    );
    vi.spyOn(api, "reviewSource").mockResolvedValue([]);

    await waitFor(() =>
      expect(container.querySelector("[data-slot='source-excerpt']")).toBeNull(),
    );
  });
});

/**
 * An answer's code comes from the file, not from the answer.
 *
 * §12.0's third clause: where the application already holds a value, a model reproducing it
 * can only produce a second copy that may disagree with the first. It did — one live run
 * returned `"chelsine"` for `"chelsie"` while every excerpt in front of it was correct. So
 * the stage marks the boundary and the interface renders that boundary's lines, which is the
 * same component and the same endpoint the finding card already uses.
 */
describe("the code beside a conversation answer", () => {
  it("is fetched per boundary the answer rests on", async () => {
    const fetched = vi.spyOn(api, "reviewSource").mockResolvedValue([READABLE]);
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        {["BR-007", "BR-008"].map((reference) => (
          <FindingSource key={reference} reviewId="rev-1" reference={reference} />
        ))}
      </QueryClientProvider>,
    );

    await waitFor(() => expect(fetched).toHaveBeenCalledTimes(2));
    expect(fetched.mock.calls.map((call) => call[1])).toEqual(["BR-007", "BR-008"]);
  });

  it("renders the file's own characters, whatever an answer said about them", async () => {
    // The drifted copy is the finding. Its value has to arrive from disk, because an answer
    // that retyped it is exactly the failure mode this replaces.
    renderSource([READABLE]);

    expect(await screen.findByText(/"chelsie"/)).toBeTruthy();
    expect(screen.queryByText(/chelsine/)).toBeNull();
  });
});
