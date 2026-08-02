/**
 * Which repository and which case a run will actually use.
 *
 * These are the two inputs that decide the answer — the same abstraction is right against
 * one case and wrong against another — so a run started against something other than what
 * the page showed as chosen is the worst kind of wrong: the report is internally consistent
 * and about the wrong thing. What remains here is the button's decision: a case is no
 * longer picked on the start step, it is brought by an example or written by the review.
 */

import { describe, expect, it } from "vitest";

import {
  EMPTY_SELECTION,
  isReady,
  runIntent,
  type StartSelection,
} from "./start-selection";

function selection(overrides: Partial<StartSelection> = {}): StartSelection {
  return { ...EMPTY_SELECTION, ...overrides };
}

describe("what pressing Run does", () => {
  it("reviews the chosen case when an example brought one", () => {
    const chosen = selection({ repositoryRoot: "/repos/warehouse", caseId: "case-1" });

    expect(runIntent(chosen, true)).toEqual({
      kind: "against-case",
      caseId: "case-1",
      repositoryRoot: "/repos/warehouse",
    });
  });

  it("starts from the repository when no case is chosen", () => {
    const chosen = selection({ repositoryRoot: "/repos/warehouse" });

    // The path for someone who has not written a case: an empty one is opened about the
    // repository and the review's own questions fill it in.
    expect(runIntent(chosen, true)).toEqual({
      kind: "from-repository",
      repositoryRoot: "/repos/warehouse",
    });
  });

  it("refuses to run without a repository, however much else is chosen", () => {
    expect(runIntent(selection(), true)).toBeNull();
    expect(runIntent(selection({ caseId: "case-1" }), true)).toBeNull();
    expect(runIntent(selection({ path: "/repos/typed-but-not-indexed" }), true)).toBeNull();
  });

  it("refuses to run without a model, however much else is chosen", () => {
    const chosen = selection({ repositoryRoot: "/repos/warehouse", caseId: "case-1" });

    expect(isReady(chosen, false)).toBe(false);
    expect(runIntent(chosen, false)).toBeNull();
  });

  it("never disagrees with the button's own enabled state", () => {
    // The two are derived from one selection, so a run cannot be startable while the
    // intent is impossible, or refused while the button says it is ready.
    const states = [
      selection(),
      selection({ caseId: "case-1" }),
      selection({ path: "/repos/typed" }),
      selection({ repositoryRoot: "/repos/warehouse" }),
      selection({ repositoryRoot: "/repos/warehouse", caseId: "case-1" }),
    ];

    for (const state of states) {
      for (const hasModel of [true, false]) {
        expect(isReady(state, hasModel)).toBe(runIntent(state, hasModel) !== null);
      }
    }
  });
});
