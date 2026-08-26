import { useQuery } from "@tanstack/react-query";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import { cn } from "../lib/cn";
import { repositoryName } from "../lib/format";
import { hasOpenModal, isTyping } from "../lib/keyboard";
import { useOverlay } from "../lib/motion";
import { SearchIcon } from "./icons";
import { Label } from "./panel";
import { KeyCap } from "./shortcuts";

export type PaletteSection = { to: string; label: string };

/**
 * `measured` is which voice the label is in, and it is a fact about the entry rather than a
 * style the row picks.
 *
 * The palette is the way a reviewer reaches a specific review, and it used to set every label
 * in sans-medium and push the machine facts — the branch, the repository root — to the right
 * margin in mono. `payments · review 4` is a name and a count, which `design-system.md`
 * assigns to the measured voice; a section is a place a person goes, which is not. So the two
 * kinds of row are set in the two faces they belong to, and the rule the docket already obeys
 * holds here too.
 */
type Entry = {
  id: string;
  to: string;
  label: string;
  hint?: string;
  group: string;
  measured?: boolean;
};

/**
 * `aria-activedescendant` points at an id, so the options need ids that are stable for as
 * long as the pointer is on them. The index rather than the entry's own id: an entry id is a
 * route or an absolute path, and neither is a legal fragment to hand a screen reader.
 */
const LIST_ID = "palette-results";
const optionId = (index: number) => `${LIST_ID}-${index}`;

/** How many rows a filtered list may draw before it says it has more. */
const CAP = 24;

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

  const { entries, cut } = useMemo<{ entries: Entry[]; cut: boolean }>(() => {
    const goTo: Entry[] = sections.map((item) => ({
      id: `section:${item.to}`,
      to: item.to,
      label: item.label,
      group: "Go to",
    }));
    const reviewEntries: Entry[] = (reviews.data ?? []).map((review) => ({
      id: `review:${review.id}`,
      to: `/reviews/${review.id}`,
      label: `${repositoryName(review.repository.path)} · review ${review.sequence}`,
      // The branch alone. It used to carry the branch *and* a relative time, which put two
      // mono runs on one row competing for the same glance — and a relative time is prose
      // rather than a machine fact, so it was the one of the two that did not belong in the
      // measured voice at all.
      hint: review.repository.branch || undefined,
      group: "Reviews",
      measured: true,
    }));
    const repositoryEntries: Entry[] = (repositories.data ?? []).map((repository) => ({
      id: `repository:${repository.root_path}`,
      // Every entry used to lead to a bare `/repositories`, so searching `billing-service`
      // and pressing Enter landed on whichever repository the page happened to select —
      // indistinguishable from the palette not working. The page reads `?root=` on mount
      // and an explicit one beats its own search filter.
      to: `/repositories?root=${encodeURIComponent(repository.root_path)}`,
      label: repositoryName(repository.root_path),
      hint: repository.root_path,
      group: "Repositories",
      measured: true,
    }));

    const needle = query.trim().toLowerCase();
    // Capped per group rather than over the concatenation, because Repositories was last and
    // the cap was 24: six sections plus eighteen reviews and a workspace showed no repository
    // at all in the palette's resting state, with nothing saying the list had been cut. A
    // reader browsing ⌘K learnt that repositories were not in here. They were.
    if (!needle) {
      const resting = [...goTo, ...reviewEntries.slice(0, 10), ...repositoryEntries.slice(0, 8)];
      return {
        entries: resting,
        cut: reviewEntries.length > 10 || repositoryEntries.length > 8,
      };
    }
    const found = [...goTo, ...reviewEntries, ...repositoryEntries].filter((entry) =>
      `${entry.label} ${entry.hint ?? ""}`.toLowerCase().includes(needle),
    );
    // A cut list says so rather than ending at a row that looks like the last one. `cut` is
    // returned from here rather than inferred from the drawn length, which cannot tell a list
    // of exactly `CAP` matches from one that was trimmed.
    return { entries: found.slice(0, CAP), cut: found.length > CAP };
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

  /**
   * What the palette says when it has no rows to show, and it is three sentences rather than
   * one.
   *
   * Both lists are fetched only once this opens, so for the first few hundred milliseconds the
   * only entries that exist are the six sections — and a reader who pressed ⌘K and typed a
   * repository name was told, definitively, that nothing matched. If either query failed they
   * were told the same thing for ever. The palette is the product's answer to "how do I reach
   * that review", and a confident false negative is the worst failure it has.
   */
  const loading = reviews.isPending || repositories.isPending;
  const failed = reviews.isError || repositories.isError;
  const emptyLine = loading
    ? "Still reading reviews and repositories…"
    : failed
      ? "Could not read the workspace's reviews and repositories, and nothing in the sections matches that."
      : "Nothing matches that.";

  // The same thing the eye is shown, for the ear. A count where there are rows, because "which
  // of these" is answered by walking them and "are there any" is not.
  const status = entries.length
    ? `${entries.length} result${entries.length === 1 ? "" : "s"}${cut ? ", more not shown" : ""}`
    : emptyLine;

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
          <KeyCap className="hidden shrink-0 sm:inline-flex">esc</KeyCap>
        </div>

        {/* Everything this dialog says has to reach a listener through the combobox, because
            focus never leaves the input by design. The visible sentence below is an ordinary
            paragraph in an unmounted branch of a listbox, so a query that matched nothing
            announced `aria-expanded` going false and then silence — indistinguishable from the
            palette having stopped responding. This is the line that is always mounted and
            always says the same thing the eye is being shown. */}
        <p className="sr-only" role="status" aria-live="polite">
          {status}
        </p>

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
                    // `mousemove`, not `mouseenter`. The palette scrolls the keyboard cursor
                    // into view, and it opens at `pt-[12vh]` — roughly where a pointer is left
                    // after clicking the search button in the rail. So holding ArrowDown
                    // scrolled rows under a stationary pointer, each arrival fired
                    // `mouseenter`, and the selection was dragged back up the list with
                    // nothing on screen explaining why. A move is a move; a row arriving under
                    // a still pointer is not.
                    onMouseMove={() => setAt(index)}
                    onClick={() => go(entry)}
                    className={cn(
                      "relative flex min-h-10 cursor-pointer items-baseline gap-2.5 px-3.5 py-1.5 text-left transition",
                      // The fill is 1.19:1 in light and 1.18:1 in dark, which is a division a
                      // reader is not asked to notice — and it was the only thing saying which
                      // of up to 24 rows Enter would take, in a list whose labels differ by one
                      // digit. So the row carries the docket's device as well: an edge, read
                      // without being looked at, in ink rather than a verdict hue. The
                      // inactive rows keep a transparent one so nothing shifts as it moves.
                      "before:absolute before:inset-y-0 before:left-0 before:w-0.5",
                      index === at
                        ? "bg-sunken before:bg-ink"
                        : "before:bg-transparent hover:bg-sunken",
                    )}
                  >
                    {/* `shrink-0` is gone. With it the label took its whole content width and
                        never truncated, and the hint — `flex-1`, so basis zero — absorbed the
                        entire overflow and disappeared, which on two repositories sharing a
                        leaf name is the only thing telling them apart. The hint is capped
                        instead, so the label keeps priority and both can still be read. */}
                    <span
                      className={cn(
                        "min-w-0 flex-1 truncate text-ink",
                        entry.measured
                          ? "font-mono text-[13px] font-medium"
                          : "text-[13px] font-medium",
                      )}
                    >
                      {entry.label}
                    </span>
                    {entry.hint ? (
                      <span className="min-w-0 max-w-[45%] shrink-0 truncate text-right font-mono text-[11px] text-ink-3">
                        {entry.hint}
                      </span>
                    ) : null}
                  </li>
                </Fragment>
              );
            })}
            {/* A cut list states that it was cut. `presentation` rather than an option: it is
                not somewhere Enter can take you, and counting it would make the option count
                a lie for anyone listening. */}
            {cut ? (
              <li role="presentation" className="px-3.5 py-2 text-[12px] text-ink-3">
                More matches — keep typing to narrow this.
              </li>
            ) : null}
          </ul>
        ) : (
          // `id={LIST_ID}` so the input's `aria-controls` resolves in this branch too; it
          // pointed at an element that did not exist whenever the list was empty, which is
          // exactly when a listener most needs to be told something.
          <p id={LIST_ID} className="px-3.5 py-6 text-[13px] text-ink-3">
            {emptyLine}
          </p>
        )}
      </div>
    </div>
  );
}
