/**
 * Discussing one open question, and the line it must not cross.
 *
 * The feature exists because a reader who does not understand what is being asked has no
 * way forward — so these check that they can ask, and that what comes back stays an offer.
 * A suggested phrasing fills the answer box when the reader presses the button and at no
 * other moment: invariant 25 is that only the user's answer enters the case, and a
 * discussion that pre-filled a box would have written one for them.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";
import { QuestionDiscussion } from "./question-discussion";
import type { OpenQuestion, ReviewConversation } from "./types";

const QUESTION: OpenQuestion = {
  reference: "Q-1",
  what_the_review_saw: "StockLedger and WarehouseFeed both wrap one supplier.",
  unknown: "whether a second warehouse is coming",
  why_it_matters: "Two verdicts move on this.",
  question: "Is a second warehouse actually planned?",
  answer_belongs_in: "expected_future_changes",
  supporting_references: ["BR-001"],
};

function thread(suggested: string): ReviewConversation {
  return {
    conversation_id: "rconv-1",
    review_id: "rev-1",
    case_id: "case-1",
    case_revision: 1,
    title: "Q-1: Is a second warehouse actually planned?",
    question_reference: "Q-1",
    messages: [
      {
        message_id: "rmsg-1",
        ordinal: 1,
        question: "What are you actually asking me?",
        answer: {
          answer: "Whether anyone has committed to a second supplier.",
          supporting_references: ["BR-001"],
          suggested_answer: suggested,
        },
        failure: "",
        asked_at: "2026-07-29T10:00:00Z",
      },
    ],
    created_at: "2026-07-29T10:00:00Z",
  } as unknown as ReviewConversation;
}

function renderDiscussion(conversations: ReviewConversation[]) {
  const onAdopt = vi.fn();
  vi.spyOn(api, "reviewConversations").mockResolvedValue(conversations);
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <QuestionDiscussion
        reviewId="rev-1"
        question={QUESTION}
        onAdopt={onAdopt}
        disabled={false}
      />
    </QueryClientProvider>,
  );
  return onAdopt;
}

afterEach(() => vi.restoreAllMocks());

describe("QuestionDiscussion", () => {
  it("stays closed until asked for, and says why someone would open it", () => {
    renderDiscussion([]);

    expect(screen.getByRole("button", { name: /Not sure what this is asking/ })).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("shows the turns already stored for this question", async () => {
    renderDiscussion([thread("")]);

    fireEvent.click(screen.getByRole("button", { name: /Not sure what this is asking/ }));

    expect(
      await screen.findByText("Whether anyone has committed to a second supplier."),
    ).toBeTruthy();
    expect(screen.getByText("What are you actually asking me?")).toBeTruthy();
  });

  it("offers a suggested phrasing without adopting it", async () => {
    const onAdopt = renderDiscussion([thread("A second warehouse opens next quarter.")]);

    fireEvent.click(screen.getByRole("button", { name: /Not sure what this is asking/ }));
    await screen.findByText("A second warehouse opens next quarter.");

    // Shown, and nothing more. The answer box is filled by the reader's click, never by
    // the suggestion arriving (invariant 25).
    expect(onAdopt).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Use this as my answer" }));

    expect(onAdopt).toHaveBeenCalledWith("A second warehouse opens next quarter.");
  });

  it("offers no button where the reply suggested nothing", async () => {
    renderDiscussion([thread("")]);

    fireEvent.click(screen.getByRole("button", { name: /Not sure what this is asking/ }));
    await screen.findByText("Whether anyone has committed to a second supplier.");

    expect(screen.queryByRole("button", { name: "Use this as my answer" })).toBeNull();
  });

  it("pins a new thread to the question it was opened from", async () => {
    const created = vi
      .spyOn(api, "createReviewConversation")
      .mockResolvedValue(thread(""));
    const [only] = thread("").messages ?? [];
    vi.spyOn(api, "streamReviewQuestion").mockResolvedValue(only as never);
    renderDiscussion([]);

    fireEvent.click(screen.getByRole("button", { name: /Not sure what this is asking/ }));
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "What does this mean?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    // Without `Q-1` the server opens a review-wide conversation, which a review still
    // waiting on answers refuses outright — and which would be shown the held verdicts.
    await waitFor(() =>
      expect(created).toHaveBeenCalledWith("rev-1", undefined, "Q-1"),
    );
  });
});
