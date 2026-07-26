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
});
