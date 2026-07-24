import { render, screen } from "@testing-library/react";

import {
  describeFailureDiagnostic,
  FailureDiagnostics,
} from "./failure-diagnostics";

test("renders allowlisted cluster partition details as actionable steps", () => {
  render(
    <FailureDiagnostics
      diagnostics={[
        {
          code: "unknown_force_references",
          force_handles: [],
          count: 2,
        },
        {
          code: "missing_force_references",
          force_handles: ["F2", "F4"],
          count: null,
        },
      ]}
    />,
  );

  expect(
    screen.getByText(/did not assign every force exactly once/i),
  ).toBeInTheDocument();
  expect(screen.getByText(/2 unrecognized force references/i)).toBeInTheDocument();
  expect(screen.getByText(/missing force handles: F2, F4/i)).toBeInTheDocument();
});

test("diagnostic descriptions contain only structured fields", () => {
  expect(
    describeFailureDiagnostic({
      code: "duplicate_force_references",
      force_handles: ["F1"],
      count: null,
    }),
  ).toBe("Repeated force handles: F1.");
});
