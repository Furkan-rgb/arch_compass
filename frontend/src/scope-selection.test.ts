import { describe, expect, it } from "vitest";

import {
  excludedPaths,
  formatBytes,
  groupFolders,
  initialSelection,
  selectionTotals,
} from "./scope-selection";
import type { RepositoryFolder } from "./types";

/* A repository shaped like the ones this picker meets: a source tree with a vendored copy
   inside it, and a test suite the server flags as usually-not-the-subject. The parents'
   counts include their children's, exactly as the listing endpoint reports them. */
const folder = (
  path: string,
  python_files: number,
  python_bytes: number,
  suggested = false,
): RepositoryFolder => ({ path, python_files, python_bytes, suggested });

const FOLDERS: RepositoryFolder[] = [
  folder("src", 100, 400_000),
  folder("src/vendor", 40, 300_000),
  folder("tests", 30, 60_000, true),
  folder("tests/fixtures", 5, 10_000, true),
];

const nodes = groupFolders(FOLDERS);

describe("groupFolders", () => {
  it("hangs depth-2 folders under the top-level folder they belong to", () => {
    expect(nodes.map((node) => node.folder.path)).toEqual(["src", "tests"]);
    expect(nodes[0].children.map((child) => child.path)).toEqual(["src/vendor"]);
    expect(nodes[1].children.map((child) => child.path)).toEqual(["tests/fixtures"]);
  });
});

describe("initialSelection", () => {
  it("starts with the suggested exclusions already unticked and nothing else", () => {
    expect([...initialSelection(FOLDERS)].sort()).toEqual(["src", "src/vendor"]);
  });
});

describe("excludedPaths", () => {
  it("names an unchecked parent once, and never its children", () => {
    // The whole point of the minimal list: `tests/fixtures` says nothing that `tests`
    // has not already said, and would go on saying it about a folder that may not exist
    // the next time this repository is indexed.
    expect(excludedPaths(nodes, initialSelection(FOLDERS))).toEqual(["tests"]);
  });

  it("names an unchecked child when its parent is being reviewed", () => {
    expect(excludedPaths(nodes, new Set(["src", "tests", "tests/fixtures"]))).toEqual([
      "src/vendor",
    ]);
  });

  it("excludes nothing when everything is checked", () => {
    expect(excludedPaths(nodes, new Set(FOLDERS.map((each) => each.path)))).toEqual([]);
  });

  it("names every top-level folder when nothing is checked", () => {
    expect(excludedPaths(nodes, new Set())).toEqual(["src", "tests"]);
  });
});

describe("selectionTotals", () => {
  it("takes an unchecked child back out of the parent that already counted it", () => {
    // Everything under `src`, less the vendored copy inside it — and nothing at all for
    // the unchecked `tests`, whose own child is therefore never in the sum either.
    expect(selectionTotals(nodes, new Set(["src"]))).toEqual({
      files: 60,
      bytes: 100_000,
    });
  });

  it("counts only what the suggestions left ticked", () => {
    expect(selectionTotals(nodes, initialSelection(FOLDERS))).toEqual({
      files: 100,
      bytes: 400_000,
    });
  });

  it("counts a checked child once, through its parent", () => {
    expect(selectionTotals(nodes, new Set(["src", "src/vendor"]))).toEqual({
      files: 100,
      bytes: 400_000,
    });
  });

  it("counts nothing when nothing is checked", () => {
    expect(selectionTotals(nodes, new Set())).toEqual({ files: 0, bytes: 0 });
  });
});

describe("formatBytes", () => {
  it("reads in kilobytes below a megabyte and megabytes above it", () => {
    expect(formatBytes(100_000)).toBe("97.7 KB");
    expect(formatBytes(4_500_000)).toBe("4.3 MB");
  });
});
