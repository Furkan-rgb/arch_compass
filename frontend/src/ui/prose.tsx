import type { ReactNode } from "react";

/* ---------------------------------------------------------------------------------------
   Model prose, and the one piece of Markdown that is allowed to reach it.

   A model writing about code quotes an identifier in backticks, because that is what
   writing about code looks like everywhere else. It does it whether or not we asked: the
   judgement schema says "Prose" and nothing about format, and about one reasoning string in
   eight arrives with a span in it anyway. On two paths the prompt orders it outright — the
   synopsis is told to "name a candidate by the identifier you were given, in backticks", and
   the conversation contract asks for "its backticked participant" — so on those two surfaces
   a backtick is guaranteed, not incidental. Rendering those strings as raw text puts the
   delimiter on screen, which is the bug this file exists for.

   WHY THIS IS NOT `ui/markdown.tsx`. Two reasons, and the first is correctness rather than
   taste. Code identifiers are written in Markdown's own punctuation, so a full pipeline
   changes the name while it renders the sentence: `__init__` in bare prose comes out as a
   bold "init" — two of those and one bare `__file__` sit in the current corpus, so this is
   measured and not hypothetical — `*args` opens emphasis, and `[avoid-duplicated-knowledge]`
   is shortcut link syntax. A wrong name looks exactly like a right one, which makes that a
   worse failure than the backtick it replaces. So this scanner reads inline code spans and
   nothing else, and every other character is emitted exactly as the model wrote it.

   The second reason is the bundle. `App.tsx` keeps the Markdown renderer in its own lazy
   chunk because react-markdown and its plugins are about a third of it, while the docket and
   the finding detail are in the main one. A hand-written scanner is a few dozen lines and no
   dependency, so the surfaces that need this do not pull that chunk in to get it.

   There is nothing else to gain from a fuller renderer here in any case: across every
   model-authored string the product has recorded, there is not one heading, bullet, `**` or
   blank line. Inline code is the only Markdown these fields carry.
--------------------------------------------------------------------------------------- */

/**
 * The half of a quoted name that carries meaning: the face, and a size relative to its
 * sentence.
 *
 * Mono is the Measured voice — the machine's — and a name the model quotes is machine
 * vocabulary, so switching face mid-sentence is what the system already says about names.
 * The size is `em` rather than a pixel value because IBM Plex Mono reads larger than Onest
 * at the same size; a relative one keeps the quoted name subordinate to the prose around it
 * at every size this is set in, from the 17px question down to the 12px rail.
 */
const QUOTED_NAME = "font-mono text-[0.86em] wrap-anywhere";

/**
 * Inline code, everywhere in the product. `ui/markdown.tsx` renders authored Markdown and
 * this file renders model prose, and both of them draw a quoted name — one class string in
 * two files is the drift the design system's own guards exist to stop, so the string lives
 * here and the Markdown renderer imports it.
 *
 * `inline-block`, which is load-bearing: an *inline* box fragments across a line break, so
 * an identifier one character too wide for the line left a second chip holding one letter
 * alone on the next — a small grey box that reads as a rendering fault rather than as a
 * name. `bg-sunken` is the ramp's quiet inset and not an alpha of one, so the fill is a real
 * step away from the panel in both themes.
 */
export const INLINE_CODE =
  `inline-block max-w-full rounded-xs border border-rule bg-sunken px-1 py-0.5 text-ink ${QUOTED_NAME}`;

/**
 * The same name with the box taken off, for a surface that is scanned rather than read.
 *
 * `markdown.tsx` already made this exception once, for a heading: a chip inside a title
 * reads as a tag rather than as a title, so the code there keeps the mono face and drops the
 * border, the fill and the padding. The exception generalises, and this is it named.
 *
 * A scanning surface needs it for a second reason the heading did not have. The chip's
 * border plus `px-1 py-0.5` adds about five pixels to every line box it lands in, so one
 * clamped row in a column of forty grows taller than its neighbours and the column stops
 * lining up — on the docket, the delta list and the conversation citations, which are the
 * lists the charter means by "scanning beats reading". The face still says the word is a
 * name; the box, where there is one, is what the row or the surrounding tag already draws.
 */
export const INLINE_CODE_BARE = QUOTED_NAME;

/** One run of the source: either literal text, or the content of a code span. */
type Span = { text: string; code: boolean };

/**
 * The index of a closing run of exactly `length` backticks, or -1.
 *
 * Exactly `length`, per CommonMark's delimiter-run rule: a longer or shorter run is content,
 * which is what makes ``` `` ` `` ``` work at all. A regex over `` `([^`]+)` `` cannot express
 * this — on ``` ``a`b`` ``` it matches the opening pair as an empty span and mangles the rest —
 * so runs are scanned rather than paired.
 *
 * A newline ends the search, which is a deliberate deviation from CommonMark, where a span
 * may cross one and the line ending becomes a space. Two of the surfaces that render model
 * prose set `whitespace-pre-line`, where a newline is a visible break the site went out of
 * its way to keep, and swallowing one into a chip would delete it. It also bounds the damage
 * from a stray backtick to one line rather than to the rest of the paragraph.
 */
function closingRun(source: string, from: number, length: number): number {
  let index = from;
  while (index < source.length) {
    const char = source[index];
    if (char === "\n") return -1;
    if (char !== "`") {
      index += 1;
      continue;
    }
    const start = index;
    while (index < source.length && source[index] === "`") index += 1;
    if (index - start === length) return start;
  }
  return -1;
}

/**
 * CommonMark's padding rule: one space off each end, when there is a space at both ends and
 * the content is not all spaces.
 *
 * It is the whole reason ``` `` ` `` ``` can quote a backtick — without it the chip renders
 * with a space inside each edge and looks like a rendering fault. No recorded string
 * exercises this, so only the unit test beside this file will ever catch it breaking.
 */
function unpad(content: string): string {
  const padded = /^[ \n]/.test(content) && /[ \n]$/.test(content) && /[^ \n]/.test(content);
  return padded ? content.slice(1, -1) : content;
}

/**
 * The source split into literal text and code-span content, and nothing else parsed.
 *
 * An unmatched run is emitted as the literal backticks it is, and the scan resumes *after*
 * it rather than inside it — so a stray backtick costs a reader one visible character
 * instead of swallowing the rest of the sentence into a chip, and the scan always advances.
 */
function scan(source: string): Span[] {
  const spans: Span[] = [];
  let literal = "";
  let index = 0;

  while (index < source.length) {
    if (source[index] !== "`") {
      const next = source.indexOf("`", index);
      const stop = next === -1 ? source.length : next;
      literal += source.slice(index, stop);
      index = stop;
      continue;
    }

    const opening = index;
    while (index < source.length && source[index] === "`") index += 1;
    const length = index - opening;

    const closing = closingRun(source, index, length);
    if (closing === -1) {
      literal += source.slice(opening, index);
      continue;
    }

    if (literal) {
      spans.push({ text: literal, code: false });
      literal = "";
    }
    spans.push({ text: unpad(source.slice(index, closing)), code: true });
    index = closing + length;
  }

  if (literal) spans.push({ text: literal, code: false });
  return spans;
}

/**
 * Model prose with its quoted names drawn as names.
 *
 * Returns a flat list of strings and `<code>` elements — not a paragraph and not a wrapper.
 * That is the design decision this component turns on. Every call site has a hand-tuned
 * class list with an argument written above it: a measure, a leading, a clamp, a
 * `whitespace-pre-line`, an id a label points at. A component that owned the paragraph would
 * have to re-litigate all of them and would delete those arguments in the process. This one
 * replaces `{finding.reasoning}` with `<Prose>{finding.reasoning}</Prose>` and leaves
 * everything around it exactly where it was.
 *
 * `bare` drops the box, for the scanning surfaces `INLINE_CODE_BARE` argues for.
 *
 * The span content goes in as a text child, so React escapes it. There is no
 * `dangerouslySetInnerHTML` anywhere near this: `ui/code.tsx` escapes deliberately because it
 * then colours the result, and there is nothing to colour in a quoted name.
 *
 * Not memoised. The scan is linear over a few hundred characters, and the longest list that
 * runs it is a screen of rows.
 */
export function Prose({ children, bare = false }: { children: string; bare?: boolean }): ReactNode {
  // The common case by a wide margin, and the one the docket runs once a row: no backtick
  // means the string is its own rendering, with no array and no elements built to say so.
  if (!children.includes("`")) return children;

  const spans = scan(children);
  const className = bare ? INLINE_CODE_BARE : INLINE_CODE;
  return spans.map((span, index) =>
    span.code ? (
      // The index is a stable key here: the array is rebuilt whole from one string, so a
      // position never holds a different span than it did on the last render of that string.
      <code key={index} className={className}>
        {span.text}
      </code>
    ) : (
      span.text
    ),
  );
}

/**
 * The same prose as a plain string, for an accessible name.
 *
 * An `aria-label`, a `title`, an `alt` and a live-region announcement are strings: no
 * element can go in one, so there is nothing to draw and the delimiters have to come off
 * instead. A screen reader must not announce "backtick Clock backtick" — the backtick is
 * punctuation the model wrote for a renderer, and the renderer is what is missing.
 *
 * The same scanner as `Prose`, deliberately, so a title and the paragraph it describes can
 * never disagree about where a span was. A backtick still standing in the *literal* text
 * after the paired pass is an unmatched one, and it is dropped rather than kept: `Prose`
 * keeps it because a reader can see a typo for what it is, and a listener gains nothing from
 * hearing it. A backtick inside a span is the opposite case — it is the character the model
 * deliberately quoted — so it survives, and the two functions stay in agreement about every
 * span in the string. `report-surface` already takes the blunt route for a heading label,
 * and `headingSlug` drops backticks by normalising everything that is not a letter.
 */
export function plainProse(text: string): string {
  if (!text.includes("`")) return text;
  return scan(text)
    .map((span) => (span.code ? span.text : span.text.replace(/`/g, "")))
    .join("");
}
