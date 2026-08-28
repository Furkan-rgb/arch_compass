import { isValidElement, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "../lib/cn";
import { highlight, isSupported } from "../lib/highlight";
import { INLINE_CODE } from "./prose";

/**
 * The measure this document is read at: one width, for every block in it.
 *
 * `ch` is the advance width of the digit zero, and IBM Plex Sans's is 0.600em at every one of
 * the four cuts this product downloads. Two things follow that the type scale asking for `62ch`
 * had neither of in mind. A zero is not an average character — it is the wider, and how much
 * wider is measured in `ui/font.test-metrics.ts` and nowhere else: `FULL_LINE_CHARACTER` holds
 * that reading for both of the prose corpora this repository sweeps, with the method and the
 * reason the two differ. It stood here as a third copy of one of those readings, written out in
 * em — which is the "a figure in prose is a copy of a measurement, and copies drift" this very
 * comment argues four paragraphs down about its own widths, in the file that argues it. So a
 * measure of 62 zeros holds well over 62 characters. And 62 of them is a different width on
 * every row of the scale: 520.80px on this document's 14px paragraph, 892.80px on its 24px
 * title. The document and the render disagreed about the same number while both were called
 * `62ch`, which is why nobody caught it. 30em is what a typographer means by "a measure", and at
 * 14px that is 420px.
 *
 * Which is why this is no longer said in `ch`. A `ch` is relative to the font size of the
 * element it is set on, and this one string goes on every text renderer here, at four sizes. Put
 * `46ch` back and it resolves to **four** different widths: one each for the 24px title, the
 * 18px section heading and the 15px candidate heading, and one shared by the two blocks at 14px.
 * Four measures wearing one name. The cost is not theoretical. `h2` draws the hairline that opens
 * a section *across the measure*, "because a section opens where the text opens" — and that rule
 * overshot the text beneath it on every section of every report and policy in the product, with
 * the title further past it again. A rule that stops in the wrong place is the one kind of
 * misalignment a reader cannot read past.
 *
 * **Four, and it used to be five, and the difference is a coincidence rather than a repair.**
 * Under Onest — one variable file, `font-weight: 400 700`, a zero that narrowed from 0.665em to
 * 0.6618em as the instance got heavier — the two 14px blocks were *two* widths, because the
 * `####` label is `font-semibold` and the paragraph is not, and that undershoot of about two
 * pixels was the seventh round of wrong numbers on this surface. Plex Sans ships four static
 * cuts that all advance the zero identically, so the pair now genuinely agree. Nothing about the
 * argument changes: the point was never that the spread was large, it was that one name was
 * doing several jobs, and a face whose weights happen to agree is not a promise that the next
 * one will.
 *
 * **Not one of those widths is written in this comment, and that is deliberate.** They are
 * recomputed: `ui/markdown.test.tsx` puts `46ch` back onto these very class lists and asserts
 * all five readings, plus both overshoots, in "resolves the one name `46ch` used to carry to
 * five different widths"; `ui/font.test-metrics.test.ts` holds the same rows in one table beside
 * every other `ch` figure in the repository. Seven rounds of these numbers have now shipped
 * wrong, and the seventh was written by the sixth round's own repair — a figure in prose is a
 * copy of a measurement, and copies drift, which six passes of being careful did not fix. The
 * eighth round would have been this one: the face moved under all of it and every figure here
 * was Onest's for a revision, because the advance was pinned in a constant rather than read off
 * the font. Change a size or a weight below and the tests say which widths moved; change this
 * paragraph and nothing does, which is why the argument is here and every number is there.
 *
 * The advances themselves are in `ui/font.test-metrics.ts`, once, with the `fontTools` recipe
 * that reads them off the shipped woff2 and the weight table and resolver that turn a class list
 * into one of them — a resolver that throws on a weight nobody has measured rather than quietly
 * answering with 400's. They were kept in two test files, and a measurement kept in two places
 * is the same defect as a measurement kept in prose: it drifts, and the second copy is what
 * tells you it drifted, after.
 *
 * `rem` because it is the only unit here that does not move when the font size does. The value
 * is the paragraph's own 46ch at 14px, and under this face it is that exactly rather than to
 * within a rounding: 46 zeros of 0.600em at 14px is 386.40px, which is 24.15rem on the nose.
 * Under Onest the same line was 428.26px and had to be rounded to a quarter-rem so the class
 * list read as a value somebody chose rather than as the residue of a division; a round advance
 * buys that back. The paragraph is the row the others come down to, because it is the block a
 * document is actually read in: the headings come down to the body rather than the body going up
 * to them.
 *
 * It lives on the text renderers rather than on the wrapper, because the wrapper is also what
 * a fence and a table are laid out inside, and those want the panel's full width to scroll in.
 */
const MEASURE = "max-w-[24.15rem]";

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
 * Every tag this pipeline can hand to `components`, so that forgetting one is a type error
 * rather than a defect somebody finds by rendering a fuller document.
 *
 * The renderer used to override eighteen tags, which is what a realistic fixture exercises.
 * The pipeline emits twenty-nine. The eleven with nobody to draw them came out as whatever
 * the browser's own sheet says, which for a block element is the full width of the panel: a
 * `#####` in a policy body drew at **1168px**, at 16px and 400 weight, stacked over paragraphs
 * that stop at `MEASURE`. Every figure in that sentence is a rectangle read out of a headless
 * Chromium serving the built stylesheet, with the shipped face's weights asserted through
 * `document.fonts.check` first.
 *
 * Adding the two missing headings would have fixed the document somebody happened to render
 * and left the other nine — a deleted run, a task checkbox, an image, a footnote reference and
 * the block it points into — for the next accident. So the map is typed as a `Record` over
 * this list instead: a tag in it with no renderer does not compile, and the list is written
 * from `mdast-util-to-hast`'s handlers plus what `remark-gfm` adds (`del`, `input`, `table`
 * and its interior, and the footnote `section`/`sup`) rather than from a document.
 *
 * `ui/markdown.test.tsx` closes the other direction, which a type cannot reach: a tag the
 * pipeline emits that is *missing from this list* would still arrive undrawn. The fixture
 * there is written from the grammar rather than from a sample, and the assertion is that
 * nothing in the rendered tree carries an empty class list.
 */
export const EMITS = [
  "a", "blockquote", "br", "code", "del", "em",
  "h1", "h2", "h3", "h4", "h5", "h6",
  "hr", "img", "input", "li", "ol", "p", "pre", "section",
  "strong", "sup", "table", "tbody", "td", "th", "thead", "tr", "ul",
] as const;

type Emitted = (typeof EMITS)[number];

/**
 * The three that may draw no class of their own, named here so that "every element carries
 * one" can be a rule with three exceptions rather than a guideline.
 *
 * A `br` is a line ending and has no box to style. A `tbody` is the table's own scaffolding:
 * the cells carry the rules and the padding, because a border on a row and a border on a cell
 * collapse into one line whose width neither of them chose. An `li` is the argument written
 * beside its renderer — the list around it owns the measure, the size and the marker — and it
 * is *may* rather than *does* because a task item is the one kind that has something to say.
 *
 * This is what the type cannot reach. `EMITS` makes a tag on the list impossible to forget;
 * a tag *missing from the list* would still arrive undrawn, and undrawn is exactly "no class".
 * So `ui/markdown.test.tsx` renders a fixture written from the grammar and fails on any
 * element outside these three with an empty class list.
 */
export const DRAWS_NO_CLASS: readonly string[] = ["BR", "LI", "TBODY"];

/**
 * A heading, and the two decisions a renderer has to make before drawing one.
 *
 * The anchor is the first, and only the top two levels take one: the contents strip on the
 * report surface jumps to a section, and a slug on a fourth-level label would be an anchor
 * nothing points at.
 *
 * The second is that one heading in a GFM document is not meant to be drawn at all.
 * `remark-gfm` opens the footnotes block with `<h2 class="sr-only" id="footnote-label">`, and
 * this renderer threw both away and substituted its own — so a document with a single
 * footnote in it grew a visible ruled section headed "Footnotes" that its author never wrote,
 * and the id the footnote markup points at went with it. A heading that arrives already
 * hidden stays hidden and keeps its own id.
 */
function Heading({
  as: Tag,
  anchored = false,
  className,
  incoming,
  id,
  children,
}: {
  as: "h2" | "h3" | "h4" | "h5" | "h6";
  anchored?: boolean;
  className: string;
  incoming?: string;
  id?: string;
  children: ReactNode;
}) {
  if (/(?:^|\s)sr-only(?:\s|$)/.test(incoming ?? "")) {
    return (
      <Tag id={id} className="sr-only">
        {children}
      </Tag>
    );
  }
  return (
    <Tag id={id ?? (anchored ? headingSlug(plainText(children)) : undefined)} className={className}>
      {children}
    </Tag>
  );
}

/**
 * The label a heading below the ramp's fourth step takes, which is the fourth step's own.
 *
 * The ramp is 24 / 18 / 15 / 14-uppercase and it is four steps deep because that is what a
 * document set inside a panel has room to be. The fourth step is already the body size and is
 * told apart from a paragraph by case and colour rather than by size, so there is nothing left
 * below it to spend: two more invented steps would differ from the label by something no
 * reader could name, and a step nobody can see is worse than a repeat, because it claims a
 * distinction it does not draw.
 *
 * So the type bottoms out and the *element* carries the depth — `#####` renders an `<h6>`, and
 * `######` renders one too, since there is no seventh level to shift into. No policy body or
 * report in the recorded store uses either level; what they used to do was draw at the panel's
 * full 1168px, which is the reason this constant exists at all.
 */
const DEEPEST = "mt-4 mb-1.5 text-sm font-semibold uppercase tracking-[0.08em] text-ink-3 first:mt-0";

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
 *
 * The type is the point, and it is not decoration on a literal that would compile anyway:
 * `Components` is fully optional, so every one of the eleven tags this file used to ignore
 * type-checked perfectly while drawing at the panel's edge. Keyed over `EMITS` instead, a
 * renderer cannot be forgotten.
 */
const RENDERERS: { [Tag in Emitted]: NonNullable<Components[Tag]> } = {
  // 24 / 18 / 15, not 20 / 18 / 16. Two pixels between one heading level and the next
  // is not a ramp: at those steps size carries no hierarchy, and in a document whose
  // sections are two hundred pixels apart a reader cannot tell a section from a
  // candidate inside one. The distance now comes from the top of the ramp and from
  // the rule the section heading opens on, rather than from three sizes that agree.
  h1: ({ children, className, id }) => (
    <Heading
      as="h2"
      anchored
      incoming={className}
      id={id}
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
    </Heading>
  ),
  // The hairline is the whole structural signal a top-level section gets, and it is
  // the device the design system already names as the primary one. It used to be
  // twelve pixels of extra margin over a paragraph break — enough to measure and not
  // enough to see, so scrolling the report gave the eye nothing to catch on. The rule
  // runs across the measure rather than across the panel, because a section opens
  // where the text opens.
  h2: ({ children, className, id }) => (
    <Heading
      as="h3"
      anchored
      incoming={className}
      id={id}
      className={cn(
        "mt-10 mb-4 scroll-mt-24 border-t border-rule pt-7 font-display text-lg font-semibold tracking-tight text-ink first:mt-0 first:border-t-0 first:pt-0 lg:scroll-mt-36",
        MEASURE,
        NAMED_HEADING,
      )}
    >
      {children}
    </Heading>
  ),
  h3: ({ children, className, id }) => (
    <Heading
      as="h4"
      incoming={className}
      id={id}
      className={cn(
        "mt-5 mb-2 font-display text-[15px] font-semibold text-ink first:mt-0",
        MEASURE,
        NAMED_HEADING,
      )}
    >
      {children}
    </Heading>
  ),
  // The fourth level carries `MEASURE` like the rest, and it did not: it was the one
  // text renderer in this file left running to the panel's edge, so a `####` label set
  // 1168px wide sat over paragraphs stopping at the measure. Nobody saw it because the
  // guard next door counted the renderers that had a measure instead of requiring one of
  // every renderer that sets text, and eight of nine agreeing on an edge is what that
  // count reports as correct.
  //
  // The sentence that used to close this comment said the label "is `text-sm`, the same
  // 14px the paragraphs are set at, so this is this element's own 46ch and no number moves
  // by adding it" — written one screen below the paragraph explaining that a `ch` follows
  // weight, in the pass whose whole subject was that. `DEEPEST` is `text-sm` *and*
  // `font-semibold`, and under Onest that made this element's own 46ch land two pixels
  // short of the paragraph's, because one variable file gives a heavier instance a
  // narrower zero.
  //
  // Under IBM Plex Sans the two are the same width, because four static cuts advance the
  // zero identically — so the sentence is now true and was still wrong to write, which is
  // the more useful version of the lesson. What this element gets from `MEASURE` is the
  // paragraph's edge, and that is the right edge for it to take whether or not its own
  // agrees: a document is read in its body text, so a label sits over the column the
  // paragraphs make rather than over one only it would ever draw. Both widths are computed
  // and asserted in `ui/font.test-metrics.test.ts` and again, off these very class lists,
  // in `ui/markdown.test.tsx` — no figure for either is written here, because this comment
  // is the seventh round of a figure written here being wrong.
  h4: ({ children, className, id }) => (
    <Heading as="h5" incoming={className} id={id} className={cn(DEEPEST, MEASURE)}>
      {children}
    </Heading>
  ),
  // The bottom of the ramp, twice — see `DEEPEST`. Both had no renderer at all until this
  // pass and drew at 1168px against a paragraph stopping at the measure, which is the widest
  // single mismatch measured anywhere in the product.
  h5: ({ children, className, id }) => (
    <Heading as="h6" incoming={className} id={id} className={cn(DEEPEST, MEASURE)}>
      {children}
    </Heading>
  ),
  h6: ({ children, className, id }) => (
    <Heading as="h6" incoming={className} id={id} className={cn(DEEPEST, MEASURE)}>
      {children}
    </Heading>
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
  // An item takes no measure and no size: the list around it carries both, and one that
  // capped itself would stop a bullet's text short inside a list that had already stopped.
  //
  // What it does carry is the one case where a list item is not a bullet. `remark-gfm` marks
  // a task item `task-list-item` and puts a checkbox in it, and the disc the list draws is
  // then a second marker beside the box — two glyphs for one item. The marker goes and the
  // item steps back into the `pl-5` gutter, so the checkbox sits where the disc was rather
  // than indented past it.
  li: ({ children, className }) => (
    <li className={cn(className, /(?:^|\s)task-list-item(?:\s|$)/.test(className ?? "") && "-ml-5 list-none")}>
      {children}
    </li>
  ),
  // The only `<input>` a Markdown document can produce: `remark-gfm`'s task checkbox, always
  // disabled, because the document is a rendering of a file and ticking it here would change
  // nothing. `readOnly` as well as `disabled` so React does not warn about a controlled box
  // with no handler; `accent-ink` because a checkbox is not one of the four things the accent
  // is budgeted for, and a tick in the brand red would read as a verdict.
  input: ({ checked, type }) => (
    <input
      type={type}
      checked={checked}
      readOnly
      disabled
      className="mr-2 size-3.5 translate-y-[1px] accent-ink"
    />
  ),
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  // A deletion recedes rather than shouts: the line is the signal and `--ink-3` is what the
  // rest of the system uses for something a reader may skip. Drawn with `--rule-strong`, the
  // hairline this document already strikes with, so the stroke is the document's own weight
  // and not the browser's 1px of full ink.
  del: ({ children }) => (
    <del className="text-ink-3 line-through decoration-rule-strong">{children}</del>
  ),
  // A hard break. It draws no box, so there is nothing to give a class to — see
  // `DRAWS_NO_CLASS`, which is what keeps that from being an oversight indistinguishable
  // from this one.
  br: () => <br />,
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
      return <code className={cn("font-mono text-[12px] leading-6", codeClass)}>{children}</code>;
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
  // The cap that matters here is `max-w-full`, and it is the only one this element gets to
  // choose. An image wider than its column is the one thing on this surface that can push the
  // whole page sideways, and an intrinsic width is a fact about a file rather than a decision
  // anybody made about this layout. What stops it at the measure in practice is the paragraph:
  // Markdown puts a lone image inside one, and that paragraph already carries `MEASURE`. Which
  // is also why `block` is load-bearing — inside a paragraph an inline box sits on the text
  // baseline and ignores its own margins, so the figure would ride up against the line above.
  img: ({ src, alt, title }) => (
    <img
      src={src}
      alt={alt ?? ""}
      title={title}
      className="my-4 block h-auto max-w-full rounded-md border border-rule"
    />
  ),
  // `text-mark` is a hue of its own now, and this is the link it was added for: an authored
  // document pointing out of itself at a source. Under v1 `--mark` was declared as
  // `var(--accent)` — the alarm red under a second name — so a citation in a policy said *act
  // on this*; it is `#0053a0` in light and `#4ca8ff` in dark, and the comment that stood here
  // arguing the red is gone with it.
  //
  // What the weight and the underline add is that the link is still findable against
  // `text-ink-2` for a reader who cannot separate the two hues.
  //
  // The underline is `--mark-edge` and goes to `--mark` on hover, which is the two tiers doing
  // exactly what they are for: a rule is a graphic and clears 3:1 (4.28:1 in light, 5.00:1 in
  // dark), the word is text and clears 4.5 (7.64:1 and 7.18:1). It was `decoration-mark/50`,
  // an alpha of a signal mixed at the call site, which composited to 2.47:1 in light and
  // 2.70:1 in dark — under the graphic floor in both, and a value no test could see because it
  // was never declared anywhere. `PathRef` in `ui/meta.tsx` draws the same pair; this is the
  // second place that gesture is written and the two now agree.
  //
  // `target="_blank"` only on a link that actually leaves. A footnote reference and the
  // arrow back out of a footnote body are both links to a fragment of this same document,
  // and opening one in a new tab lands the reader in a blank page scrolled to an anchor
  // that is not there.
  a: ({ children, href }) => {
    const leaves = !(href ?? "").startsWith("#");
    return (
      <a
        href={href}
        target={leaves ? "_blank" : undefined}
        rel={leaves ? "noreferrer" : undefined}
        className="font-semibold text-mark underline decoration-mark-edge underline-offset-4 transition hover:decoration-mark"
      >
        {children}
      </a>
    );
  },
  // A footnote reference. The browser's own `<sup>` is 0.65em with `vertical-align: super`,
  // which at the paragraph's 14px is a 10.5px mark carrying a link's weight and hue — small
  // enough to read as a rendering artefact rather than as something to press. 0.8em keeps it
  // subordinate and keeps the touch target of the link inside it usable.
  sup: ({ children, id }) => (
    <sup id={id} className="text-[0.8em] leading-none">
      {children}
    </sup>
  ),
  // The footnotes block, which is the only `<section>` this pipeline emits. Its heading is
  // `sr-only` by GFM's own design — see `Heading` — so without a rule here the notes would
  // arrive attached to the last paragraph of the document with nothing to separate them. The
  // rule is the same device `h2` opens a section with, and it stops where the text stops.
  section: ({ children, id }) => (
    <section
      id={id}
      className={cn("mt-10 border-t border-rule pt-6 text-sm leading-7 text-ink-3", MEASURE)}
    >
      {children}
    </section>
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
  tbody: ({ children }) => <tbody>{children}</tbody>,
  // The last row drops its cells' rule, because the wrapper already draws one there: a
  // `border-b` on the final `<td>` lands a hairline one pixel above the rounded border of
  // the box the table scrolls in, and two parallel hairlines a pixel apart read as a
  // rendering fault rather than as a table's foot.
  tr: ({ children }) => <tr className="[&:last-child>td]:border-b-0">{children}</tr>,
  // The block-label row of the scale, which is where a table head belongs: 11px, 700, `0.08em`,
  // uppercase. It was 12px semibold at `0.06em` — its own recipe, a third of a tier off the one
  // every other uppercase run in the product is set in, and the kind of near-miss that reads as
  // a rendering inconsistency rather than as a decision. `ui/panel.tsx`'s `Label` is the same
  // four values; this is not that component only because a `<th>` cannot be one.
  th: ({ children }) => (
    <th className="border-b border-rule px-3 py-2 text-left text-[11px] font-bold uppercase tracking-[0.08em] text-ink-3">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-b border-rule px-3 py-2 align-top leading-6 text-ink-2">{children}</td>
  ),
};

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("max-w-none", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={RENDERERS}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
