/**
 * The surface that turns a review's questions into the user's own case revision.
 *
 * Every test here defends one half of invariant 25: the advisor supplies the question, the
 * user supplies the answer, and only the answer enters the case — as a revision they have
 * seen before it saves. Nothing here may pre-fill an answer, save an unseen one, or touch a
 * part of the case nobody wrote in.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OpenQuestions, composeAnswerUpdate, groupByField } from "./review-questions";
import type { ArchitectureCase, OpenQuestion } from "./types";

const VENDOR: OpenQuestion = {
  reference: "Q-1",
  unknown: "The case does not say whether a second warehouse is coming.",
  why_it_matters: "Two verdicts move on this.",
  question: "Is a second warehouse actually planned?",
  answer_belongs_in: "expected_future_changes",
  supporting_references: ["BR-001", "BR-005"],
};

const CONSTANTS: OpenQuestion = {
  reference: "Q-2",
  unknown: "The case does not say whether the two batch sizes are one fact.",
  why_it_matters: "One verdict moves on this.",
  question: "Are the two BATCH_SIZE constants one fact?",
  answer_belongs_in: "assumptions",
  supporting_references: ["BR-003"],
};

const SNAPSHOT = {
  title: "Keeping stock in step with the warehouse",
  problem_statement: "Decide which boundaries earn their place.",
  desired_outcome: "A verdict per boundary.",
  expected_future_changes: ["An existing entry nobody touched."],
  non_goals: ["Writing stock levels back."],
  assumptions: [{ text: "The page limit is stable.", kind: "assumption" as const }],
} as unknown as ArchitectureCase;

function renderQuestions(overrides: Partial<Parameters<typeof OpenQuestions>[0]> = {}) {
  const onSubmit = vi.fn();
  const view = render(
    <OpenQuestions
      questions={[VENDOR, CONSTANTS]}
      snapshot={SNAPSHOT}
      nextRevision={2}
      pending={false}
      disabled={false}
      error={null}
      onSubmit={onSubmit}
      renderCitations={(references) => <span>{references.join(", ")}</span>}
      {...overrides}
    />,
  );
  return Object.assign(onSubmit, { container: view.container });
}

describe("composeAnswerUpdate", () => {
  it("appends to the lists it was answered into and touches nothing else", () => {
    const update = composeAnswerUpdate(SNAPSHOT, {
      expected_future_changes: ["A second warehouse arrives next quarter."],
    });

    expect(update.expected_future_changes).toEqual([
      "An existing entry nobody touched.",
      "A second warehouse arrives next quarter.",
    ]);
    // The whole point of composing an update rather than reusing the case form: a reader
    // who answered one question must not have their other lists rewritten.
    expect(update.non_goals).toBeUndefined();
    expect(update.assumptions).toBeUndefined();
    expect(update.title).toBeUndefined();
  });

  it("gives a statement the kind fixed by the list it joins", () => {
    const update = composeAnswerUpdate(SNAPSHOT, {
      assumptions: ["The two batch sizes are the same fact."],
      confirmed_facts: ["The digest is mailed, not served."],
    });

    // `kind` is set here because it is decided by which list the statement is in. Asking a
    // person to type it would be asking them to restate the form's own structure — and the
    // domain rejects a statement whose kind does not match its list.
    expect(update.assumptions).toEqual([
      { text: "The page limit is stable.", kind: "assumption" },
      { text: "The two batch sizes are the same fact.", kind: "assumption" },
    ]);
    expect(update.confirmed_facts).toEqual([
      { text: "The digest is mailed, not served.", kind: "fact" },
    ]);
  });

  it("ignores an answer that is only whitespace", () => {
    expect(composeAnswerUpdate(SNAPSHOT, { non_goals: ["   "] })).toEqual({});
  });
});

describe("groupByField", () => {
  it("merges answers that belong in the same list", () => {
    const grouped = groupByField(
      [VENDOR, { ...CONSTANTS, answer_belongs_in: "expected_future_changes" }],
      { "Q-1": "A second warehouse arrives.", "Q-2": "So does a third." },
    );

    expect(grouped).toEqual({
      expected_future_changes: ["A second warehouse arrives.", "So does a third."],
    });
  });

  it("drops a question left blank", () => {
    expect(groupByField([VENDOR, CONSTANTS], { "Q-1": "  " })).toEqual({});
  });
});

describe("OpenQuestions", () => {
  it("asks, says which verdicts move, and offers a box per question", () => {
    renderQuestions();

    expect(screen.getByText("Is a second warehouse actually planned?")).toBeTruthy();
    expect(screen.getByText("BR-001, BR-005")).toBeTruthy();
    expect(screen.getAllByRole("textbox")).toHaveLength(2);
    // Never pre-filled. The advisor supplies the question and nothing else (§6C.5).
    for (const box of screen.getAllByRole("textbox")) {
      expect((box as HTMLTextAreaElement).value).toBe("");
    }
  });

  it("will not save until something has been written", () => {
    renderQuestions();

    const submit = screen.getByRole("button");
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    expect(submit.textContent).toContain("Answer at least one");
  });

  it("shows what will enter the case before it saves", () => {
    const submit = renderQuestions();
    const container = submit.container;

    fireEvent.change(screen.getAllByRole("textbox")[0], {
      target: { value: "A second warehouse arrives next quarter." },
    });

    // Scoped to the preview, because the field name also labels the box it was typed into
    // — and it is the preview that has to carry it. The diff is what makes the button
    // honest: saving without the user seeing what enters their case is what §6C.4 forbids.
    const preview = container.querySelector(".questions__preview");
    expect(preview).not.toBeNull();
    expect(preview?.textContent).toContain("1 of 2 answered");
    expect(preview?.textContent).toContain("expected_future_changes");
    expect(preview?.textContent).toContain("+ A second warehouse arrives next quarter.");
    // And only that list: an unanswered question puts nothing in front of the reader.
    expect(preview?.textContent).not.toContain("assumptions");
  });

  it("batches several answers into one revision", () => {
    const onSubmit = renderQuestions();

    const [first, second] = screen.getAllByRole("textbox");
    fireEvent.change(first, { target: { value: "A second warehouse arrives." } });
    fireEvent.change(second, { target: { value: "They are the same fact." } });
    fireEvent.click(screen.getByRole("button"));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    // One revision carrying both answers, not one revision each: answering what you know
    // in one sitting is a single act of correcting the record.
    expect(onSubmit.mock.calls[0][0]).toEqual({
      expected_future_changes: [
        "An existing entry nobody touched.",
        "A second warehouse arrives.",
      ],
      assumptions: [
        { text: "The page limit is stable.", kind: "assumption" },
        { text: "They are the same fact.", kind: "assumption" },
      ],
    });
  });

  it("still reads when the loop cannot be walked, and refuses to save", () => {
    // No repository indexed means saving cannot run a new review. The questions are a
    // finding in their own right, so they stay readable and say why they are inert.
    renderQuestions({ disabled: true });

    expect(screen.getByText("Is a second warehouse actually planned?")).toBeTruthy();
    for (const box of screen.getAllByRole("textbox")) {
      expect((box as HTMLTextAreaElement).disabled).toBe(true);
    }
    expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
  });

  it("reports a failure to save rather than losing what was typed", () => {
    renderQuestions({ error: new Error("The workspace refused the revision.") });

    fireEvent.change(screen.getAllByRole("textbox")[0], {
      target: { value: "A second warehouse arrives." },
    });

    expect(screen.getByText("The workspace refused the revision.")).toBeTruthy();
    expect((screen.getAllByRole("textbox")[0] as HTMLTextAreaElement).value).toBe(
      "A second warehouse arrives.",
    );
  });
});
