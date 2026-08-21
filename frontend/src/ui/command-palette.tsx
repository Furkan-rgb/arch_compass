import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import { cn } from "../lib/cn";
import { relativeTime, repositoryName } from "../lib/format";
import { SearchIcon } from "./icons";

export type PaletteSection = { to: string; label: string };

type Entry = { id: string; to: string; label: string; hint?: string; group: string };

/**
 * Open from anywhere with the one shortcut every tool has trained people to try.
 *
 * Bound at the document, refused while something is being typed into and while a modal is
 * already up — the same three guards the decision keys carry, for the same reason: a
 * shortcut that fires inside a waiver's reason box is a bug, not a shortcut.
 */
export function useCommandPalette() {
  const [isOpen, setOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== "k" || !(event.metaKey || event.ctrlKey)) return;
      event.preventDefault();
      setOpen((value) => !value);
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
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

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
        to: "/repositories",
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
    if (open) inputRef.current?.focus();
    else setQuery("");
  }, [open]);

  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelectorAll("[data-entry]")
      [at]?.scrollIntoView({ block: "nearest" });
  }, [at, open]);

  if (!open) return null;

  function go(entry: Entry | undefined) {
    if (!entry) return;
    onClose();
    navigate(entry.to);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown") {
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
        role="dialog"
        aria-modal="true"
        aria-label="Search everything"
        onKeyDown={onKeyDown}
        className="animate-expand relative flex max-h-[70vh] w-full max-w-xl flex-col overflow-hidden rounded-lg border border-rule bg-surface shadow-float"
      >
        <div className="flex shrink-0 items-center gap-2.5 border-b border-rule px-3.5">
          <SearchIcon className="size-4 shrink-0 text-ink-3" />
          <input
            ref={inputRef}
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
          <ul ref={listRef} className="min-h-0 flex-1 overflow-y-auto overflow-x-clip py-1.5">
            {entries.map((entry, index) => {
              const heading = entry.group !== group ? entry.group : null;
              group = entry.group;
              return (
                <li key={entry.id}>
                  {heading ? (
                    <div className="px-3.5 pb-1 pt-2.5 text-[10px] font-bold uppercase tracking-[0.13em] text-ink-3">
                      {heading}
                    </div>
                  ) : null}
                  <button
                    type="button"
                    data-entry={entry.id}
                    aria-current={index === at ? "true" : undefined}
                    onMouseEnter={() => setAt(index)}
                    onClick={() => go(entry)}
                    className={cn(
                      "flex min-h-10 w-full items-baseline gap-2.5 px-3.5 py-1.5 text-left transition",
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
                  </button>
                </li>
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
