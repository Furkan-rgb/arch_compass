import { useQuery } from "@tanstack/react-query";
import { BookOpenText, ClipboardList, Compass, Info, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandFooter,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

import { api } from "./api";
import { formatDate, humanizeLabel, shortId } from "./components";

/**
 * Everything this workspace holds, one keystroke away.
 *
 * The three destinations are the same three the top bar draws, so the palette is never a
 * second navigation with its own opinion. What it adds is the part a bar cannot hold: a
 * review is found by the case it judged rather than by scrolling a grouped history, and a
 * policy by its name rather than by filtering a table of a hundred of them.
 *
 * Nothing is fetched until it is opened. Both lists are standing records that most readings
 * never ask for, and the two queries use the keys the Reviews and Policies pages already
 * use — so opening the palette on either page is free, and opening it anywhere else warms
 * the page it is about to send you to.
 */

/* ⌘ on a Mac and Ctrl everywhere else, decided once. Written as the reader's own keyboard
   prints it: a hint that names the wrong key is worse than no hint. `userAgentData` is the
   unprefixed answer where it exists; `userAgent` is the fallback that works everywhere. */
const APPLE = /Mac|iPhone|iPad/.test(
  (navigator as { userAgentData?: { platform?: string } }).userAgentData?.platform ||
    navigator.userAgent,
);
const SHORTCUT_LABEL = APPLE ? "⌘K" : "Ctrl K";

/* What a row is matched on. cmdk scores the whole string, so the identifier rides along
   behind the name: a reader who pasted a review id finds the review, and one who typed two
   words of a case title still finds it first. */
function haystack(...parts: Array<string | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

/* The fact about a row that distinguishes it from the row above — when a review ran, what a
   policy governs. Set against the name rather than under it: a palette row is read in the
   half second before Enter, and a second line would not be. Right-aligned and tabular, so a
   column of dates lines up digit under digit without a column being drawn.
   It steps up an ink on the highlighted row, which is the one row this is actually read on —
   and by night the third ink on the lit ground of a selection is 4.4:1, just under AA. */
const rowMeta =
  "ml-auto flex-none pl-4 text-right text-meta tabular-nums text-ink-3 group-data-[selected=true]/command-item:text-ink-2";

/* A row's name, when the row has one. */
const rowTitle = "min-w-0 overflow-hidden text-ellipsis whitespace-nowrap";

/* And when it does not. A review that failed before composing a report has no case title, and
   its identifier is the only name it ever had — so the identifier is what the row is labelled
   with, set in mono at the meta size to read as one. Left as the sentence-cased title it is
   not, it read as a broken row rather than as a review named by its id. */
const rowId = "font-mono text-meta text-ink-2";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== "k" || !(event.metaKey || event.ctrlKey)) return;
      // Claimed from the browser: ⌘K is a search bar in some of them, and the reader who
      // pressed it inside this app meant this app.
      event.preventDefault();
      setOpen((current) => !current);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const reviews = useQuery({ queryKey: ["reviews"], queryFn: () => api.reviews(), enabled: open });
  const policies = useQuery({ queryKey: ["policies"], queryFn: api.policies, enabled: open });

  const go = (to: string) => {
    setOpen(false);
    navigate(to);
  };

  return (
    <>
      <Button
        type="button"
        onClick={() => setOpen(true)}
        // Announced as the shortcut it stands for, so a reader who never sees the bar is
        // told the keystroke exists rather than only offered the button.
        aria-keyshortcuts="Meta+K Control+K"
        aria-label={`Search and jump to (${SHORTCUT_LABEL})`}
        className="px-2.5"
      >
        <Search size={13} aria-hidden />
        {/* The second ink, not the third: this is 11px of mono on a 5%-white chip by night,
            where the third ink lands at 4.4:1 — under AA, and this is the one word on the
            control that carries the information. */}
        {/* Hidden where the primary pointer is a finger: a keystroke shown to a device
            with no keyboard is not a hint, it is a puzzle. The button itself stays — the
            palette is as reachable by tap as by key — and the aria-label keeps announcing
            the shortcut for the hardware-keyboard readers this heuristic cannot see. */}
        <kbd className="pointer-coarse:hidden font-mono text-micro text-ink-2">{SHORTCUT_LABEL}</kbd>
      </Button>

      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Search and jump to"
        description="Go to a page, a past review or a policy."
      >
        <Command
          loop
          /* Contains, not cmdk's default fuzzy score. Over a haystack this long — a title, an
             identifier and a policy's tags — a subsequence match finds five letters scattered
             across almost every row, so typing "polic" listed the whole corpus. Contains is
             also what the Policies page's own filter does, and one app should not have two
             answers to what searching means. */
          filter={(value, search) =>
            value.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()) ? 1 : 0
          }
        >
          <CommandInput placeholder="Go to a page, a review or a policy…" />
          <CommandList>
            <CommandEmpty>
              {reviews.isLoading || policies.isLoading
                ? "Reading the workspace…"
                : "Nothing matches."}
            </CommandEmpty>

            {/* One glyph per kind of destination, and the same glyph wherever that kind
                appears: the Reviews page and a single review carry the same mark, so a reader
                scanning the list sorts it by shape before reading a word of it. */}
            <CommandGroup heading="Go to">
              <CommandItem value={haystack("Start a review")} onSelect={() => go("/start")}>
                <Compass size={15} aria-hidden />
                Start
              </CommandItem>
              <CommandItem value={haystack("Reviews history")} onSelect={() => go("/reviews")}>
                <ClipboardList size={15} aria-hidden />
                Reviews
              </CommandItem>
              <CommandItem value={haystack("Policies corpus")} onSelect={() => go("/policies")}>
                <BookOpenText size={15} aria-hidden />
                Policies
              </CommandItem>
              <CommandItem
                value={haystack("About how it works method")}
                onSelect={() => go("/about")}
              >
                <Info size={15} aria-hidden />
                About
              </CommandItem>
            </CommandGroup>

            {reviews.data?.length ? (
              <CommandGroup heading="Reviews">
                {reviews.data.map((review) => (
                  <CommandItem
                    key={review.review_id}
                    value={haystack(review.case_title, review.review_id)}
                    onSelect={() => go(`/reviews/${review.review_id}`)}
                  >
                    <ClipboardList size={15} aria-hidden />
                    <span
                      className={review.case_title ? rowTitle : `${rowTitle} ${rowId}`}
                    >
                      {review.case_title || shortId(review.review_id)}
                    </span>
                    {/* Which of a case's reviews this is. A case reviewed four times gives four
                        rows with one name between them, and the date is what tells them apart. */}
                    <span className={rowMeta}>{formatDate(review.created_at)}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ) : null}

            {policies.data?.length ? (
              <CommandGroup heading="Policies">
                {policies.data.map((policy) => (
                  <CommandItem
                    key={policy.id}
                    value={haystack(policy.title, policy.id, policy.tags.join(" "))}
                    onSelect={() => go(`/policies?policy=${encodeURIComponent(policy.id)}`)}
                  >
                    <BookOpenText size={15} aria-hidden />
                    <span className={rowTitle}>{policy.title}</span>
                    <span className={rowMeta}>{humanizeLabel(policy.scope)}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ) : null}
          </CommandList>
          <CommandFooter>↑↓ navigate · ↵ open · esc close</CommandFooter>
        </Command>
      </CommandDialog>
    </>
  );
}
