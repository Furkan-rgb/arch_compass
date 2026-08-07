import { ChevronDown, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

import { EmptyLine, ErrorPanel } from "./components";
import {
  excludedPaths,
  formatBytes,
  groupFolders,
  initialSelection,
  selectionTotals,
  type ScopeNode,
} from "./scope-selection";
import type { RepositoryFolderTree } from "./types";

/* The same list this page's folder picker draws — a scrolling column of quiet rows on the
   sunken surface — with a checkbox where that one had a chevron. Two levels is the whole
   depth, so a row's indent is the only hierarchy there is to show. */
const scopeList = "m-0 grid max-h-[320px] list-none gap-0.5 overflow-y-auto p-0";
const scopeRow = cn(
  "grid w-full grid-cols-[16px_auto_minmax(0,1fr)_auto] items-center gap-x-2",
  "rounded-control border border-transparent bg-sunken px-2.5 py-1.5 text-left",
  "hover:border-rule has-[:focus-visible]:border-accent-rule",
);
const scopeName = "min-w-0 overflow-hidden font-mono text-meta text-ellipsis whitespace-nowrap";
const scopeSize = "text-micro whitespace-nowrap text-ink-3";
/* The rows are labels, so the checkbox is the only focusable thing in one: the whole row is
   the hit area and the tick is what the pointer lands on. */
const scopeBox = "size-3.5 shrink-0 cursor-pointer accent-[var(--primary)]";

/**
 * Every folder under a top-level one, so ticking the parent can carry them.
 *
 * The parent's own path is in the set as well: a subtree is checked or unchecked as one
 * thing, and the caller never has to remember to add the root of it.
 */
function subtree(node: ScopeNode): string[] {
  return [node.folder.path, ...node.children.map((child) => child.path)];
}

/** One row's tick, including the third state a parent gets when its children disagree. */
function Tick({
  checked,
  mixed,
  label,
  onChange,
}: {
  checked: boolean;
  mixed?: boolean;
  label: string;
  onChange: () => void;
}) {
  return (
    <input
      type="checkbox"
      className={scopeBox}
      checked={checked}
      aria-label={label}
      // Indeterminate is a property rather than an attribute, so React cannot set it from
      // JSX and it has to be written onto the node itself.
      ref={(node) => {
        if (node) node.indeterminate = Boolean(mixed) && !checked;
      }}
      onChange={onChange}
    />
  );
}

/**
 * Choosing what a review will read, before anything has read it.
 *
 * Offered after a checkout rather than asked for: the listing is already in hand by the
 * time this appears, and the numbers on it are the whole argument for narrowing — a
 * vendored library is half the source bytes of the repository and none of its architecture.
 * Dismissable, like the folder picker beside it, and dismissing indexes nothing: the flow
 * was "add this repository", and abandoning the choice abandons the errand.
 *
 * The state lives here and not on the page, so closing the dialog forgets the selection —
 * the next repository's tree is a different question with different folders in it.
 */
export function ScopePicker({
  tree,
  indexing,
  error,
  onConfirm,
  onDismiss,
}: {
  tree: RepositoryFolderTree;
  indexing: boolean;
  error: unknown;
  /** The minimal set of folders to leave out — empty means the whole repository. */
  onConfirm: (excluded: string[]) => void;
  onDismiss: () => void;
}) {
  const folders = useMemo(() => tree.folders ?? [], [tree.folders]);
  const nodes = useMemo(() => groupFolders(folders), [folders]);
  const [checked, setChecked] = useState(() => initialSelection(folders));
  // Closed to begin with: the top level is the choice being made, and a tree that opens
  // fully expanded buries it under the depth-2 folders of every folder.
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());

  const change = (paths: readonly string[], on: boolean) => {
    setChecked((current) => {
      const next = new Set(current);
      for (const path of paths) {
        if (on) next.add(path);
        else next.delete(path);
      }
      return next;
    });
  };

  const totals = selectionTotals(nodes, checked);
  const everything = folders.map((folder) => folder.path);

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onDismiss())}>
      <DialogContent
        className="max-w-[560px]"
        // Top-aligned for the same reason the folder picker is: the list is as tall as the
        // repository has folders, and expanding one must not slide the buttons about.
        overlayClassName="items-start py-[12vh]"
      >
        <DialogHeader>
          <DialogTitle>What should this review read?</DialogTitle>
          <DialogDescription>
            Everything is reviewed unless you say otherwise. Vendored code, generated code
            and fixtures cost the same to parse as the code you wrote, and say less about
            the architecture — folders that usually hold them start unticked.
          </DialogDescription>
        </DialogHeader>

        {nodes.length ? (
          <ul data-slot="pick" className={scopeList}>
            {nodes.map((node) => {
              const parent = node.folder;
              const on = checked.has(parent.path);
              const mixed =
                on && node.children.some((child) => !checked.has(child.path));
              const open = expanded.has(parent.path);
              return (
                <li key={parent.path}>
                  {/* The chevron is a control of its own and so sits outside the label
                      rather than inside it — a button nested in a label is a click that
                      does two things. The label takes the rest of the row through
                      `contents`, which keeps the four columns aligned across every row. */}
                  <div className={scopeRow}>
                    {node.children.length ? (
                      <button
                        type="button"
                        className="grid size-4 cursor-pointer place-items-center text-ink-3 hover:text-ink"
                        aria-label={
                          open ? `Collapse ${parent.path}` : `Expand ${parent.path}`
                        }
                        aria-expanded={open}
                        onClick={() =>
                          setExpanded((current) => {
                            const next = new Set(current);
                            if (next.has(parent.path)) next.delete(parent.path);
                            else next.add(parent.path);
                            return next;
                          })
                        }
                      >
                        {open ? (
                          <ChevronDown size={13} aria-hidden />
                        ) : (
                          <ChevronRight size={13} aria-hidden />
                        )}
                      </button>
                    ) : (
                      <span aria-hidden />
                    )}
                    <label className="contents">
                      <Tick
                        checked={on}
                        mixed={mixed}
                        label={parent.path}
                        // A parent carries its children: unticking `src` cannot leave
                        // `src/vendor` ticked, because there is no scope in which that is
                        // what the reader asked for.
                        onChange={() => change(subtree(node), !on)}
                      />
                      <b className={cn(scopeName, "font-[650]")}>{parent.path}</b>
                      <span className={scopeSize}>
                        {parent.python_files} files · {formatBytes(parent.python_bytes)}
                      </span>
                    </label>
                  </div>
                  {open
                    ? node.children.map((child) => (
                        <label
                          key={child.path}
                          className={cn(scopeRow, "mt-0.5 pl-8")}
                        >
                          <span aria-hidden />
                          <Tick
                            checked={checked.has(child.path)}
                            label={child.path}
                            onChange={() => {
                              const wanted = !checked.has(child.path);
                              change([child.path], wanted);
                              // Ticking a child that its parent was excluding brings the
                              // parent back: a folder cannot be read out of a subtree the
                              // server was told to skip.
                              if (wanted) change([parent.path], true);
                            }}
                          />
                          <span className={cn(scopeName, "text-ink-2")}>
                            {child.path.split("/").slice(1).join("/")}
                          </span>
                          <span className={scopeSize}>
                            {child.python_files} files · {formatBytes(child.python_bytes)}
                          </span>
                        </label>
                      ))
                    : null}
                </li>
              );
            })}
          </ul>
        ) : (
          <EmptyLine>No folders to choose between — the whole repository it is.</EmptyLine>
        )}

        {error ? <ErrorPanel error={error} /> : null}

        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-rule-soft pt-3.5">
          <p className="m-0 flex-[1_1_20ch] text-meta text-ink-2">
            Reviewing <strong className="font-[650] text-ink">{totals.files} files</strong>,{" "}
            {formatBytes(totals.bytes)} of Python
          </p>
          <div className="flex items-center gap-3">
            {/* Quieter than the two controls beside it: undoing the suggestions is a
                correction, not the thing this dialog is for. */}
            <button
              type="button"
              className="cursor-pointer text-meta text-ink-2 underline underline-offset-2 hover:text-ink"
              onClick={() => change(everything, true)}
            >
              Select all
            </button>
            <Button
              type="button"
              variant="primary"
              disabled={indexing}
              onClick={() => onConfirm(excludedPaths(nodes, checked))}
            >
              {indexing ? (
                <>
                  <Spinner /> Indexing…
                </>
              ) : (
                "Review selection"
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
