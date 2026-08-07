/**
 * Which of a repository's folders a review will read, and what that adds up to.
 *
 * Kept apart from the picker that renders it because the one thing here that can be wrong
 * quietly is the exclusion list: it goes to the server, decides what is never parsed, and
 * shows up on screen only as a number. Pure and synchronous, so the rules are checkable
 * without rendering a dialog.
 *
 * The server counts a child's Python inside its parent's as well — a depth-2 entry like
 * `src/vendor` is part of `src` — so every sum and every list in here is written against
 * that overlap rather than around it.
 */

import type { RepositoryFolder } from "./types";

/** A top-level folder and the depth-2 folders the listing gave underneath it. */
export type ScopeNode = {
  folder: RepositoryFolder;
  children: readonly RepositoryFolder[];
};

/**
 * The flat listing as two levels.
 *
 * A depth-2 entry whose parent is absent from the listing cannot happen — a parent counts
 * everything its children count, so a child with Python guarantees a parent with Python —
 * but it is treated as a top-level folder if it ever does, because dropping a folder would
 * silently review code nobody was shown.
 */
export function groupFolders(folders: readonly RepositoryFolder[]): ScopeNode[] {
  const tops = folders.filter((folder) => !folder.path.includes("/"));
  const known = new Set(tops.map((folder) => folder.path));
  const orphans = folders.filter(
    (folder) => folder.path.includes("/") && !known.has(folder.path.split("/")[0]),
  );
  return [...tops, ...orphans]
    .map((folder) => ({
      folder,
      children: folders.filter(
        (other) => other !== folder && other.path.startsWith(`${folder.path}/`),
      ),
    }))
    .sort((left, right) => left.folder.path.localeCompare(right.folder.path));
}

/**
 * Everything checked, except what the server flagged as usually-not-the-code-under-review.
 *
 * The flag is advisory and the starting state is where advice belongs: a suggestion that
 * arrives already applied can be undone in one click, where one that has to be applied by
 * hand is a chore repeated for every repository.
 */
export function initialSelection(folders: readonly RepositoryFolder[]): Set<string> {
  return new Set(
    folders.filter((folder) => !folder.suggested).map((folder) => folder.path),
  );
}

/**
 * The shortest set of paths that describes what was left out.
 *
 * Minimal on purpose: a folder that is unchecked along with all of its children is one
 * excluded subtree, and listing the children as well would say the same thing three times
 * — and would keep saying it about children the repository no longer has the next time it
 * is indexed. An unchecked child of a checked parent is the only case where a deeper path
 * carries information.
 */
export function excludedPaths(
  nodes: readonly ScopeNode[],
  checked: ReadonlySet<string>,
): string[] {
  const excluded: string[] = [];
  for (const node of nodes) {
    if (!checked.has(node.folder.path)) {
      excluded.push(node.folder.path);
      continue;
    }
    for (const child of node.children) {
      if (!checked.has(child.path)) excluded.push(child.path);
    }
  }
  return excluded;
}

/** What the selection comes to: the numbers the footer line reports. */
export type ScopeTotals = { files: number; bytes: number };

/**
 * The selection's size, counted by subtraction.
 *
 * A checked parent already includes its children, so the total starts from the parent and
 * takes back each child that was unchecked. Adding the checked children instead would
 * double-count everything under them.
 *
 * Python at the repository root, in no listed folder, is reviewed either way and is not in
 * these numbers — there is no choice to make about it, so it is not offered as one.
 */
export function selectionTotals(
  nodes: readonly ScopeNode[],
  checked: ReadonlySet<string>,
): ScopeTotals {
  let files = 0;
  let bytes = 0;
  for (const node of nodes) {
    if (!checked.has(node.folder.path)) continue;
    files += node.folder.python_files;
    bytes += node.folder.python_bytes;
    for (const child of node.children) {
      if (checked.has(child.path)) continue;
      files -= child.python_files;
      bytes -= child.python_bytes;
    }
  }
  return { files, bytes };
}

/**
 * A size at the precision someone deciding what to skip can act on: one decimal, and never
 * a five-digit kilobyte count. Below a megabyte the useful unit is KB, above it is MB —
 * gigabytes of Python source are not a thing this listing will meet.
 */
export function formatBytes(bytes: number): string {
  const kilobytes = bytes / 1024;
  if (kilobytes < 1024) return `${kilobytes.toFixed(1)} KB`;
  return `${(kilobytes / 1024).toFixed(1)} MB`;
}
