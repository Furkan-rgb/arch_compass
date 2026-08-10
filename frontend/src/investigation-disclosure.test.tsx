import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InvestigationDisclosure } from "./investigation-disclosure";
import type { RecordedInvestigation } from "./types";

const LOOKED: RecordedInvestigation = {
  lookups: [
    {
      tool: "search_source",
      arguments: { query: "RETRY_LIMIT" },
      result: "billing/settings.py:4: RETRY_LIMIT = 5\nnotifications/settings.py:5: RETRY_LIMIT = 5",
    },
    {
      tool: "read_source",
      arguments: { path: "billing/settings.py", start_line: 1, end_line: 8 },
      result: "billing/settings.py:1-8\n...",
    },
  ],
  closing: "Both copies feed the same client.",
  prompt_identity: "investigate-usage:v2:abc123def456",
};

describe("InvestigationDisclosure", () => {
  it("names each lookup by what it did, with the transcript underneath", () => {
    render(<InvestigationDisclosure investigation={LOOKED} />);

    expect(screen.getByText("2 lookups")).toBeInTheDocument();
    expect(screen.getByText("searched for “RETRY_LIMIT”")).toBeInTheDocument();
    expect(screen.getByText("read billing/settings.py:1")).toBeInTheDocument();
    expect(screen.getByText(/notifications\/settings\.py:5/)).toBeInTheDocument();
    expect(screen.getByText("Both copies feed the same client.")).toBeInTheDocument();
  });

  it("captions an abandoned investigation on whatever it gathered", () => {
    render(
      <InvestigationDisclosure
        investigation={{
          ...LOOKED,
          closing: "",
          abandoned: "the model's reply was truncated",
        }}
      />,
    );

    expect(screen.getByText("2 lookups")).toBeInTheDocument();
    expect(screen.getByText("cut short")).toBeInTheDocument();
    expect(
      screen.getByText(/the model's reply was truncated/),
    ).toBeInTheDocument();
  });

  it("says why nothing could look, instead of not appearing", () => {
    render(
      <InvestigationDisclosure
        investigation={{
          lookups: [],
          withheld:
            "This repository has changed since the review ran; rerun the index to restore lookups.",
          prompt_identity: "investigate-for-answer:v1:abc123def456",
        }}
      />,
    );

    expect(screen.getByText("lookups unavailable")).toBeInTheDocument();
    expect(
      screen.getByText(/changed since the review ran/),
    ).toBeInTheDocument();
  });

  it("renders nothing when there is nothing to disclose", () => {
    const { container } = render(
      <InvestigationDisclosure
        investigation={{ lookups: [], prompt_identity: "investigate-usage:v2:abc" }}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
