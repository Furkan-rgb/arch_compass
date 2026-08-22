import { useQuery } from "@tanstack/react-query";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import { cn } from "../lib/cn";
import { relativeTime, repositoryName } from "../lib/format";
import { hasOpenModal, isTyping } from "../lib/keyboard";
import { useOverlay } from "../lib/motion";
import { SearchIcon } from "./icons";
import { Label } from "./panel";

export type PaletteSection = { to: string; label: string };

type Entry = { id: string; to: string; label: string; hint?: string; group: string };

/**
 * `aria-activedescendant` points at an id, so the options need ids that are stable for as
 * long as the pointer is on them. The index rather than the entry's own id: an entry id is a
 * route or an absolute path, and neither is a legal fragment to hand a screen reader.
 */
const LIST_ID = "palette-results";
const optionId = (index: number) => `${LIST_ID}-${index}`;

/**
 * Open from anywhere with the one shortcut every tool has trained people to try.
 *
 * Bound at the document, refused while something is being typed into and while a modal is
 * already up — the same guards the decision keys carry, from `lib/keyboard.ts`, for the same
 * reason: a shortcut that fires inside a waiver's reason box is a bug, not a shortcut. The
 * comment used to say all of that while the handler checked the key and the modifier alone,
 * so `Ctrl+K` — kill-to-end-of-line on macOS — opened the palette over whatever you were
 * writing, and `⌘K` with the context drawer open stacked a second modal on a live focus trap.
 *
 * It opens rather than toggles. Escape is how a palette closes, and a shortcut that also
 * closes has to decide what to do when the reader has typed a query and pressed it again.
 */
export function useCommandPalette() {
  const [isOpen, setOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== "k" || !(event.metaKey || event.ctrlKey)) return;
      if (isTyping(event.target) || hasOpenModal()) return;
      event.preventDefault();
      setOpen(true);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  return {
    isOpen,
    open: useCallback(() => setOpen(true), []),
    close: useCallback(() => setOpen(false), []),
  };
}

/**
 * Everywhere you can go, by name.
 *
 * This is what replaced the sidebar, and it can do the thing a sidebar never could: a
 * sidebar lists six destinations, and what a reviewer actually wants to reach is *this
 * review of that branch* — one of dozens, none of which a nav can hold. So the sections are
 * in here alongside every review and every repository the workspace knows about.
 *
 * The lists are fetched only once it is opened, and they are the same query keys the pages
 * use, so opening this twice costs one request.
 */
export function CommandPalette({
  open,
  onClose,
  sections,
}: {
  open: boolean;
  onClose: () => void;
  sections: PaletteSection[];
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [at, setAt] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);
  // The trap focuses the first focusable thing inside the dialog, which is the search
  // field — so the palette gets its own focus, the page behind it stops scrolling, and
  // focus goes back to whatever opened it, from the same hook the drawer uses.
  const dialogRef = useOverlay(open, onClose);

  const reviews = useQuery({ queryKey: ["reviews"], queryFn: api.reviews, enabled: open });
  const repositories = useQuery({
    queryKey: ["repositories"],
    queryFn: api.repositories,
    enabled: open,
  });

  const entries = useMemo<Entry[]>(() => {
    const all: Entry[] = [
      ...sections.map((item) => ({
        id: `section:${item.to}`,
        to: item.to,
        label: item.label,
        group: "Go to",
      })),
      ...(reviews.data ?? []).map((review) => ({
        id: `review:${review.id}`,
        to: `/reviews/${review.id}`,
        label: `${repositoryName(review.repository.path)} · review ${review.sequence}`,
        hint: [review.repository.branch, relativeTime(review.started_at)]
          .filter(Boolean)
          .join(" · "),
        group: "Reviews",
      })),
      ...(repositories.data ?? []).map((repository) => ({
        id: `repository:${repository.root_path}`,
        // Every entry used to lead to a bare `/repositories`, so searching `billing-service`
        // and pressing Enter landed on whichever repository the page happened to select —
        // indistinguishable from the palette not working. The page reads `?root=` on mount
        // and an explicit one beats its own search filter.
        to: `/repositories?root=${encodeURIComponent(repository.root_path)}`,
        label: repositoryName(repository.root_path),
        hint: repository.root_path,
        group: "Repositories",
      })),
    ];
    const needle = query.trim().toLowerCase();
    if (!needle) return all.slice(0, 24);
    return all
      .filter((entry) => `${entry.label} ${entry.hint ?? ""}`.toLowerCase().includes(needle))
      .slice(0, 24);
  }, [sections, reviews.data, repositories.data, query]);

  // A filter that shortens the list must not leave the cursor past the end of it, and
  // reopening starts from the top rather than wherever the last search left off.
  useEffect(() => setAt(0), [query, open]);
  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelectorAll("[data-entry]")
      // The second `?.` the way the docket writes it: jsdom implements no `scrollIntoView`
      // at all, and this is the one keyboard path in the palette every test walks.
      [at]?.scrollIntoView?.({ block: "nearest" });
  }, [at, open]);

  if (!open) return null;

  function go(entry: Entry | undefined) {
    if (!entry) return;
    onClose();
    navigate(entry.to);
  }

  // Escape is not here: the overlay hook owns it, at the document and in the capture phase,
  // so it closes the palette whether or not the keystroke started inside the dialog.
  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setAt((value) => Math.min(value + 1, entries.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setAt((value) => Math.max(value - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(entries[at]);
    }
  }

  let group: string | null = null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12vh]">
      <div
        className="absolute inset-0 bg-overlay"
        aria-hidden="true"
        onClick={onClose}
      />
      {/* One of the three things in this product that genuinely leaves the page, so it is one
          of the three allowed a lift. */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Search everything"
        onKeyDown={onKeyDown}
        className="animate-expand relative flex max-h-[70vh] w-full max-w-xl flex-col overflow-hidden rounded-lg border border-rule bg-surface shadow-float"
      >
        <div className="flex shrink-0 items-center gap-2.5 border-b border-rule px-3.5">
          <SearchIcon className="size-4 shrink-0 text-ink-3" />
          {/* A real combobox over a real listbox. It used to be an input beside a column of
              buttons carrying `aria-current`, which announces nothing while the arrow keys
              move it — the highlight was visible and silent. Focus stays here and
              `aria-activedescendant` says which option it is on, which is what lets one
              keystroke both filter and walk. */}
          <input
            role="combobox"
            aria-expanded={entries.length > 0}
            aria-controls={LIST_ID}
            aria-activedescendant={entries[at] ? optionId(at) : undefined}
            aria-autocomplete="list"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Search reviews, repositories and sections"
            placeholder="Search reviews, repositories and sections…"
            className="min-h-12 min-w-0 flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-ink-3"
          />
          <kbd className="hidden shrink-0 rounded-xs border border-rule px-1 font-mono text-[10px] leading-4 text-ink-3 sm:inline">
            esc
          </kbd>
        </div>

        {entries.length ? (
          <ul
            ref={listRef}
            id={LIST_ID}
            role="listbox"
            aria-label="Results"
            className="min-h-0 flex-1 overflow-y-auto overflow-x-clip py-1.5"
          >
            {entries.map((entry, index) => {
              const heading = entry.group !== group ? entry.group : null;
              group = entry.group;
              return (
                <Fragment key={entry.id}>
                  {/* A heading inside a listbox is not an option, and saying so is what
                      keeps the option count honest for anyone listening to it. */}
                  {heading ? (
                    <li role="presentation">
                      <Label className="px-3.5 pb-1 pt-2.5">{heading}</Label>
                    </li>
                  ) : null}
                  <li
                    role="option"
                    id={optionId(index)}
                    data-entry={entry.id}
                    aria-selected={index === at}
                    onMouseEnter={() => setAt(index)}
                    onClick={() => go(entry)}
                    className={cn(
                      "flex min-h-10 cursor-pointer items-baseline gap-2.5 px-3.5 py-1.5 text-left transition",
                      index === at ? "bg-sunken" : "hover:bg-sunken/60",
                    )}
                  >
                    <span className="min-w-0 shrink-0 truncate text-[13.5px] font-medium text-ink">
                      {entry.label}
                    </span>
                    {entry.hint ? (
                      <span className="min-w-0 flex-1 truncate text-right font-mono text-[11px] text-ink-3">
                        {entry.hint}
                      </span>
                    ) : null}
                  </li>
                </Fragment>
              );
            })}
          </ul>
        ) : (
          <p className="px-3.5 py-6 text-[13px] text-ink-3">Nothing matches that.</p>
        )}
      </div>
    </div>
  );
}
