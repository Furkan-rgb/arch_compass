/**
 * Which repository a run will actually use.
 *
 * A run started against something other than what the page showed as chosen is the worst
 * kind of wrong: the report is internally consistent and about the wrong thing. What
 * remains here is the button's decision — every run starts from a repository and an empty
 * case; the review's questions write the case.
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
  it("starts from the repository, whose review writes the case", () => {
    const chosen = selection({ repositoryRoot: "/repos/warehouse" });

    expect(runIntent(chosen, true)).toEqual({
      kind: "from-repository",
      repositoryRoot: "/repos/warehouse",
    });
  });

  it("refuses to run without a repository, however much else is set", () => {
    expect(runIntent(selection(), true)).toBeNull();
    expect(runIntent(selection({ path: "/repos/typed-but-not-indexed" }), true)).toBeNull();
  });

  it("refuses to run without a model", () => {
    const chosen = selection({ repositoryRoot: "/repos/warehouse" });

    expect(isReady(chosen, false)).toBe(false);
    expect(runIntent(chosen, false)).toBeNull();
  });

  it("never disagrees with the button's own enabled state", () => {
    // The two are derived from one selection, so a run cannot be startable while the
    // intent is impossible, or refused while the button says it is ready.
    const states = [
      selection(),
      selection({ path: "/repos/typed" }),
      selection({ repositoryRoot: "/repos/warehouse" }),
    ];

    for (const state of states) {
      for (const hasModel of [true, false]) {
        expect(isReady(state, hasModel)).toBe(runIntent(state, hasModel) !== null);
      }
    }
  });
});
