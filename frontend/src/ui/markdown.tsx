import { isValidElement, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "../lib/cn";
import { highlight, isSupported } from "../lib/highlight";
import { INLINE_CODE } from "./prose";

/**
 * The measure this document is read at, and why it is not the number the system used to say.
 *
 * `ch` is the advance width of the digit zero, and Onest's digits are wide — about `0.65em` —
 * so the `62ch` the type scale asked for resolved to roughly 650px at the reading size and
 * admitted about 89 lowercase characters a line. The document and the render disagreed about
 * the same number while both were called `62ch`, which is why nobody caught it: 46ch is the
 * same 30em a typographer means by "a measure", said in the unit that keeps it proportional
 * to the size it is set at.
 *
 * It lives on the text renderers rather than on the wrapper, because the wrapper is also what
 * a fence and a table are laid out inside, and those want the panel's full width to scroll in.
 */
const MEASURE = "max-w-[46ch]";

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
          h4: ({ children }) => (
            <h5 className="mt-4 mb-1.5 text-sm font-semibold uppercase tracking-[0.08em] text-ink-3 first:mt-0">
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
          // `text-mark` is ink now, and the paragraph around it is `text-ink-2`, so what
          // used to be a hue is half a step of lightness against its own sentence. The
          // weight is what replaces it — the underline was always here and was never
          // carrying this on its own. It rests at half strength and goes to full ink on
          // hover, so the link still answers the pointer.
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
