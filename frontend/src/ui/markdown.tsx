import { isValidElement, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "../lib/cn";
import { highlight, isSupported } from "../lib/highlight";
import { INLINE_CODE } from "./prose";

/**
 * The measure this document is read at: one width, for every block in it.
 *
 * `ch` is the advance width of the digit zero, and Onest's is 0.665em at the 400 weight body
 * text is set in — 0.6618em at the 600 the headings here are set in, which is the next
 * paragraph's subject. Two things follow that the type scale asking for `62ch` had neither of in
 * mind. A zero is not an average character — it is 0.665em against the 0.509em a character of
 * this face costs on a full line, which is `ui/prose.tsx`'s measured 617.12px over 75.7 — so a
 * measure of 62 zeros holds about 81 characters and not 62. And 62 of them is a different width
 * on every row of the scale: 577.22px on this document's 14px paragraph, 984.76px on its
 * `font-semibold` 24px title. The document and the render disagreed about the same number while
 * both were called `62ch`, which is why nobody caught it. 30em is what a typographer means by
 * "a measure", and at 14px that is 428px.
 *
 * Which is why this is no longer said in `ch`. A `ch` is relative to the font size of the
 * element it is set on — and to its weight, since Onest ships as one variable file and a
 * heavier instance has a narrower zero — and this one string goes on seven renderers at four
 * sizes, three of them `font-semibold`. `max-w-[46ch]` was 730.63px on the document title at
 * 24px, 547.97px on a section heading at 18px, 456.64px at 15px, and 428.26px on the
 * paragraphs, the lists and a blockquote — four measures wearing one name. The cost is not
 * theoretical. `h2` draws the hairline that opens a section *across the measure*, "because a
 * section opens where the text opens" — and that rule overshot the text beneath it by 119.71px
 * on every section of every report and policy in the product, with the title 302.37px past it
 * again. A rule that stops in the wrong place is the one kind of misalignment a reader cannot
 * read past.
 *
 * Every figure in that paragraph is recomputed, not copied: `ui/markdown.test.tsx` puts `46ch`
 * back onto these very class lists and asserts all six in "resolves the one name `46ch` used to
 * carry to four different widths". Change one here and nothing catches it, which is why the
 * argument is here and the arithmetic is there. The 734 / 551 / 459 / 122 / 306 this paragraph
 * used to carry is the same sum with a 400-weight zero applied to three headings set at 600.
 *
 * The two advances themselves are in `ui/onest.test-metrics.ts`, once, with the `fontTools`
 * recipe that reads them off the shipped `onest.woff2`. They were kept in two test files, and a
 * measurement kept in two places is the same defect as a measurement kept in prose — it drifts,
 * and the second copy is what tells you it drifted, after.
 *
 * `rem` because it is the only unit here that does not move when the font size does. The value
 * is the paragraph's own 46ch at 14px to within a quarter of a pixel — 428px against 428.26px,
 * rounded to a quarter-rem so the class list reads as a value somebody chose rather than as the
 * residue of a division. The paragraph is the row the others come down to, because it is the
 * block a document is actually read in: the headings come down to the body rather than the body
 * going up to them.
 *
 * It lives on the text renderers rather than on the wrapper, because the wrapper is also what
 * a fence and a table are laid out inside, and those want the panel's full width to scroll in.
 */
const MEASURE = "max-w-[26.75rem]";

/**
 * A heading's own anchor, so the contents strip on the report surface can reach it.
 *
 * The two halves are computed from different things — the strip slugs the heading's raw
 * Markdown source, the renderer slugs the parsed children — so the normalisation has to be
 * blunt enough that "## `ports.Clock`" and the text node `ports.Clock` land on the same
 * value. Everything that is not a letter or a digit becomes a separator, which takes the
 * backticks, the em dashes and the dots with it.
 */
export function headingSlug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** The words inside a rendered node, for a heading that needs an id rather than a render. */
function plainText(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(plainText).join("");
  if (isValidElement(node)) return plainText((node.props as { children?: ReactNode }).children);
  return "";
}

/**
 * A heading may be a name.
 *
 * The report leads every finding with its identifier in backticks, because scanning beats
 * reading and a heading is what the eye lands on. Inline code elsewhere is a chip — a border
 * and a fill, so a symbol inside a sentence is visibly not part of it — and a chip is the
 * wrong shape for a heading, which reads as a tag rather than as a title. Inside a heading
 * the code keeps the mono face, which is the part that carries meaning, and drops the box.
 *
 * The exception outgrew the heading: `INLINE_CODE_BARE` in `ui/prose.tsx` is the same
 * decision made for a scanning surface, where a chip's border and padding would grow one
 * clamped row taller than its neighbours. This override stays local because it also resets
 * the size — 0.92em rather than 0.86em, since a heading is set at the display face's own
 * weight and a name inside it must not read as a footnote.
 */
const NAMED_HEADING =
  "wrap-anywhere [&>code]:border-0 [&>code]:bg-transparent [&>code]:px-0 [&>code]:py-0 [&>code]:text-[0.92em]";

/** Everything after `language-` on a fence, which is all the fence tells us. */
function fenceLanguage(className: string | undefined): string | undefined {
  const found = /language-([\w+-]+)/.exec(className ?? "");
  return found?.[1]?.toLowerCase();
}

/**
 * Policy bodies and rendered reports.
 *
 * Every element is given a class here rather than inheriting one from a wrapper, because a
 * policy body is authored Markdown and has to read as a document — headings that are
 * actually headings, tables that scroll rather than overflow, code that stays monospace.
 *
 * The wrapper stays `max-w-none` and each text renderer carries `MEASURE` instead. The
 * report ran the full 1168px of its panel — 166 characters a line at 1440, stacked 130px
 * under a model paragraph that wrapped at its own measure — and capping the wrapper would
 * have taken the panel's width away from the two things that need all of it, a fence and a
 * table.
 */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("max-w-none", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // 24 / 18 / 15, not 20 / 18 / 16. Two pixels between one heading level and the next
          // is not a ramp: at those steps size carries no hierarchy, and in a document whose
          // sections are two hundred pixels apart a reader cannot tell a section from a
          // candidate inside one. The distance now comes from the top of the ramp and from
          // the rule the section heading opens on, rather than from three sizes that agree.
          h1: ({ children }) => (
            <h2
              id={headingSlug(plainText(children))}
              className={cn(
                // `scroll-mt-*` because the contents strip jumps here by anchor, and the
                // review page pins 92px of chrome above the document — the rail and the
                // surface strip — with the contents band itself adding a third at `lg`.
                // Without it every jump lands the heading underneath the thing that took you
                // there.
                "mt-7 mb-3 scroll-mt-24 font-display text-2xl font-semibold tracking-tight text-ink first:mt-0 lg:scroll-mt-36",
                MEASURE,
                NAMED_HEADING,
              )}
            >
              {children}
            </h2>
          ),
          // The hairline is the whole structural signal a top-level section gets, and it is
          // the device the design system already names as the primary one. It used to be
          // twelve pixels of extra margin over a paragraph break — enough to measure and not
          // enough to see, so scrolling the report gave the eye nothing to catch on. The rule
          // runs across the measure rather than across the panel, because a section opens
          // where the text opens.
          h2: ({ children }) => (
            <h3
              id={headingSlug(plainText(children))}
              className={cn(
                "mt-10 mb-4 scroll-mt-24 border-t border-rule pt-7 font-display text-lg font-semibold tracking-tight text-ink first:mt-0 first:border-t-0 first:pt-0 lg:scroll-mt-36",
                MEASURE,
                NAMED_HEADING,
              )}
            >
              {children}
            </h3>
          ),
          h3: ({ children }) => (
            <h4
              className={cn(
                "mt-5 mb-2 font-display text-[15px] font-semibold text-ink first:mt-0",
                MEASURE,
                NAMED_HEADING,
              )}
            >
              {children}
            </h4>
          ),
          // The fourth level carries `MEASURE` like the other six, and it did not: it was the
          // one text renderer in this file left running to the panel's edge, so a `####` label
          // set 1168px wide sat over paragraphs stopping at 428px. Nobody saw it because the
          // guard next door counted the renderers that had a measure instead of requiring one
          // of every renderer that sets text, and eight of nine agreeing on an edge is what
          // that count reports as correct. It is `text-sm`, the same 14px the paragraphs are
          // set at, so 26.75rem is this element's own 46ch and no number moves by adding it.
          h4: ({ children }) => (
            <h5
              className={cn(
                "mt-4 mb-1.5 text-sm font-semibold uppercase tracking-[0.08em] text-ink-3 first:mt-0",
                MEASURE,
              )}
            >
              {children}
            </h5>
          ),
          p: ({ children }) => (
            <p className={cn("my-3 text-sm leading-7 text-ink-2 first:mt-0 last:mb-0", MEASURE)}>
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul
              className={cn(
                "my-3 list-disc space-y-1.5 pl-5 text-sm leading-7 text-ink-2 marker:text-ink-3",
                MEASURE,
              )}
            >
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol
              className={cn(
                "my-3 list-decimal space-y-1.5 pl-5 text-sm leading-7 text-ink-2 marker:text-ink-3",
                MEASURE,
              )}
            >
              {children}
            </ol>
          ),
          strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          blockquote: ({ children }) => (
            <blockquote
              className={cn(
                "my-4 border-l-2 border-rule-strong pl-4 text-sm leading-7 text-ink-3",
                MEASURE,
              )}
            >
              {children}
            </blockquote>
          ),
          code: ({ children, className: codeClass }) => {
            const language = fenceLanguage(codeClass);
            if (!codeClass?.startsWith("language-")) {
              return (
                // The chip's class list moved to `ui/prose.tsx` as `INLINE_CODE`, and this
                // file imports it rather than keeping a copy. `ui/prose.tsx` renders the
                // model's own prose — which quotes identifiers in backticks whether or not
                // this document does — so a quoted name is now drawn in two files, and one
                // class string written twice is exactly the drift the design system's guards
                // exist to stop. The argument for what is in the string lives with it there:
                // `inline-block` so a name too wide for the line wraps inside one chip
                // instead of fragmenting into two, `wrap-anywhere` and `max-w-full` because
                // `overflow.test.tsx` holds the rule that a name inside a sentence breaks
                // rather than pushing the page sideways.
                <code className={INLINE_CODE}>{children}</code>
              );
            }
            // A fence that names a language we hold a grammar for is coloured; one that
            // names something else, or nothing, is left as plain monospace rather than
            // guessed at. Colour here is a claim about what a token means.
            const text = String(children).replace(/\n$/, "");
            if (!isSupported(language)) {
              return (
                <code className={cn("font-mono text-[12px] leading-6", codeClass)}>
                  {children}
                </code>
              );
            }
            return (
              <code
                className={cn("font-mono text-[12px] leading-6", codeClass)}
                dangerouslySetInnerHTML={{ __html: highlight(text, language) }}
              />
            );
          },
          pre: ({ children }) => (
            // `bg-sunken`, not `bg-sunken/70`. An alpha of a ramp token composites to a value
            // on neither ramp — six steps from the panel in light and nineteen in dark — so
            // the same declaration was a real inset in one theme and almost nothing in the
            // other. `--sunken` is the token the elevation ramp names for a code block.
            <pre className="scrollbar-slim my-4 overflow-x-auto rounded-md border border-rule bg-sunken p-3.5 text-[12px] leading-6 text-ink">
              {children}
            </pre>
          ),
          // `text-mark` is the accent, not ink, and the comment that stood here said the
          // opposite: `styles.css` declares `--mark: var(--accent)` in all three of its theme
          // blocks, so this is the deep red in light and `#f27166` in dark. The sentence it
          // taught — "the hue is gone, the weight replaces it" — would have licensed the next
          // `text-mark` somebody added on the strength of it being neutral.
          //
          // The hue is correct and is the design system's third job for the accent: an authored
          // document links out to a source, which is exactly what `--mark` is budgeted for. What
          // the weight and the underline add is that the link is still findable against
          // `text-ink-2` for a reader who cannot separate the two hues. The underline rests at
          // half strength and goes to full on hover, so it still answers the pointer.
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="font-semibold text-mark underline decoration-mark/50 underline-offset-4 transition hover:decoration-mark"
            >
              {children}
            </a>
          ),
          hr: () => <hr className="my-6 border-0 border-t border-rule" />,
          table: ({ children }) => (
            <div className="scrollbar-slim my-4 overflow-x-auto rounded-md border border-rule">
              <table className="w-full border-collapse text-sm">{children}</table>
            </div>
          ),
          // A header strip set into a table is the same thing as a header strip set into a
          // panel, and takes the same ground. It was `bg-sunken/70`, which is an alpha of a
          // ramp step and therefore a grey on neither ramp.
          thead: ({ children }) => <thead className="bg-surface-2">{children}</thead>,
          th: ({ children }) => (
            <th className="border-b border-rule px-3 py-2 text-left text-xs font-semibold uppercase tracking-[0.06em] text-ink-3">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-rule px-3 py-2 align-top leading-6 text-ink-2">
              {children}
            </td>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
