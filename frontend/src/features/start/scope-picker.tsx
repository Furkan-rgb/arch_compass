import { useQuery } from "@tanstack/react-query";
import type { CSSProperties } from "react";

import { api, type RepositoryFolder, type RepositoryFolderTree } from "../../api";
import { cn } from "../../lib/cn";
import { plural } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { Button } from "../../ui/button";
import { FolderIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { EmptyState, ErrorNotice, Spinner } from "../../ui/states";

/**
 * Whether a path is worth asking the workspace about at all.
 *
 * `/api/repositories/tree` walks the folder with `rglob("*")` and a `stat()` per file, so a
 * half-typed path is not a cheap request that comes back 404 — it is a full recursive walk of
 * whatever directory the prefix happens to name. `/Users/me` is a real directory on the way
 * to everything under it, which is how typing a path once walked somebody's entire home
 * folder. Nothing that is not an absolute path can be read, so nothing else is sent.
 */
export const isAbsolutePath = (path: string) => path.startsWith("/");

/**
 * The repository's folders, asked for once however many components want them.
 *
 * The start page needs the file count for what it prints under the run button and for
 * whether the button can run at all; this picker needs the folders themselves. One query
 * key, so React Query answers both from one request rather than each opening its own.
 */
export function useRepositoryTree(root: string) {
  return useQuery({
    queryKey: ["repository-tree", root],
    queryFn: ({ signal }) => api.repositoryTree(root, signal),
    enabled: isAbsolutePath(root),
    // No retry, against the global three. The one failure this query has is the read timeout,
    // and a walk that did not finish in thirty seconds will not finish in thirty seconds on
    // the second ask: `AbortSignal.timeout` firing is not React Query's own cancellation, so
    // the retryer read it as an ordinary failure and asked again three times, while the
    // server — a sync route in a threadpool — kept walking after every abort. One paste of a
    // large path bought four uncancellable walks and, two minutes later, "That repository
    // could not be read" about a repository that reads fine.
    retry: false,
  });
}

/** The Python files this run will actually read, given what has been left out. */
export function filesInScope(
  tree: RepositoryFolderTree | undefined,
  excluded: string[],
): number | null {
  if (!tree) return null;
  const skipped = (tree.folders ?? [])
    .filter((folder) => excluded.includes(folder.path))
    .reduce((sum, folder) => sum + folder.python_files, 0);
  return (tree.total_python_files ?? 0) - skipped;
}

/**
 * Which parts of the repository this review reads.
 *
 * Everything here is offered with the number beside it, because the question is not "what is
 * in this repository" but "what would leaving this out save" — and a folder's count is that
 * answer. Counted recursively, so `src` includes `src/vendor`; leaving out a parent leaves
 * out its children, and the listing says so by disabling them rather than by letting two
 * checkboxes describe one decision.
 *
 * Nothing is excluded on the reader's behalf. `tests` and `docs` are marked as usually
 * skippable and stay unticked, because a repository whose product is its examples would be
 * gutted by a guess made from a directory's name.
 */
export function ScopePicker({
  root,
  excluded,
  onChange,
}: {
  root: string;
  excluded: string[];
  onChange: (next: string[]) => void;
}) {
  const tree = useRepositoryTree(root);

  if (!root) {
    return (
      <p className="text-sm text-ink-3">Choose a repository first, and its folders appear here.</p>
    );
  }
  if (!isAbsolutePath(root)) {
    return (
      <p className="text-sm text-ink-3">
        A repository is named by an absolute path on this machine, and its folders appear here
        as soon as this one is.
      </p>
    );
  }
  if (tree.isLoading) {
    return (
      <div className="flex items-center gap-2 py-3 text-sm text-ink-3">
        {/* The label is printed right beside it, so the spinner does not say it again. */}
        <Spinner label="" /> Reading the repository…
      </div>
    );
  }
  if (tree.error) {
    return (
      <ErrorNotice
        error={tree.error}
        title="That repository could not be read"
        action={
          <Button variant="secondary" size="sm" onClick={() => void tree.refetch()}>
            Try again
          </Button>
        }
      />
    );
  }

  const folders = tree.data?.folders ?? [];
  if (!folders.length) {
    return (
      <EmptyState title="No sub-folders with Python in them" className="py-6">
        The whole repository will be reviewed.
      </EmptyState>
    );
  }

  const total = tree.data?.total_python_files ?? 0;
  const reading = filesInScope(tree.data, excluded) ?? total;
  const skipped = total - reading;
  const suggested = folders.filter((folder) => folder.suggested).map((folder) => folder.path);

  const toggle = (path: string) => {
    if (excluded.includes(path)) {
      onChange(excluded.filter((entry) => entry !== path));
      return;
    }
    // A parent replaces its children rather than joining them: `src` and `src/vendor` are
    // two spellings of one scope, and the choice is read back and compared, not just
    // applied. The backend collapses them too — this only keeps the screen honest about it.
    onChange([...excluded.filter((entry) => !entry.startsWith(`${path}/`)), path]);
  };

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-ink-2">
          Reviewing <strong className="font-semibold tabular-nums text-ink">{reading}</strong> of{" "}
          <span className="tabular-nums">{plural(total, "Python file")}</span>
          {skipped ? <span className="text-ink-3"> · {skipped} left out</span> : null}
        </p>
        <div className="flex gap-1.5">
          <Button
            size="sm"
            variant="ghost"
            disabled={!suggested.length || suggested.every((path) => excluded.includes(path))}
            onClick={() => onChange([...new Set([...excluded, ...suggested])])}
          >
            Skip the usual
          </Button>
          <Button size="sm" variant="ghost" disabled={!excluded.length} onClick={() => onChange([])}>
            Review all of it
          </Button>
        </div>
      </div>

      <ul className="scrollbar-slim grid max-h-72 gap-1 overflow-y-auto overflow-x-clip">
        {folders.map((folder) => (
          <FolderRow
            key={folder.path}
            folder={folder}
            checked={excluded.includes(folder.path)}
            // Covered by an ancestor already left out, so it has no separate decision left
            // to make and must not read as one somebody forgot to tick.
            covered={excluded.some((entry) => folder.path.startsWith(`${entry}/`))}
            onToggle={() => toggle(folder.path)}
          />
        ))}
      </ul>
    </div>
  );
}

function FolderRow({
  folder,
  checked,
  covered,
  onToggle,
}: {
  folder: RepositoryFolder;
  checked: boolean;
  covered: boolean;
  onToggle: () => void;
}) {
  const depth = folder.path.split("/").length - 1;
  const cut = folder.path.lastIndexOf("/");
  const leaf = cut > 0 ? folder.path.slice(cut + 1) : folder.path;
  const dimmed = checked || covered;

  return (
    <li>
      <label
        // The whole path, always, wherever the row had to shorten it. There was none, so a
        // truncated row had nothing behind it to recover the difference from.
        title={folder.path}
        // 1.625rem, so a child's checkbox sits under its parent's folder icon: 10px of
        // padding, a 16px box and a 10px gap is 36px, and 36 less the 10 this row already
        // has is 26. An arbitrary step would only push the row along; this one lines up
        // with something, which is what makes it read as containment rather than as a gap.
        style={{ "--depth": `${depth * 1.625}rem` } as CSSProperties}
        className={cn(
          "flex cursor-pointer items-center gap-2.5 rounded-sm border py-2 pr-2.5 transition",
          // The indent is the only thing on a row that says this folder is inside the one
          // above it, so it is not a thing to spend at any width. It used to be `sm:` only:
          // below 640px the tree gave up the indent and re-stated the parent as a second
          // line above the leaf, which is what a phone actually showed — seven rows all
          // flush left, `src/` printed above `archcompass`, and nothing saying which was
          // inside which.
          //
          // The trade was sized against a depth-2 row, and `_MAX_DEPTH = 2` in
          // `analysis/tree.py` means the listing only ever returns one- and two-part paths.
          // So what was being given away is a single step, out of roughly 219px of name at
          // 390px — against a longest real leaf of eleven characters. Two anatomies keyed to
          // a breakpoint is also the second interface `docs/experience.md` says a phone does
          // not get.
          //
          // The fallback on `var()` is load-bearing now that the base padding is gone: an
          // unregistered custom property that resolves to nothing makes the declaration
          // invalid at computed-value time, and `padding-left` would fall back to 0 rather
          // than to the gutter every row needs.
          "pl-[calc(0.625rem_+_var(--depth,0rem))]",
          dimmed
            ? "border-rule bg-sunken text-ink-3"
            : "border-transparent hover:border-rule hover:bg-sunken/60",
          covered && "cursor-not-allowed opacity-60",
        )}
      >
        <input
          type="checkbox"
          checked={dimmed}
          disabled={covered}
          onChange={onToggle}
          className="size-4 shrink-0 accent-[var(--ink)]"
          aria-label={`Leave out ${folder.path}`}
        />
        <FolderIcon className="size-4 shrink-0 text-ink-3" />
        <span className="min-w-0 flex-1">
          {/* The leaf alone. The listing sorts lexicographically and a two-part path's own
              parent is always a row in it — `folder_tree` counts a file into both — so the
              row above is the parent and the indent already says so. Printing `src/` here
              as well is the prefix repeating what the position states, and on a phone it
              cost a second line on every nested row to do it. The whole path stays on the
              hover and in the checkbox's accessible name, which is also how
              `start-page.test.tsx` addresses these rows. */}
          <Mono
            className={cn(
              "block truncate text-[12px]",
              dimmed ? "text-ink-3 line-through" : "text-ink",
            )}
          >
            {leaf}
          </Mono>
        </span>
        {folder.suggested ? <Tag>usually skipped</Tag> : null}
        <span className="shrink-0 text-[11px] tabular-nums text-ink-3">
          {folder.python_files.toLocaleString()}
        </span>
      </label>
    </li>
  );
}
