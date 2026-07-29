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

import { OpenQuestions, composeCaseLine } from "./review-questions";
import type { OpenQuestion } from "./types";

const VENDOR: OpenQuestion = {
  reference: "Q-1",
  what_the_review_saw:
    "StockLedger and WarehouseFeed both wrap one supplier. The case says nothing about a second.",
  unknown: "whether a second warehouse is coming",
  why_it_matters: "Two verdicts move on this.",
  question: "Is a second warehouse actually planned?",
  answer_belongs_in: "expected_future_changes",
  supporting_references: ["BR-001", "BR-005"],
};

const CONSTANTS: OpenQuestion = {
  reference: "Q-2",
  what_the_review_saw: "BATCH_SIZE is declared in two modules with the same value.",
  unknown: "whether the two batch sizes are one fact",
  why_it_matters: "One verdict moves on this.",
  question: "Are the two BATCH_SIZE constants one fact?",
  answer_belongs_in: "assumptions",
  supporting_references: ["BR-003"],
};

function renderQuestions(overrides: Partial<Parameters<typeof OpenQuestions>[0]> = {}) {
  const onSubmit = vi.fn();
  const view = render(
    <OpenQuestions
      questions={[VENDOR, CONSTANTS]}
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

/** The answer box for whichever question is on screen. One is shown at a time. */
function answerBox(): HTMLTextAreaElement {
  return screen.getAllByRole("textbox")[0] as HTMLTextAreaElement;
}

/** Jump to a step by its number in the row, the way a reader revisits one. */
function goTo(step: number) {
  fireEvent.click(screen.getByRole("button", { name: new RegExp(`^Question ${step} `) }));
}

function goToReview() {
  fireEvent.click(screen.getByRole("button", { name: "Review" }));
}

describe("composeCaseLine", () => {
  it("carries the subject into the line, so the answer still means something alone", () => {
    // The failure this exists to stop: "They shouldn't rely on it" recorded into the case,
    // where nothing downstream ever sees the question and "it" refers to nothing.
    expect(composeCaseLine(VENDOR, "They shouldn't rely on it")).toBe(
      "Whether a second warehouse is coming — They shouldn't rely on it.",
    );
  });

  it("leaves the answer's own spelling alone", () => {
    // Lowercasing to fix the mid-sentence capital would damage the identifiers people
    // actually write here. A stray capital is the cheaper mistake, and the box is editable.
    expect(composeCaseLine(CONSTANTS, "SQLite is the permanent choice")).toContain(
      "— SQLite is the permanent choice.",
    );
  });

  it("does not double a terminator the answer already has", () => {
    expect(composeCaseLine(VENDOR, "No, and none is planned.")).toBe(
      "Whether a second warehouse is coming — No, and none is planned.",
    );
    expect(composeCaseLine(VENDOR, "Is it? Nobody has said.")).toMatch(/said\.$/);
  });

  it("has nothing to compose from an unanswered question", () => {
    expect(composeCaseLine(VENDOR, "   ")).toBe("");
  });
});

describe("OpenQuestions", () => {
  it("asks one question at a time, with what was seen and which verdicts move", () => {
    renderQuestions();

    expect(screen.getByText("Is a second warehouse actually planned?")).toBeTruthy();
    expect(screen.getByText("BR-001, BR-005")).toBeTruthy();
    // What was seen, which is the part the reader cannot supply for themselves. `unknown`
    // is not shown: it restated the question and cost a line to do it.
    expect(screen.getByText(/StockLedger and WarehouseFeed both wrap one supplier/)).toBeTruthy();
    expect(screen.queryByText("whether a second warehouse is coming")).toBeNull();
    // The second question is not on screen. Each of these takes real thought about the
    // reader's own project, and five at once reads as a form to get through.
    expect(screen.queryByText("Are the two BATCH_SIZE constants one fact?")).toBeNull();
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    // Never pre-filled. The advisor supplies the question and nothing else (§6C.5).
    expect(answerBox().value).toBe("");
  });

  it("keeps every step reachable, and what was typed while moving between them", () => {
    renderQuestions();

    fireEvent.change(answerBox(), { target: { value: "A second warehouse arrives." } });
    goTo(2);
    expect(screen.getByText("Are the two BATCH_SIZE constants one fact?")).toBeTruthy();
    expect(answerBox().value).toBe("");

    // Straight back to the first, not by walking backwards through the others: revisiting
    // is the point, and an answer is not a thing you should have to retype to change.
    goTo(1);
    expect(answerBox().value).toBe("A second warehouse arrives.");
  });

  it("will not save until something has been written", () => {
    renderQuestions();
    goToReview();

    const submit = screen.getByRole("button", { name: /Answer at least one/ });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Nothing is answered yet/)).toBeTruthy();
  });

  it("offers no way to save from the middle of a question", () => {
    renderQuestions();

    fireEvent.change(answerBox(), { target: { value: "A second warehouse arrives." } });

    // Submitting is the one act here that cannot be revisited, so it does not sit under a
    // question the reader is still in the middle of.
    expect(screen.queryByRole("button", { name: /Continue/ })).toBeNull();
    goToReview();
    expect(screen.getByRole("button", { name: /Continue/ })).toBeTruthy();
  });

  it("shows what will enter the case before it saves", () => {
    const submit = renderQuestions();
    const container = submit.container;

    fireEvent.change(answerBox(), {
      target: { value: "A second warehouse arrives next quarter." },
    });
    goToReview();

    // Scoped to the preview, because the field name also labels the box it was typed into
    // — and it is the preview that has to carry it. The diff is what makes the button
    // honest: saving without the user seeing what enters their case is what §6C.4 forbids.
    const preview = container.querySelector(".questions__preview");
    expect(preview).not.toBeNull();
    expect(preview?.textContent).toContain("1 of 2 answered");
    expect(preview?.textContent).toContain("expected_future_changes");
    // The composed line, not the raw reply: what is shown has to be what will be saved.
    expect(
      (screen.getByLabelText("What Q-1 adds to expected_future_changes") as HTMLTextAreaElement)
        .value,
    ).toBe("Whether a second warehouse is coming — A second warehouse arrives next quarter.");
    // And only that list: an unanswered question puts nothing in front of the reader.
    expect(preview?.textContent).not.toContain("assumptions");
  });

  it("saves the line the reader edited, not the one that was composed", () => {
    const onSubmit = renderQuestions();

    fireEvent.change(answerBox(), {
      target: { value: "A second warehouse arrives." },
    });
    goToReview();
    fireEvent.change(screen.getByLabelText("What Q-1 adds to expected_future_changes"), {
      target: { value: "A second warehouse opens in Utrecht next quarter." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));

    expect(onSubmit.mock.calls[0][0]).toEqual([
      {
        question_reference: "Q-1",
        recorded_text: "A second warehouse opens in Utrecht next quarter.",
      },
    ]);
  });

  it("puts the suggested line back when an edit is abandoned", () => {
    renderQuestions();

    fireEvent.change(answerBox(), {
      target: { value: "A second warehouse arrives." },
    });
    goToReview();
    const composed = screen.getByLabelText(
      "What Q-1 adds to expected_future_changes",
    ) as HTMLTextAreaElement;
    fireEvent.change(composed, { target: { value: "Something else entirely." } });
    fireEvent.click(screen.getByRole("button", { name: "Reset to suggested" }));

    expect(
      (screen.getByLabelText("What Q-1 adds to expected_future_changes") as HTMLTextAreaElement)
        .value,
    ).toBe("Whether a second warehouse is coming — A second warehouse arrives.");
  });

  it("batches several answers into one revision", () => {
    const onSubmit = renderQuestions();

    fireEvent.change(answerBox(), { target: { value: "A second warehouse arrives." } });
    fireEvent.click(screen.getByRole("button", { name: "Next question" }));
    fireEvent.change(answerBox(), { target: { value: "They are the same fact." } });
    // The last question offers the preview by name rather than another "next".
    fireEvent.click(screen.getByRole("button", { name: "Review what will be recorded" }));
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    // One submission carrying both answers, not one each: answering what you know in one
    // sitting is a single act of correcting the record, and it becomes one revision.
    //
    // Keyed by question and carrying no destination. Which list an answer joins is the
    // question's property, read from the review by the workspace — a client that could name
    // it could route an answer into a list its question never mentioned.
    expect(onSubmit.mock.calls[0][0]).toEqual([
      {
        question_reference: "Q-1",
        recorded_text: "Whether a second warehouse is coming — A second warehouse arrives.",
      },
      {
        question_reference: "Q-2",
        recorded_text: "Whether the two batch sizes are one fact — They are the same fact.",
      },
    ]);
  });

  it("still reads when the loop cannot be walked, and refuses to save", () => {
    // No repository indexed means saving cannot run a new review. The questions are a
    // finding in their own right, so they stay readable and say why they are inert.
    renderQuestions({ disabled: true });

    expect(screen.getByText("Is a second warehouse actually planned?")).toBeTruthy();
    expect(answerBox().disabled).toBe(true);
    goToReview();
    expect(
      (screen.getByRole("button", { name: /Answer at least one/ }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("reports a failure to save rather than losing what was typed", () => {
    renderQuestions({ error: new Error("The workspace refused the revision.") });

    fireEvent.change(answerBox(), {
      target: { value: "A second warehouse arrives." },
    });
    goToReview();

    expect(screen.getByText("The workspace refused the revision.")).toBeTruthy();
    // Still there to be retried or edited, on the step where saving failed.
    goTo(1);
    expect(answerBox().value).toBe("A second warehouse arrives.");
  });
});
