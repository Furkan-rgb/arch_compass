import { useQuery } from "@tanstack/react-query";

import { api, type Review } from "../../api";
import { Button, ExternalButtonLink } from "../../ui/button";
import { Markdown } from "../../ui/markdown";
import { Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel } from "../../ui/states";

/**
 * A file of its own so the Markdown engine can be a chunk of its own.
 *
 * `ui/markdown.tsx` and the highlighter under it are ~160KB, and `surfaces.tsx` imported
 * them statically — so opening any review downloaded the whole renderer before the docket
 * painted, for a tab four readers in five never open. `App.tsx` makes exactly this argument
 * for the routes and did not apply it one level down. The page lazies this component, and the
 * bundler follows the import: the Markdown chunk arrives with the Report tab and not before.
 *
 * The report itself is not gated on the review being finished. It is composed for a waiting
 * review too and opens on a line saying it is not final, which is far more use than an empty
 * state — a reviewer part-way through a clarification round can still hand somebody what has
 * been judged so far.
 */

/**
 * The run-in label `workflow/report.py` puts on the summary paragraph.
 *
 * The document carries the summary because it has to stand on its own — downloaded,
 * attached to a pull request, printed by the CLI. The page carries it too, hoisted out of
 * the document and set the way every other model-authored paragraph in the product is set.
 * Both would mean saying it twice on one screen, so the page renders the document without
 * that one paragraph.
 *
 * The two sides of this literal are in different languages and can drift apart in silence,
 * which is why `tests/browser/test_workspace.py` opens a real report and counts the summary
 * once. Nothing here can catch a rename in Python.
 */
const SUMMARY_LABEL = "**In summary.**";

/** The document minus the paragraph the page is about to set for itself. */
function withoutSummary(markdown: string): string {
  return markdown
    .split("\n\n")
    .filter((block) => !block.startsWith(SUMMARY_LABEL))
    .join("\n\n");
}

export function ReportSurface({ review }: { review: Review }) {
  const report = useQuery({
    queryKey: ["review-report", review.id],
    queryFn: () => api.reviewReport(review.id),
    // A review is a record, not a message: it is immutable and sequenced, which is the
    // charter's third commitment. Its report is written once and cannot come back different,
    // so every remount of this tab used to re-download a document that had not changed.
    staleTime: Infinity,
  });
  if (report.isLoading) return <LoadingPanel label="Rendering the report…" />;
  if (report.error) {
    return (
      <ErrorNotice
        error={report.error}
        title="The report could not be read"
        action={
          <Button variant="secondary" size="sm" onClick={() => void report.refetch()}>
            Try again
          </Button>
        }
      />
    );
  }
  const markdown = report.data?.trim() ?? "";
  const summary = review.synopsis?.trim() ?? "";
  return (
    <Panel>
      <PanelHeader
        title="Review report"
        description="The whole review as one document — what was found, what moved since last time, and the context it was judged against. Written to be read away from here."
        actions={
          <ExternalButtonLink
            size="sm"
            href={`/api/reviews/${encodeURIComponent(review.id)}/report`}
            download={`archcompass-${review.id}.md`}
          >
            Download Markdown
          </ExternalButtonLink>
        }
      />
      {/* What the review comes to, before the document that establishes it.

          The counts inside the report say how much there is; a reader arriving at a review
          of forty candidates wants to know what it amounts to, and "1 material, 3 held" is
          not that. Set like the reasoning on a finding — an attribution line in the machine
          voice, then the sentences at the reading size — because it is the same kind of
          thing: a paragraph the model wrote, which a reader is meant to weigh rather than
          take as a reading.

          Absent rather than empty when no model wrote one. A heading over a blank space
          reads as a component that failed, and the document below opens on its counts
          exactly as it did before summaries existed. */}
      {summary ? (
        <div className="border-t border-rule px-4 py-5 sm:px-5">
          <p className="font-mono text-[10.5px] leading-5 text-ink-3 [overflow-wrap:anywhere]">
            <span className="font-semibold uppercase tracking-[0.1em] text-ink">In summary</span>
            {review.synopsis_identity ? ` · ${review.synopsis_identity}` : null}
          </p>
          <p className="mt-3 max-w-[60ch] whitespace-pre-line text-[17px] leading-[1.68] text-ink wrap-anywhere">
            {summary}
          </p>
        </div>
      ) : null}
      <PanelBody>
        {/* The fourth state. A request that succeeds and returns nothing used to render as a
            panel with a header and a blank body, which reads as a component that failed
            rather than as a review with nothing in it yet — and the download beside it would
            have handed over an empty file without saying so. */}
        {markdown ? (
          <Markdown>{withoutSummary(markdown)}</Markdown>
        ) : (
          <EmptyState title="The report is empty">
            This review has been composed but has nothing in it to write up yet. It fills in as
            candidates are judged.
          </EmptyState>
        )}
      </PanelBody>
    </Panel>
  );
}
