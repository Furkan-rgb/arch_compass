import {
  appendSeedLines,
  caseFormValues,
  casePayload,
  CONVENTION_SEEDS,
} from "./case-form";
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
  stated_conventions: [
    "All I/O crosses a port; the domain never imports an adapter.",
    "Ports exist for every dependency we intend to swap or fake in tests.",
  ],
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
    expect(values.stated_conventions).toBe(
      "All I/O crosses a port; the domain never imports an adapter.\n" +
        "Ports exist for every dependency we intend to swap or fake in tests.",
    );
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
    expect(payload.stated_conventions).toEqual(STORED.stated_conventions);
  });

  it("saves the lines a stance was written as, and nothing about which chip wrote them", () => {
    // "We are hexagonal" is not something a boundary can be held against; the lines are. The
    // seeder exists to save typing, so what leaves the form is prose the reader can reword or
    // delete, with no record of the style it started as.
    const payload = casePayload({
      ...caseFormValues(undefined),
      stated_conventions: "  Adapters may not import domain internals.  \n\nOne port per swap.",
    });

    expect(payload.stated_conventions).toEqual([
      "Adapters may not import domain internals.",
      "One port per swap.",
    ]);
    expect(Object.keys(payload)).not.toContain("convention_style");
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

/**
 * What a chip does to the box, as a rule rather than as a click.
 *
 * The whole of a seeder's behaviour is here: it adds lines and it keeps what is written. Every
 * hazard in it — a doubled commitment, a reworded line quietly replaced — is a hazard about
 * text, so it is settled about text.
 */
describe("appendSeedLines", () => {
  const hexagonal = CONVENTION_SEEDS.find((seed) => seed.name === "Hexagonal")!.lines;

  it("writes a style's lines into an empty box", () => {
    expect(appendSeedLines("", hexagonal)).toBe(hexagonal.join("\n"));
  });

  it("adds them under what is already written, keeping every word of it", () => {
    const written = "Nothing in this codebase talks to the filesystem outside `storage/`.";

    expect(appendSeedLines(written, hexagonal)).toBe([written, ...hexagonal].join("\n"));
  });

  it("does not write a line that is already there", () => {
    // Pressing the same chip twice is a slip, not a second commitment.
    const once = appendSeedLines("", hexagonal);

    expect(appendSeedLines(once, hexagonal)).toBe(once);
  });

  it("adds only the lines that are missing", () => {
    const partial = hexagonal[0];

    expect(appendSeedLines(partial, hexagonal)).toBe([partial, hexagonal[1]].join("\n"));
  });

  it("leaves a reworded line alone and adds the seed beside it", () => {
    // Nothing here can tell a rewrite from a second commitment, and guessing would throw away
    // words somebody chose. The reader deletes whichever they did not mean.
    const reworded = "All I/O crosses a port. The domain imports no adapter.";
    const next = appendSeedLines(reworded, hexagonal);

    expect(next).toContain(reworded);
    expect(next).toContain(hexagonal[0]);
  });

  it("does not leave a blank line where the reader left a trailing newline", () => {
    expect(appendSeedLines("Ports are owned by the domain.\n\n", hexagonal)).toBe(
      ["Ports are owned by the domain.", ...hexagonal].join("\n"),
    );
  });
});

describe("CONVENTION_SEEDS", () => {
  it("offers concrete commitments rather than style names", () => {
    // A chip's own word ("Hexagonal") is a label on a button and never reaches the case. What
    // it writes is two or three sentences a review can hold a boundary against.
    expect(CONVENTION_SEEDS.map((seed) => seed.name)).toEqual([
      "DDD",
      "Hexagonal",
      "Vertical slice",
      "Layered",
    ]);
    for (const seed of CONVENTION_SEEDS) {
      expect(seed.lines.length).toBeGreaterThanOrEqual(2);
      expect(seed.lines.length).toBeLessThanOrEqual(3);
      for (const line of seed.lines) expect(line).not.toContain("\n");
    }
  });
});
