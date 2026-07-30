import { fireEvent, render, screen } from "@testing-library/react";

import { CaseForm } from "./case-form";
import type { ArchitectureCase } from "./types";

const CASE = {
  title: "Task scheduler boundary review",
  problem_statement: "Which of these ports are earning their place?",
  desired_outcome: "A verdict per boundary.",
  expected_future_changes: ["SMS delivery is scheduled for the next release"],
} as ArchitectureCase;

const ANSWERED = {
  ...CASE,
  clarifications: [
    {
      id: "clar_1",
      question: "Is a second delivery channel actually planned?",
      answer: "Yes — SMS is scheduled and the contract is signed.",
      bears_on: "expected_future_changes",
    },
  ],
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

/**
 * The pairs a review's questions produced, revisable like anything else in the case.
 *
 * Both halves are shown and only one of them is editable, which is the whole point of keeping
 * them together: the question is the advisor's words and the answer is the reader's, and a
 * reader has to be able to tell which is which before they can sensibly change either.
 */
describe("CaseForm and the answers already recorded", () => {
  it("shows the question as the review's and the answer as the reader's own", () => {
    render(form({ initial: ANSWERED }));

    // The question is prose, not a box: it is not theirs to edit, and a form that offered to
    // would let a case claim a review asked something it never did.
    expect(
      screen.getByText(/Asked: Is a second delivery channel actually planned\?/),
    ).toBeTruthy();
    expect(
      screen.getByLabelText('Your answer to "Is a second delivery channel actually planned?"'),
    ).toHaveValue("Yes — SMS is scheduled and the contract is signed.");
    // The force it carries is shown rather than offered. It was read from the review's own
    // report, and a case that could choose it could decide how its own evidence is weighed.
    expect(screen.getByText("expected_future_changes")).toBeTruthy();
  });

  it("takes a pair out of the case when it is removed", () => {
    render(form({ initial: ANSWERED }));

    fireEvent.click(
      screen.getByRole("button", {
        name: 'Remove the answer to "Is a second delivery channel actually planned?"',
      }),
    );

    expect(
      screen.queryByText(/Asked: Is a second delivery channel actually planned\?/),
    ).toBeNull();
  });

  it("offers no section at all where no review has asked anything", () => {
    // An empty one would invite someone to write their own question, and these are not theirs
    // to write: a pair exists because a verdict turned on something the case did not say.
    const { container } = render(form({ initial: CASE }));

    expect(container.querySelector("[data-slot='case-clarifications']")).toBeNull();
  });
});
