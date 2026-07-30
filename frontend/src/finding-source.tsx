import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "./api";
import { HighlightedCode, languageForPath } from "./markdown";
import type { BoundaryExcerpt } from "./types";

/**
 * The code a finding was measured from, on the finding.
 *
 * Open rather than collapsed, matching what the policy bearings above it already do: the
 * substantiation is the reason to believe a verdict, and a reader should not have to go
 * looking for it. Four copies of a constant shown side by side is the finding — describing
 * them is not, and a live conversation asked for exactly this and was told the review "does
 * not include the specific lines of code".
 *
 * What keeps that affordable is that it shows the *recorded span and nothing more*. The
 * detector picks declaration spans, so a duplicated constant is one line per site and a sole
 * implementation is a handful per participant. Surrounding code is the unfold, so the
 * disclosure is for more rather than for the evidence itself.
 *
 * A span that cannot be read says why. The repository has changed since the review ran, or
 * is gone, or the boundary was never written — a reader is better served knowing which than
 * by an empty panel, and none of those makes the finding less real.
 */

const CONTEXT_LINES = 6;

export function FindingSource({
  reviewId,
  reference,
}: {
  reviewId: string;
  reference: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const excerpts = useQuery({
    queryKey: ["review-source", reviewId, reference, expanded],
    queryFn: () =>
      api.reviewSource(reviewId, reference, expanded ? CONTEXT_LINES : 0),
    enabled: Boolean(reviewId && reference),
    // The repository does not change while a page is open, and re-reading it on every
    // focus would re-read files for no new answer.
    staleTime: Infinity,
  });

  const rows: BoundaryExcerpt[] = excerpts.data ?? [];
  if (excerpts.isLoading || rows.length === 0) return null;

  return (
    <div data-slot="source-excerpt" className="mt-4 border-t border-dashed border-rule pt-3">
      <p className="m-0 mb-2 flex flex-wrap items-baseline gap-2 text-meta font-semibold tracking-[.04em] text-ink-3 uppercase">
        The code this was measured from
        <button
          type="button"
          className="ml-auto inline-flex cursor-pointer items-center gap-1 border-0 bg-transparent p-0 text-meta font-medium tracking-normal text-accent-ink normal-case hover:underline"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? (
            <>
              <ChevronUp size={13} aria-hidden /> Just the lines
            </>
          ) : (
            <>
              <ChevronDown size={13} aria-hidden /> Show surrounding lines
            </>
          )}
        </button>
      </p>
      {/* Bounded tracks, for the same reason the ask panel's log needs them: an excerpt is
          as wide as the widest line in the file, and an `auto` track sizes itself to that —
          which widens whatever holds it instead of letting the `pre` below scroll on its
          own. Wide in a finding's reasoning, where the column is wide; out through the edge
          in the ask panel, where the drawer is a fraction of the window. */}
      <ul className="m-0 grid list-none grid-cols-[minmax(0,1fr)] gap-3 p-0">
        {rows.map((row) => (
          <li key={`${row.qualified_name}-${row.location?.path ?? "none"}`}>
            <p className="m-0 mb-1 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-meta [&_code]:text-meta [&_code]:text-ink-2 [&_em]:text-meta [&_em]:not-italic [&_em]:text-ink-3 [&_span]:text-meta [&_span]:text-ink-3">
              <code>{row.qualified_name}</code>
              {row.location ? (
                <span>
                  {row.location.path}:{row.location.start_line}
                </span>
              ) : null}
              {/* The candidate's own words for why this participant is implicated, so a
                  block of code says what it is evidence *of* and not only where it is. */}
              <em>{row.role}</em>
            </p>
            {row.text ? (
              // Coloured from the file's own extension rather than from anything read out of
              // the code. The path is recorded on the excerpt, so the grammar is a fact about
              // the repository and not a guess about a fragment — which is the same rule
              // markdown.tsx applies to fenced blocks, given better evidence.
              <pre>
                <code>
                  <HighlightedCode
                    code={row.text}
                    language={languageForPath(row.location?.path)}
                  />
                </code>
              </pre>
            ) : (
              <p className="m-0 rounded-control border border-dashed border-rule px-3 py-2 text-ui leading-[1.55] text-ink-3">
                {row.unavailable}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
