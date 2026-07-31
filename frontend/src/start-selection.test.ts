/**
 * Which repository and which case a run will actually use.
 *
 * These are the two inputs that decide the answer — the same abstraction is right against
 * one case and wrong against another — so a run started against something other than what
 * the page showed as chosen is the worst kind of wrong: the report is internally consistent
 * and about the wrong thing. Every property here is about that: what a click selects, what
 * it leaves alone, and what the button does with the result.
 */

import { describe, expect, it } from "vitest";

import {
  EMPTY_SELECTION,
  applyRepositoryHint,
  chooseCase,
  chooseRepository,
  isReady,
  runIntent,
  type StartSelection,
} from "./start-selection";

const INDEXED = ["/repos/warehouse", "/repos/scheduler"];

const WAREHOUSE_CASE = { case_id: "case-1", repository_root: "/repos/warehouse" };
const SCHEDULER_CASE = { case_id: "case-2", repository_root: "/repos/scheduler" };
const UNINDEXED_CASE = { case_id: "case-3", repository_root: "/repos/not-yet" };
const ROOTLESS_CASE = { case_id: "case-4", repository_root: null };

function selection(overrides: Partial<StartSelection> = {}): StartSelection {
  return { ...EMPTY_SELECTION, ...overrides };
}

describe("choosing a case", () => {
  it("selects it, and fills the repository rail when that repository is indexed", () => {
    const next = chooseCase(selection(), WAREHOUSE_CASE, INDEXED);

    expect(next.caseId).toBe("case-1");
    // The case already answers the question the repository rail asks; asking again would
    // be asking the reader to repeat themselves.
    expect(next.repositoryRoot).toBe("/repos/warehouse");
  });

  it("offers an unindexed repository as a path rather than selecting it", () => {
    const next = chooseCase(selection(), UNINDEXED_CASE, INDEXED);

    expect(next.caseId).toBe("case-3");
    // Selecting it would claim a step that never happened: nothing has parsed that path.
    expect(next.repositoryRoot).toBeNull();
    expect(next.path).toBe("/repos/not-yet");
  });

  it("offers the repository of the case chosen last, not the first one to name any", () => {
    const first = chooseCase(selection(), UNINDEXED_CASE, INDEXED);

    const next = chooseCase(first, { case_id: "case-5", repository_root: "/repos/later" }, INDEXED);

    // The offer decides where the folder picker opens, so a stale one would send the reader
    // somewhere the page no longer points at.
    expect(next.path).toBe("/repos/later");
  });

  it("leaves the repository alone for a case that names none", () => {
    const next = chooseCase(
      selection({ repositoryRoot: "/repos/warehouse" }),
      ROOTLESS_CASE,
      INDEXED,
    );

    expect(next.caseId).toBe("case-4");
    expect(next.repositoryRoot).toBe("/repos/warehouse");
  });

  it("switches to a different case, and to its repository", () => {
    const chosen = chooseCase(selection(), WAREHOUSE_CASE, INDEXED);

    const next = chooseCase(chosen, SCHEDULER_CASE, INDEXED);

    expect(next.caseId).toBe("case-2");
    expect(next.repositoryRoot).toBe("/repos/scheduler");
  });
});

describe("clearing a case", () => {
  it("clears it when the chosen one is chosen again", () => {
    const chosen = chooseCase(selection(), WAREHOUSE_CASE, INDEXED);

    const next = chooseCase(chosen, WAREHOUSE_CASE, INDEXED);

    // "No case" is a state worth getting back to now that a run does not need one.
    expect(next.caseId).toBeNull();
  });

  it("keeps the repository, which the reader did not ask to undo", () => {
    const chosen = chooseCase(selection(), WAREHOUSE_CASE, INDEXED);

    const next = chooseCase(chosen, WAREHOUSE_CASE, INDEXED);

    expect(next.repositoryRoot).toBe("/repos/warehouse");
    expect(isReady(next)).toBe(true);
  });

  it("round-trips: clearing and choosing again returns the same selection", () => {
    const chosen = chooseCase(selection(), WAREHOUSE_CASE, INDEXED);

    const cleared = chooseCase(chosen, WAREHOUSE_CASE, INDEXED);
    const again = chooseCase(cleared, WAREHOUSE_CASE, INDEXED);

    expect(again).toEqual(chosen);
  });
});

describe("choosing a repository", () => {
  it("selects it and leaves the case alone", () => {
    const chosen = chooseCase(selection(), WAREHOUSE_CASE, INDEXED);

    const next = chooseRepository(chosen, "/repos/scheduler");

    expect(next.repositoryRoot).toBe("/repos/scheduler");
    expect(next.caseId).toBe("case-1");
  });

  it("is not a toggle: the same repository twice stays selected", () => {
    // Unlike a case, it is the one input a run cannot do without, so clearing it could
    // only ever disable the button.
    const once = chooseRepository(selection(), "/repos/warehouse");
    const twice = chooseRepository(once, "/repos/warehouse");

    expect(twice.repositoryRoot).toBe("/repos/warehouse");
    expect(isReady(twice)).toBe(true);
  });
});

describe("applyRepositoryHint", () => {
  it("ignores a missing root rather than clearing what is chosen", () => {
    const chosen = selection({ repositoryRoot: "/repos/warehouse" });

    expect(applyRepositoryHint(chosen, null, INDEXED)).toEqual(chosen);
    expect(applyRepositoryHint(chosen, undefined, INDEXED)).toEqual(chosen);
    expect(applyRepositoryHint(chosen, "", INDEXED)).toEqual(chosen);
  });
});

describe("what pressing Run does", () => {
  it("reviews the chosen case when there is one", () => {
    const chosen = chooseCase(selection(), WAREHOUSE_CASE, INDEXED);

    expect(runIntent(chosen)).toEqual({
      kind: "against-case",
      caseId: "case-1",
      repositoryRoot: "/repos/warehouse",
    });
  });

  it("starts from the repository when no case is chosen", () => {
    const chosen = chooseRepository(selection(), "/repos/warehouse");

    // The path for someone who has not written a case: an empty one is opened about the
    // repository and the review's own questions fill it in.
    expect(runIntent(chosen)).toEqual({
      kind: "from-repository",
      repositoryRoot: "/repos/warehouse",
    });
  });

  it("goes back to reviewing the repository alone once a case is cleared", () => {
    const chosen = chooseCase(selection(), WAREHOUSE_CASE, INDEXED);
    const cleared = chooseCase(chosen, WAREHOUSE_CASE, INDEXED);

    expect(runIntent(cleared)).toEqual({
      kind: "from-repository",
      repositoryRoot: "/repos/warehouse",
    });
  });

  it("refuses to run without a repository, however much else is chosen", () => {
    expect(runIntent(selection())).toBeNull();
    expect(runIntent(selection({ caseId: "case-1" }))).toBeNull();
    expect(runIntent(selection({ path: "/repos/typed-but-not-indexed" }))).toBeNull();
  });

  it("never disagrees with the button's own enabled state", () => {
    // The two are derived from one selection, so a run cannot be startable while the
    // intent is impossible, or refused while the button says it is ready.
    const states = [
      selection(),
      selection({ caseId: "case-1" }),
      selection({ path: "/repos/typed" }),
      selection({ repositoryRoot: "/repos/warehouse" }),
      chooseCase(selection(), WAREHOUSE_CASE, INDEXED),
      chooseCase(chooseCase(selection(), WAREHOUSE_CASE, INDEXED), WAREHOUSE_CASE, INDEXED),
    ];

    for (const state of states) {
      expect(isReady(state)).toBe(runIntent(state) !== null);
    }
  });
});
