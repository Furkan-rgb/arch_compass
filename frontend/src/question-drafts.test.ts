/**
 * What a half-written answer is worth, and what happens to it when the browser refuses to help.
 *
 * These are the tests for the mechanism rather than for the surface: the surface's own tests
 * check that a reader gets their words back, and these check the two things that are invisible
 * from there — that one review's drafts can never be read as another's, and that a browser
 * with no usable storage produces exactly the behaviour this product had before drafts
 * existed. A private window that throws on `localStorage` must lose a draft, not a page.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ANSWER_DRAFTS,
  DISCUSSION_DRAFTS,
  draftKey,
  dropDrafts,
  saveDrafts,
  storedDrafts,
} from "./question-drafts";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

/** Take `localStorage` away the way a locked-down browser does: by throwing on the read. */
function withoutStorage(): () => void {
  const original = Object.getOwnPropertyDescriptor(window, "localStorage");
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    get() {
      throw new Error("The operation is insecure.");
    },
  });
  return () => {
    if (original) Object.defineProperty(window, "localStorage", original);
  };
}

describe("question drafts", () => {
  it("keeps one review's answers apart from another's", () => {
    saveDrafts(ANSWER_DRAFTS, "rev-1", { "Q-1": "A second warehouse arrives." });
    saveDrafts(ANSWER_DRAFTS, "rev-2", { "Q-1": "Nothing of the sort is planned." });

    // The same `Q-1` in both, because a question reference is only stable inside the review
    // that asked it. A single map keyed by reference alone would have shown one review's
    // reader the other's answer.
    expect(storedDrafts(ANSWER_DRAFTS, "rev-1")).toEqual({
      "Q-1": "A second warehouse arrives.",
    });
    expect(storedDrafts(ANSWER_DRAFTS, "rev-2")).toEqual({
      "Q-1": "Nothing of the sort is planned.",
    });
  });

  it("keeps an answer apart from a question asked about it", () => {
    saveDrafts(ANSWER_DRAFTS, "rev-1", { "Q-1": "A second warehouse arrives." });
    saveDrafts(DISCUSSION_DRAFTS, "rev-1", { "Q-1": "What does this even mean?" });

    // Only the first of these may ever reach the case. Sharing a key would have put the
    // reader's confusion into the box that becomes a revision.
    expect(storedDrafts(ANSWER_DRAFTS, "rev-1")["Q-1"]).toBe("A second warehouse arrives.");
    expect(storedDrafts(DISCUSSION_DRAFTS, "rev-1")["Q-1"]).toBe("What does this even mean?");
  });

  it("stores nothing for a question that was only opened", () => {
    saveDrafts(ANSWER_DRAFTS, "rev-1", { "Q-1": "", "Q-2": "   " });

    // A row per review anyone ever looked at would outlive every review in the workspace, and
    // an empty map read back says exactly what no map says.
    expect(window.localStorage.getItem(draftKey(ANSWER_DRAFTS, "rev-1"))).toBeNull();
  });

  it("forgets the questions that were answered and keeps the ones that were not", () => {
    saveDrafts(ANSWER_DRAFTS, "rev-1", {
      "Q-1": "A second warehouse arrives.",
      "Q-2": "Still thinking about this one.",
    });

    dropDrafts(ANSWER_DRAFTS, "rev-1", ["Q-1"]);

    expect(storedDrafts(ANSWER_DRAFTS, "rev-1")).toEqual({
      "Q-2": "Still thinking about this one.",
    });
  });

  it("drops the key entirely once every draft is recorded", () => {
    saveDrafts(ANSWER_DRAFTS, "rev-1", { "Q-1": "A second warehouse arrives." });

    dropDrafts(ANSWER_DRAFTS, "rev-1", ["Q-1"]);

    expect(window.localStorage.getItem(draftKey(ANSWER_DRAFTS, "rev-1"))).toBeNull();
  });

  it("reads back nothing from a value it did not write", () => {
    // This value survives deploys, so a shape from an older build — or one written by hand —
    // has to fail as "no draft" rather than reach a textarea as something that is not text.
    window.localStorage.setItem(draftKey(ANSWER_DRAFTS, "rev-1"), "not json at all");
    expect(storedDrafts(ANSWER_DRAFTS, "rev-1")).toEqual({});

    window.localStorage.setItem(draftKey(ANSWER_DRAFTS, "rev-2"), '["Q-1"]');
    expect(storedDrafts(ANSWER_DRAFTS, "rev-2")).toEqual({});

    window.localStorage.setItem(
      draftKey(ANSWER_DRAFTS, "rev-3"),
      '{"Q-1": {"text": "typed"}, "Q-2": "typed"}',
    );
    expect(storedDrafts(ANSWER_DRAFTS, "rev-3")).toEqual({ "Q-2": "typed" });
  });

  it("degrades to no memory at all where the browser refuses storage", () => {
    const restore = withoutStorage();
    try {
      // Not an error to report and not a thrown exception to render: a reader in a private
      // window gets the product as it was before drafts existed, which is a reload that loses
      // what they typed and nothing worse.
      expect(() => saveDrafts(ANSWER_DRAFTS, "rev-1", { "Q-1": "typed" })).not.toThrow();
      expect(() => dropDrafts(ANSWER_DRAFTS, "rev-1", ["Q-1"])).not.toThrow();
      expect(storedDrafts(ANSWER_DRAFTS, "rev-1")).toEqual({});
    } finally {
      restore();
    }
  });

  it("degrades the same way where the write itself is refused", () => {
    // The other half of a locked-down browser: reading works and writing throws, which is what
    // a full quota looks like as well.
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("The quota has been exceeded.");
    });

    expect(() => saveDrafts(ANSWER_DRAFTS, "rev-1", { "Q-1": "typed" })).not.toThrow();
    expect(storedDrafts(ANSWER_DRAFTS, "rev-1")).toEqual({});
  });
});
