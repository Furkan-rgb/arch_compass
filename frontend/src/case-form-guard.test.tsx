import { render, screen } from "@testing-library/react";

import { CaseForm } from "./case-form";
import type { ArchitectureCase } from "./types";

const CASE = {
  title: "Task scheduler boundary review",
  problem_statement: "Which of these ports are earning their place?",
  desired_outcome: "A verdict per boundary.",
  expected_future_changes: ["SMS delivery is scheduled for the next release"],
} as ArchitectureCase;

function form(props: Partial<Parameters<typeof CaseForm>[0]> = {}) {
  return (
    <CaseForm
      heading="Revise this case"
      initial={undefined}
      submitLabel="Save"
      pendingLabel="Saving…"
      pending={false}
      error={null}
      onSubmit={() => undefined}
      onClose={() => undefined}
      {...props}
    />
  );
}

describe("CaseForm while its case is still loading", () => {
  it("offers no fields to fill in", () => {
    // `useForm` takes its defaults once, at mount. A form rendered before the case arrives
    // holds empty fields for good, and submitting it writes a revision with every field
    // cleared — the payload always carries every key. Silently erasing someone's case is
    // the worst outcome this form has, so it is not offered until it can be right.
    render(form({ loading: true }));

    expect(screen.queryByLabelText(/Name for this case/)).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Reading the case");
  });

  it("opens with the case's own answers once it has them", () => {
    render(form({ initial: CASE }));

    // Matched loosely: a label here carries the question, why it matters, and a pair of
    // examples, so its accessible name is all of that text rather than the question.
    expect(screen.getByLabelText(/Name for this case/)).toHaveValue(CASE.title);
    expect(screen.getByLabelText(/What changes are actually coming\?/)).toHaveValue(
      "SMS delivery is scheduled for the next release",
    );
  });
});
