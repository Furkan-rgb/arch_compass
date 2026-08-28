import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Review, ReviewConversation } from "../../api";
import { reviewFixture } from "../../test-fixtures";
import { AskBox, ConversationExchange } from "./conversation-thread";

/**
 * The composer, as a document rather than as a picture.
 *
 * jsdom applies no stylesheet and lays nothing out, so nothing here is a measurement and none
 * of it can see that the button looks as though it belongs to the field. What it *can* see is
 * the fact the look rests on — that the button is inside the element carrying the field's edge
 * rather than a sibling of it — and that is exactly the thing the previous arrangement got
 * wrong. The rectangles are `tests/browser/test_workspace.py`'s.
 *
 * The rest of this file is the behaviour the composer's own doc comment argues for and which
 * nothing anywhere asserted: which keystroke sends, which one does not, and what happens to a
 * reader's sentence when the request they sent it in fails.
 */

function draw(overrides: Partial<Parameters<typeof AskBox>[0]> = {}) {
  const onChange = vi.fn();
  const onAsk = vi.fn();
  render(
    <AskBox
      label="Question about this review"
      placeholder="How would the gateway finding be fixed?"
      pending={false}
      value=""
      onChange={onChange}
      onAsk={onAsk}
      {...overrides}
    />,
  );
  const area = screen.getByLabelText("Question about this review");
  return { area, box: area.parentElement as HTMLElement, onChange, onAsk };
}

describe("the ask composer", () => {
  /**
   * The whole of the redesign, said as a containment.
   *
   * The button used to be a `<Button>` inside a `<div className="flex justify-end">` that was a
   * *sibling* of the field, 8px below it — so no arrangement of classes could have made it read
   * as part of the thing it acts on, and this assertion is the one that fails on that markup.
   */
  it("puts the button inside the element that draws the field's edge", () => {
    const { area, box } = draw();
    const button = screen.getByRole("button", { name: "Ask" });

    expect(box).toContainElement(button);
    expect(box).toContainElement(area);
    // The edge, the ground and the radius are the field's recipe from `ui/field.tsx`, on the
    // box. A reader looking for the control is looking at this rectangle.
    expect(box.className).toContain("border-rule-control");
    expect(box.className).toContain("bg-control");
    expect(box.className).toContain("rounded-sm");
    // And the textarea inside it draws neither, or there would be two boxes again.
    expect(area.className).toContain("bg-transparent");
    expect(area.className).not.toMatch(/(?:^|\s)border(?:-|\s|$)/);
  });

  /**
   * `34.8rem` is derived — it is the width the answer above the composer is read at, which is
   * `ModelProse`'s `58ch` at 16px — and it only means anything if it caps the box a reader can
   * see. On an invisible wrapper it caps a rectangle nothing is drawn on, which is how the same
   * class list came to be measured against a font size no element on it declared.
   *
   * The number moved with the face: it was `38.5rem`, the round 616px just under the 617.12px
   * Onest's 0.665em zero put `58ch` at, and IBM Plex Sans's 0.600em brings the same declaration
   * to 556.80px — which `34.8rem` is exactly. The literal is asserted rather than derived here
   * on purpose, because what this test is about is *which element* carries the cap; the
   * derivation is checked in `ui/font.test-metrics.test.ts`, where the advance lives.
   */
  it("caps the box that is drawn, not a wrapper around it", () => {
    const { box } = draw();
    expect(box.className).toContain("max-w-[34.8rem]");
    expect(box.className).toContain("border-rule-control");
  });

  /**
   * The focus indicator is the product's one indicator, moved onto the box and not removed:
   * `ui/field.tsx` records what happened the last time a field declared `outline-none` with
   * nothing put back. Both halves are asserted, because either alone is the bug.
   */
  it("moves the focus ring onto the box and leaves it nowhere else", () => {
    const { area, box } = draw();
    expect(area.className).toContain("outline-none");
    expect(box.className).toContain("has-[textarea:focus-visible]:outline-2");
    expect(box.className).toContain("has-[textarea:focus-visible]:outline-ink");
  });

  /** The keyboard route is invisible unless something says so, and it is said to both readers. */
  it("says which key sends, in the field's own description", () => {
    const { area } = draw();
    const describedBy = area.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    const hint = document.getElementById(describedBy as string);
    expect(hint).not.toBeNull();
    expect(hint?.textContent).toMatch(/Enter/);
    expect(hint?.textContent).toMatch(/send/i);
  });

  /**
   * Three keystrokes, one of which is the reason the condition is three clauses.
   *
   * `isComposing` is the IME case: pressing Enter to commit a Japanese, Chinese or Korean
   * candidate used to send the half-composed question to an agent. It is asserted here because
   * it is invisible in every other way — nothing on screen distinguishes the press that commits
   * a candidate from the press that sends.
   */
  it("sends on Enter, and does not on Shift+Enter or mid-composition", () => {
    const { area, onAsk } = draw({ value: "Why is the gateway held?" });

    fireEvent.keyDown(area, { key: "Enter", shiftKey: true });
    expect(onAsk).not.toHaveBeenCalled();

    fireEvent.keyDown(area, { key: "Enter", isComposing: true });
    expect(onAsk).not.toHaveBeenCalled();

    fireEvent.keyDown(area, { key: "Enter" });
    expect(onAsk).toHaveBeenCalledWith("Why is the gateway held?");
  });

  /**
   * The rule the box's own doc comment is written around: an ask runs an agent and has no
   * timeout, so the words stay until it lands and stay for good if it does not. Cleared on the
   * press, a failure took the reader's sentence off the screen and offered to resend it.
   */
  it("keeps the words until the ask lands, and clears them only then", async () => {
    let settle: (() => void) | undefined;
    const onAsk = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          settle = resolve;
        }),
    );
    const { area, onChange } = draw({ value: "Why is the gateway held?", onAsk });

    fireEvent.keyDown(area, { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
    settle?.();
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith(""));
  });

  /** The other half, and the half that cost somebody a paragraph: a rejection keeps them. */
  it("keeps the words in the box when the ask fails", async () => {
    const onAsk = vi.fn(() => Promise.reject(new Error("the agent gave up")));
    const { area, onChange } = draw({ value: "Why is the gateway held?", onAsk });

    fireEvent.keyDown(area, { key: "Enter" });
    await vi.waitFor(() => expect(onAsk).toHaveBeenCalled());
    expect(onChange).not.toHaveBeenCalled();
  });

  /**
   * The pending state is a spinner in place of the word, and it has to survive being moved into
   * the rail. `Spinner` carries its own accessible name, so the control is still askable for
   * while it is working rather than becoming a button with no name at all.
   */
  it("swaps the word for a spinner while an ask is in flight", () => {
    draw({ value: "Why is the gateway held?", pending: true });
    expect(screen.queryByRole("button", { name: "Ask" })).not.toBeInTheDocument();
    const working = screen.getByRole("button", { name: "Working" });
    expect(working).toBeDisabled();
  });

  /** Nothing to send is nothing to press, which is also what keeps the accent off an empty box. */
  it("does not offer to send an empty box", () => {
    draw({ value: "   " });
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
  });
});

/**
 * A citation the model wrote into the middle of its answer.
 *
 * The identifier here is shaped like a real one — `stable_id`'s prefix and twenty-four
 * characters of digest — because that shape is the grammar. The rest of this file's fixtures
 * use `candidate-1`, which deliberately is not one: a hyphenated test id must never be taken
 * for a key and drawn as a link.
 */
const RECORDER = "candidate_3dcc1d5ac92ac0b5baf6e2e0";

function citingReview(): Review {
  const review = reviewFixture();
  const finding = review.findings[1];
  finding.candidate.id = RECORDER;
  finding.candidate.participants = [
    {
      qualified_name: "persistence.ports.CaseSnapshotRecorder",
      role: "source",
      node_id: "node-recorder",
    },
  ];
  finding.candidate.summary = "A protocol with one implementation and no test bound to it";
  return review;
}

function exchange(text: string): ReviewConversation["messages"][number] {
  return {
    question: "Why is this one waiting on me?",
    answer: {
      text,
      supporting_candidate_ids: [],
      investigation: null,
      suggested_answer: "",
      model_identity: "anthropic/claude-sonnet-5",
    },
    asked_at: "2026-01-01T00:00:00Z",
  };
}

describe("a finding cited inside an answer", () => {
  const answer = `Finding [${RECORDER}] is held because intent cannot be read from the code.`;

  it("reads as the finding's name, and opens its row", () => {
    const onOpen = vi.fn();
    render(
      <ConversationExchange message={exchange(answer)} review={citingReview()} onOpen={onOpen} />,
    );

    // The key is gone from the sentence entirely, which is the whole of the defect.
    expect(screen.queryByText(/candidate_/)).toBeNull();
    const reference = screen.getByRole("button", { name: "CaseSnapshotRecorder" });
    expect(reference.getAttribute("title")).toContain("persistence.ports.CaseSnapshotRecorder");

    fireEvent.click(reference);
    expect(onOpen).toHaveBeenCalledWith(RECORDER);
  });

  /**
   * The clarification panel draws this same exchange with nothing to open — a reader stuck on
   * a question is not on the docket — so the reference gives up the affordance rather than
   * keeping a dead one.
   */
  it("keeps the name where the surface has nowhere to open it", () => {
    const { container } = render(
      <ConversationExchange message={exchange(answer)} review={citingReview()} />,
    );

    expect(screen.queryByRole("button", { name: "CaseSnapshotRecorder" })).toBeNull();
    expect(container.textContent).toContain("Finding CaseSnapshotRecorder is held");
  });
});
