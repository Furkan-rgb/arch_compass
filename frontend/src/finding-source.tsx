import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "./api";
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
    <div className="finding__source">
      <p className="finding__source-head">
        The code this was measured from
        <button type="button" onClick={() => setExpanded((value) => !value)}>
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
      <ul>
        {rows.map((row) => (
          <li key={`${row.qualified_name}-${row.location?.path ?? "none"}`}>
            <p className="finding__source-at">
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
              <pre>
                <code>{row.text}</code>
              </pre>
            ) : (
              <p className="finding__source-missing">{row.unavailable}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
