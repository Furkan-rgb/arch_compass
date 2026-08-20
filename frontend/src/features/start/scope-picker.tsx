import { useQuery } from "@tanstack/react-query";

import { api, type RepositoryFolder } from "../../api";
import { cn } from "../../lib/cn";
import { plural } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { Button } from "../../ui/button";
import { FolderIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { EmptyState, ErrorNotice, Spinner } from "../../ui/states";

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
  const tree = useQuery({
    queryKey: ["repository-tree", root],
    queryFn: () => api.repositoryTree(root),
    enabled: Boolean(root),
  });

  if (!root) {
    return (
      <p className="text-sm text-ink-3">Choose a repository first, and its folders appear here.</p>
    );
  }
  if (tree.isLoading) {
    return (
      <div className="flex items-center gap-2 py-3 text-sm text-ink-3">
        <Spinner /> Reading the repository…
      </div>
    );
  }
  if (tree.error) return <ErrorNotice error={tree.error} title="That repository could not be read" />;

  const folders = tree.data?.folders ?? [];
  if (!folders.length) {
    return (
      <EmptyState title="No sub-folders with Python in them" className="py-6">
        The whole repository will be reviewed.
      </EmptyState>
    );
  }

  const total = tree.data?.total_python_files ?? 0;
  const skipped = folders
    .filter((folder) => excluded.includes(folder.path))
    .reduce((sum, folder) => sum + folder.python_files, 0);
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
          Reviewing{" "}
          <strong className="font-semibold tabular-nums text-ink">{total - skipped}</strong> of{" "}
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
  return (
    <li>
      <label
        className={cn(
          "flex cursor-pointer items-center gap-2.5 rounded-sm border px-2.5 py-2 transition",
          checked || covered
            ? "border-rule bg-sunken text-ink-3"
            : "border-transparent hover:border-rule hover:bg-sunken/60",
          covered && "cursor-not-allowed opacity-60",
        )}
        style={{ paddingLeft: `${0.625 + depth * 1.1}rem` }}
      >
        <input
          type="checkbox"
          checked={checked || covered}
          disabled={covered}
          onChange={onToggle}
          className="size-4 shrink-0 accent-[var(--accent)]"
          aria-label={`Leave out ${folder.path}`}
        />
        <FolderIcon className="size-4 shrink-0 text-ink-3" />
        <Mono
          className={cn(
            "min-w-0 flex-1 truncate text-[12px]",
            checked || covered ? "text-ink-3 line-through" : "text-ink",
          )}
        >
          {folder.path}
        </Mono>
        {folder.suggested ? <Tag>usually skipped</Tag> : null}
        <span className="shrink-0 text-[11px] tabular-nums text-ink-3">
          {folder.python_files.toLocaleString()}
        </span>
      </label>
    </li>
  );
}
