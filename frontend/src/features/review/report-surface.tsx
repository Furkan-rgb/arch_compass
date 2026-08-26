import { useQuery } from "@tanstack/react-query";

import { api, type Review } from "../../api";
import { Button, ExternalButtonLink } from "../../ui/button";
import { Markdown, headingSlug } from "../../ui/markdown";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel } from "../../ui/states";
import { Attribution } from "./finding-detail";

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

/** The pair `report.py` always puts on the identity line, whatever else it prepends to them. */
const IDENTITY_LINE = /\breview \d+ · case revision \d+/;

/**
 * The document minus the three things the page around it is already saying.
 *
 * The summary is the reason this function exists, and the argument for dropping it applies
 * word for word to the two blocks above it: `report.py` opens every document with
 * `# Architecture review — {name}` and an identity line naming the repository, the branch,
 * the commit, the review number and the case revision. The review head prints all five 410px
 * higher and the panel header names the surface between them, so on one screen a reader met
 * the same three facts three times, the largest of them the redundant one. The downloaded
 * Markdown and the CLI keep both, because a document that is attached to a pull request has
 * to say what it is.
 *
 * The summary half is a block *walk*, not a filter. `report.py` writes the whole synopsis
 * inline after the run-in label and nothing normalises the model's text, so a synopsis
 * containing a blank line left its second and later paragraphs behind — printed again under
 * the copy the page had already hoisted. This takes every block from the label up to the next
 * heading, which is what report.py always writes next.
 *
 * The two sides of these literals are in different languages and can drift apart in silence,
 * which is why `tests/browser/test_workspace.py` opens a real report and counts the summary
 * once. Nothing here can catch a rename in Python; that test wants a second assertion
 * counting the title once, for the same reason.
 */
function forThePage(markdown: string): string {
  const blocks = markdown.split("\n\n");
  // The identity line is matched rather than counted to. It is the block after the title in
  // every document `report.py` writes, but a positional drop would take the *headline* off a
  // document that happens not to carry one — and the headline is the counts, which is the one
  // thing the page has nothing else to say. `review N · case revision M` is the pair the
  // builder always emits, whether or not a branch, a commit and a round were put in front of
  // it, so it is what identifies the line.
  let start = 0;
  if (blocks[0]?.startsWith("# ")) {
    start = blocks[1] !== undefined && IDENTITY_LINE.test(blocks[1]) ? 2 : 1;
  }
  const summaryAt = blocks.findIndex(
    (block, index) => index >= start && block.startsWith(SUMMARY_LABEL),
  );
  if (summaryAt === -1) return blocks.slice(start).join("\n\n");
  let end = summaryAt + 1;
  while (end < blocks.length && !/^#{1,6} /.test(blocks[end])) end += 1;
  return [...blocks.slice(start, summaryAt), ...blocks.slice(end)].join("\n\n");
}

/**
 * The document's own top-level sections, as somewhere to jump to.
 *
 * This is the longest document in the product and the only tool for reaching a section of it
 * was the scroll wheel — on a review of forty candidates, one sentence repeats verbatim six
 * times in a single 1100px band. Scanning beats reading, and a reader arrives at a report
 * looking for one section or one candidate.
 *
 * Read off the Markdown source rather than out of the rendered tree, and slugged by the same
 * function the heading renderer uses, so the two halves cannot drift into anchors that point
 * at nothing.
 */
function sectionsOf(markdown: string): Array<{ id: string; text: string }> {
  return [...markdown.matchAll(/^## +(.+)$/gm)].map((match) => ({
    id: headingSlug(match[1]),
    // The label is the heading's words, without the Markdown that decorates them.
    text: match[1].replace(/[`*_]/g, "").trim(),
  }));
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
  const body = forThePage(markdown);
  const sections = sectionsOf(body);
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
          {/* Set as a Judged block, with the component that draws one, rather than as a
              twenty-third hand-rolled copy of the block-label recipe at its own tracking and
              its own weight over a paragraph at its own size, measure and leading. It is the
              same kind of thing as the reasoning on a finding — a paragraph the model wrote,
              which a reader is meant to weigh — and it was the one model-authored paragraph
              in the product that did not look like the others.

              The voice reads "In summary" rather than "Judged", which is the one place this
              component is not naming one of the three. `report.py` labels this paragraph "In
              summary" inside the document a reader can download, and the page is hoisting that
              same paragraph out of it: calling it something else here would leave the page and
              the file disagreeing about what the paragraph is. The identity beside it is the
              attribution, which is the half that was missing. */}
          <Attribution voice="In summary" by={review.synopsis_identity || undefined} />
          <p className="mt-2.5 max-w-[46ch] whitespace-pre-line text-[16px] leading-[1.65] text-ink wrap-anywhere">
            {summary}
          </p>
        </div>
      ) : null}
      {sections.length > 1 ? (
        // A way into the document, pinned under the review's own tab strip so it survives the
        // scroll it exists for. `top-[5.75rem]` is the 48px rail plus the 44px strip at
        // `review-page.tsx`'s `sticky top-12`; below `lg` it scrolls with the page, because a
        // phone has no vertical room to spend on two pinned bands.
        //
        // Wrapping, not a horizontal scroller: a hidden scrollbar over a row of links clips
        // the last of them silently, which is the failure `scroll-edge` exists for elsewhere
        // and a flex-wrap avoids having at all.
        <nav
          aria-label="Sections of this report"
          className="border-t border-rule bg-surface-2 px-4 py-2.5 sm:px-5 lg:sticky lg:top-[5.75rem] lg:z-10"
        >
          <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
            {sections.map((section) => (
              <li key={section.id}>
                <a href={`#${section.id}`} className="group -my-2 inline-block py-2">
                  <Label as="span" className="transition group-hover:text-ink">
                    {section.text}
                  </Label>
                </a>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
      <PanelBody>
        {/* The fourth state. A request that succeeds and returns nothing used to render as a
            panel with a header and a blank body, which reads as a component that failed
            rather than as a review with nothing in it yet — and the download beside it would
            have handed over an empty file without saying so. */}
        {markdown ? (
          // Body prose in full ink here, and nowhere else the renderer is used. The report is
          // the only sustained reading in the product, and at `--ink-2` four full screens of
          // it read as one long caption; a policy body is a reference somebody dips into and
          // keeps the quieter default. The run-ins `report.py` writes are then separated by
          // weight alone, which is what bold is for.
          <Markdown className="[&_p]:text-ink">{body}</Markdown>
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
