import { caseFormValues, casePayload } from "./case-form";
import type { ArchitectureCase } from "./types";

const STORED = {
  title: "Scheduler boundaries",
  problem_statement: "Decide which boundaries earn their place.",
  desired_outcome: "A verdict per boundary.",
  expected_future_changes: ["SMS ships next release.", "Postgres is under discussion."],
  non_goals: ["A second label format."],
  confirmed_facts: [
    { id: "stmt_1", text: "The label format is fixed downstream.", kind: "fact" },
  ],
  technical_constraints: [],
  organisational_constraints: ["One part-time maintainer."],
  quality_attributes: [],
  functional_requirements: [],
  actors_and_workflows: [],
  clarifications: [
    {
      id: "clar_1",
      question: "Is a second label format actually planned?",
      answer: "No, and none is planned.",
      bears_on: "non_goals",
    },
  ],
} as unknown as ArchitectureCase;

describe("caseFormValues", () => {
  it("shows each list entry on its own line, in stored order", () => {
    const values = caseFormValues(STORED);

    expect(values.expected_future_changes).toBe(
      "SMS ships next release.\nPostgres is under discussion.",
    );
    expect(values.confirmed_facts).toBe("The label format is fixed downstream.");
    expect(values.technical_constraints).toBe("");
  });

  it("is empty for a case that does not exist yet", () => {
    expect(caseFormValues(undefined).title).toBe("");
    expect(caseFormValues(undefined).clarifications).toEqual([]);
  });

  it("keeps a clarification as a pair rather than flattening it to a line", () => {
    // The one field here that is not a textarea of lines. Half of a pair is the advisor's
    // words and half is the reader's, and a format that ran them together would lose which
    // was which — which is the failure the pair replaced.
    expect(caseFormValues(STORED).clarifications).toEqual([
      {
        id: "clar_1",
        question: "Is a second label format actually planned?",
        answer: "No, and none is planned.",
        bears_on: "non_goals",
      },
    ]);
  });
});

describe("casePayload", () => {
  it("round-trips a stored case without changing what it says", () => {
    const payload = casePayload(caseFormValues(STORED));

    expect(payload.expected_future_changes).toEqual(STORED.expected_future_changes);
    expect(payload.non_goals).toEqual(STORED.non_goals);
    expect(payload.organisational_constraints).toEqual(STORED.organisational_constraints);
  });

  it("sets the statement kind the list implies rather than asking for it", () => {
    const payload = casePayload({
      ...caseFormValues(undefined),
      confirmed_facts: "SQLite is fixed.\n\n  Trailing blank lines are not entries.  \n",
    });

    expect(payload.confirmed_facts).toEqual([
      { text: "SQLite is fixed.", kind: "fact" },
      { text: "Trailing blank lines are not entries.", kind: "fact" },
    ]);
  });

  it("carries every key, so a cleared field is cleared in the next revision", () => {
    const payload = casePayload({ ...caseFormValues(STORED), non_goals: "" });

    expect(payload.non_goals).toEqual([]);
    expect(Object.keys(payload)).toContain("non_goals");
  });

  it("carries a clarification through with the question untouched", () => {
    const payload = casePayload(caseFormValues(STORED));

    // The question is the review's wording. A case that claimed a review asked something it
    // never did would be a fabricated record of an exchange, so nothing in this form can
    // reach that half — and the force it carries was read from the review's own report, not
    // chosen here.
    expect(payload.clarifications).toEqual(STORED.clarifications);
  });

  it("drops a pair whose answer has been emptied", () => {
    // Clearing the box is how someone withdraws an answer without hunting for the button.
    // A question left in the case with nothing answering it reads to every later pass as a
    // statement about this project, so it is not sent.
    const values = caseFormValues(STORED);
    const payload = casePayload({
      ...values,
      clarifications: values.clarifications.map((item) => ({ ...item, answer: "  " })),
    });

    expect(payload.clarifications).toEqual([]);
  });

  it("trims the answer without touching the question", () => {
    const values = caseFormValues(STORED);
    const payload = casePayload({
      ...values,
      clarifications: values.clarifications.map((item) => ({
        ...item,
        answer: "  Reworded, and still mine.  ",
      })),
    });

    expect(payload.clarifications).toEqual([
      { ...values.clarifications[0], answer: "Reworded, and still mine." },
    ]);
  });
});
