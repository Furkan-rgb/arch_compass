/**
 * The surface that turns a review's questions into the user's own case revision.
 *
 * Every test here defends one half of invariant 25: the advisor supplies the question, the
 * user supplies the answer, and only the answer enters the case — as a revision they have
 * seen before it saves. Nothing here may pre-fill an answer, save an unseen one, or touch a
 * part of the case nobody wrote in.
 *
 * The pair is what makes that checkable rather than merely stated. While an answer was
 * composed into a line before saving, the thing recorded was neither half: it was this
 * component's sentence, built from the advisor's subject and the user's reply, and a test
 * could only assert that the composition was the one intended. Now the question is the
 * review's words and the answer is the reader's, and each assertion below is about one of
 * those two rather than about a join.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ANSWER_DRAFTS, draftKey, saveDrafts, storedDrafts } from "./question-drafts";
import { OpenQuestions } from "./review-questions";
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

const WITH_OPTIONS: OpenQuestion = {
  ...VENDOR,
  answer_options: ["A second warehouse is planned this year", "No second warehouse is coming"],
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

afterEach(() => window.localStorage.clear());

function renderQuestions(overrides: Partial<Parameters<typeof OpenQuestions>[0]> = {}) {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const view = render(
    <OpenQuestions
      reviewId="rev-1"
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
  return Object.assign(onSubmit, { container: view.container, unmount: view.unmount });
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

  it("shows the pair that will enter the case before it saves", () => {
    const submit = renderQuestions();
    const container = submit.container;

    fireEvent.change(answerBox(), {
      target: { value: "A second warehouse arrives next quarter." },
    });
    goToReview();

    // Scoped to the preview, because the field name also labels the box it was typed into
    // — and it is the preview that has to carry it. The diff is what makes the button
    // honest: saving without the user seeing what enters their case is what §6C.4 forbids.
    const preview = container.querySelector("[data-slot='answer-preview']");
    expect(preview).not.toBeNull();
    expect(preview?.textContent).toContain("1 of 2 answered");
    expect(preview?.textContent).toContain("expected_future_changes");
    // Both halves, each attributed. The question is the review's and is printed as it was
    // asked; the answer is the reader's and is exactly what they typed — no line composed
    // from the two, which is what used to show them the question twice on one screen.
    expect(preview?.textContent).toContain("Asked: Is a second warehouse actually planned?");
    expect(
      (screen.getByLabelText("Your answer to Q-1") as HTMLTextAreaElement).value,
    ).toBe("A second warehouse arrives next quarter.");
    // Nothing restates the question in the reader's voice, which is what the composed line did.
    expect(preview?.textContent).not.toContain("Whether a second warehouse is coming —");
    // And only the field this question bears on: an unanswered question puts nothing in
    // front of the reader.
    expect(preview?.textContent).not.toContain("assumptions");
  });

  it("saves the answer as typed, and edits in the preview are the same answer", () => {
    const onSubmit = renderQuestions();

    fireEvent.change(answerBox(), {
      target: { value: "A second warehouse arrives." },
    });
    goToReview();
    // One box, one value. The preview edits the answer itself rather than a line derived
    // from it, so there is no second copy that could be the one that saves.
    fireEvent.change(screen.getByLabelText("Your answer to Q-1"), {
      target: { value: "A second warehouse opens in Utrecht next quarter." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));

    expect(onSubmit.mock.calls[0][0]).toEqual([
      {
        question_reference: "Q-1",
        recorded_text: "A second warehouse opens in Utrecht next quarter.",
      },
    ]);
    // And the question box shows it too, because it is the same answer.
    goTo(1);
    expect(answerBox().value).toBe("A second warehouse opens in Utrecht next quarter.");
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
    // The reference and the answer, and nothing else. The question half of each pair is taken
    // from the review's own report by the workspace, and so is the force the answer carries —
    // a client that could supply either could put words in a review's mouth, or give an answer
    // a weight its question never asked for.
    expect(onSubmit.mock.calls[0][0]).toEqual([
      { question_reference: "Q-1", recorded_text: "A second warehouse arrives." },
      { question_reference: "Q-2", recorded_text: "They are the same fact." },
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

/**
 * The answers, against the things that used to destroy them.
 *
 * An answer here is the highest-effort input in the product — a sentence about the reader's own
 * project that nothing else in the workspace knows — and it lived in component state alone, so
 * a reload, a second tab or a citation followed and come back from ended in five empty boxes.
 * Every test below is one of those ordinary movements, and none of them may cost a word.
 *
 * Nothing here weakens invariant 25. A draft is only ever what the reader typed, and it is put
 * back into the same box facing the same preview: what saves is still the answer they can see.
 */
describe("OpenQuestions and what has been typed but not yet saved", () => {
  it("puts back what was being written when the page went away", () => {
    const first = renderQuestions();
    fireEvent.change(answerBox(), { target: { value: "A second warehouse arrives." } });
    first.unmount();

    // The same review, opened again — a reload, a tab restored, a step come back to.
    renderQuestions();

    expect(answerBox().value).toBe("A second warehouse arrives.");
  });

  it("shows a restored answer as an answer, not as a box that happens to have text in it", () => {
    saveDrafts(ANSWER_DRAFTS, "rev-1", { "Q-2": "They are the same fact." });

    renderQuestions();

    // The row of steps and the count are how a reader sees where they got to, so a draft that
    // came back has to be visible from the first screen rather than found by walking the row.
    expect(screen.getByText("1 of 2 answered")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /^Question 2 of 2, answered/ }),
    ).toBeTruthy();
  });

  it("keeps a draft under the review it was written for", () => {
    const view = render(
      <OpenQuestions
        reviewId="rev-1"
        questions={[VENDOR, CONSTANTS]}
        nextRevision={2}
        pending={false}
        disabled={false}
        error={null}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        renderCitations={() => null}
      />,
    );
    fireEvent.change(answerBox(), { target: { value: "A second warehouse arrives." } });

    // The reader's own page swaps one review for another under this component — that is what
    // starting a second pass does — and an answer about the first review must not be shown
    // against the second's questions, nor saved under its key.
    view.rerender(
      <OpenQuestions
        reviewId="rev-2"
        questions={[VENDOR, CONSTANTS]}
        nextRevision={2}
        pending={false}
        disabled={false}
        error={null}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        renderCitations={() => null}
      />,
    );

    expect(answerBox().value).toBe("");
    expect(storedDrafts(ANSWER_DRAFTS, "rev-2")).toEqual({});
    expect(storedDrafts(ANSWER_DRAFTS, "rev-1")).toEqual({
      "Q-1": "A second warehouse arrives.",
    });
  });

  it("forgets a draft once the workspace has recorded the answer", async () => {
    renderQuestions();

    fireEvent.change(answerBox(), { target: { value: "A second warehouse arrives." } });
    goToReview();
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));

    // Recorded is recorded: the case holds the pair now, and a draft that outlived it would
    // come back as an unsaved answer to a question that has already been answered.
    await waitFor(() =>
      expect(window.localStorage.getItem(draftKey(ANSWER_DRAFTS, "rev-1"))).toBeNull(),
    );
    // The box keeps it while the second pass starts, though. Emptying it under the reader at
    // the moment their answer was accepted would read as it being thrown away.
    goTo(1);
    expect(answerBox().value).toBe("A second warehouse arrives.");
  });

  it("keeps every draft when the workspace refuses the answers", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("The workspace refused it."));
    renderQuestions({ onSubmit });

    fireEvent.change(answerBox(), { target: { value: "A second warehouse arrives." } });
    goToReview();
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    // A save that failed is the case a reader most needs their words back for, so the failure
    // path is the one that must not clear anything.
    expect(storedDrafts(ANSWER_DRAFTS, "rev-1")).toEqual({
      "Q-1": "A second warehouse arrives.",
    });
  });

  it("says the work is kept, where it is", () => {
    renderQuestions();

    // The reader has no way to know a box will still hold their sentence tomorrow, and it is
    // the reason they may leave this page at all — which is also why nothing here interrupts
    // them on the way out.
    expect(screen.getByText(/what you write is kept in this browser/)).toBeTruthy();
  });

  it("promises nothing where the browser will not keep it", () => {
    // A private window that refuses to store. The feature degrades to what this page did
    // before drafts existed; the sentence must degrade with it rather than tell the reader
    // their answers are safe on a machine that is about to lose them.
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("The operation is insecure.");
    });

    renderQuestions();

    expect(screen.queryByText(/kept in this browser/)).toBeNull();
    expect(screen.getByText(/The verdicts above rest on these/)).toBeTruthy();
    vi.restoreAllMocks();
  });

  it("remembers only what has actually been written", () => {
    const view = renderQuestions();

    fireEvent.change(answerBox(), { target: { value: "A second warehouse arrives." } });
    fireEvent.change(answerBox(), { target: { value: "" } });
    view.unmount();

    // A question opened and left blank is a question skipped, which is a normal way to use
    // this — and it leaves nothing behind to be restored or cleaned up.
    expect(window.localStorage.getItem(draftKey(ANSWER_DRAFTS, "rev-1"))).toBeNull();
  });
});

describe("OpenQuestions and the answers a review can offer", () => {
  it("shows options only where the review offered them", () => {
    renderQuestions({ questions: [WITH_OPTIONS, CONSTANTS] });

    expect(screen.getByRole("group", { name: "Offered answers" })).toBeTruthy();
    goTo(2);
    expect(screen.queryByRole("group", { name: "Offered answers" })).toBeNull();
  });

  it("records a pressed option as the reader's own text, editable to the last moment", () => {
    const onSubmit = renderQuestions({ questions: [WITH_OPTIONS] });

    fireEvent.click(screen.getByRole("button", { name: "No second warehouse is coming" }));
    expect(answerBox().value).toBe("No second warehouse is coming");

    goToReview();
    fireEvent.click(screen.getByRole("button", { name: /^Continue/ }));
    expect(onSubmit).toHaveBeenCalledWith([
      { question_reference: "Q-1", recorded_text: "No second warehouse is coming" },
    ]);
  });

  it("lets an offer be declined by pressing it again", () => {
    renderQuestions({ questions: [WITH_OPTIONS] });
    const option = screen.getByRole("button", { name: "No second warehouse is coming" });

    fireEvent.click(option);
    expect(option.getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(option);
    expect(option.getAttribute("aria-pressed")).toBe("false");
    expect(answerBox().value).toBe("");
  });

  it("treats an edited option as the reader's words, no longer any option's", () => {
    renderQuestions({ questions: [WITH_OPTIONS] });
    const option = screen.getByRole("button", { name: "No second warehouse is coming" });

    fireEvent.click(option);
    fireEvent.change(answerBox(), {
      target: { value: "No second warehouse is coming, and none is being evaluated." },
    });

    expect(option.getAttribute("aria-pressed")).toBe("false");
  });

  it("never selects an option the reader has not pressed", () => {
    renderQuestions({ questions: [WITH_OPTIONS] });

    for (const name of WITH_OPTIONS.answer_options!) {
      expect(screen.getByRole("button", { name }).getAttribute("aria-pressed")).toBe("false");
    }
    expect(answerBox().value).toBe("");
  });
});
