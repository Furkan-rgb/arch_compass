import { createContext, useContext, useMemo, type ReactNode } from "react";

import { cn } from "../lib/cn";

/* ---------------------------------------------------------------------------------------
   Model prose, and the one piece of Markdown that is allowed to reach it.

   A model writing about code quotes an identifier in backticks, because that is what
   writing about code looks like everywhere else. It does it whether or not we asked: the
   judgement schema says "Prose" and nothing about format, and 64 of the 375 recorded strings
   — about one in six — arrive with a span in them anyway. On two paths the prompt orders it
   outright — the synopsis is told to "name a candidate by the identifier you were given, in
   backticks", and the conversation contract asks for "its backticked participant" — so on
   those two surfaces a backtick is guaranteed, not incidental. Rendering those strings as raw text puts the
   delimiter on screen, which is the bug this file exists for.

   WHY THIS IS NOT `ui/markdown.tsx`. Two reasons, and the first is correctness rather than
   taste. Code identifiers are written in Markdown's own punctuation, so a full pipeline
   changes the name while it renders the sentence: `__init__` in bare prose comes out as a
   bold "init" — two of those and one bare `__file__` sit in the current corpus, so this is
   measured and not hypothetical — `*args` opens emphasis, and `[avoid-duplicated-knowledge]`
   is shortcut link syntax. A wrong name looks exactly like a right one, which makes that a
   worse failure than the backtick it replaces. So this scanner reads inline code spans and
   one other thing, and every character outside those two is emitted exactly as the model
   wrote it.

   The other thing is a citation — `[candidate_…]`, which the conversation contracts hand the
   model as the key to copy into `candidate_ids` and which it writes into its sentences as
   well. It is not Markdown and it is not the model's own punctuation: it is our own
   identifier, arriving in prose because we put it in front of the model, and a reader is
   shown twenty-four characters of SHA-256 where a name should be. `CANDIDATE_REFERENCE` is
   what parses it and `CandidateRef` is what draws it; the exception to "code spans and
   nothing else" is deliberate and it is one grammar wide.

   The second reason is the bundle. `App.tsx` keeps the Markdown renderer in its own lazy
   chunk because react-markdown and its plugins are about a third of it, while the docket and
   the finding detail are in the main one. A hand-written scanner is a few dozen lines and no
   dependency, so the surfaces that need this do not pull that chunk in to get it.

   There is nothing else to gain from a fuller renderer here in any case. Across all 375
   recorded strings there is not one heading, not one bullet and not one `**`; two carry a
   blank line and one of those numbers its points, which is block structure the model wrote
   itself and which `whitespace-pre-line` draws without a renderer. Inline code is the only
   Markdown these fields carry that anything has to parse.
--------------------------------------------------------------------------------------- */

/**
 * The half of a quoted name that carries meaning: the face, and a size relative to its
 * sentence.
 *
 * Mono is the Measured voice — the machine's — and a name the model quotes is machine
 * vocabulary, so switching face mid-sentence is what the system already says about names.
 * The size is `em` rather than a pixel value because the mono reads larger than the sans beside
 * it at the same nominal size; a relative one keeps the quoted name subordinate to the prose
 * around it at every size this is set in, from the 17px question down to the 12px rail. That was
 * measured against Onest and the sans is IBM Plex Sans now — same superfamily as the mono, same
 * skeleton, and a zero of exactly the same 0.600em advance — so the gap this `0.86em` corrects
 * for is probably narrower than it was and has not been re-measured. The relative unit is right
 * either way; the multiplier is the part that wants a browser reading.
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

/**
 * A citation the model wrote into the middle of a sentence, and how it gets a name.
 *
 * `_conversation_finding_text` leads every finding it lists with `[candidate_…] `participant``,
 * because a citation has to copy the identifier exactly. The contract then asks for two things
 * in two places — the backticked participant in the prose, the bracketed identifier in
 * `candidate_ids` — and a model holding both puts the identifier in the prose as well. What a
 * reader gets is thirty-six characters of machine string standing where a name should be, in
 * the one paragraph this product sets at the reading size.
 *
 * The prompt is where that is actually fixed, and both conversation contracts now say the key
 * never goes in a sentence. This is the net under it, because a model will write one anyway —
 * and a net that draws the token as the finding it points at is worth more than one that hides
 * it.
 *
 * Two forms, because a model copies the listing with its brackets and sometimes without them.
 * A token inside backticks is deliberately left alone: a code span's content is never
 * re-parsed here, and a reader who quoted an identifier meant to be shown it.
 *
 * Lower-case hex and at least sixteen of it. Every candidate id in the product is
 * `stable_id("candidate", …)` — the prefix and twenty-four characters of a SHA-256 digest —
 * and the bound is what keeps this off a word that merely starts `candidate_`.
 */
const CANDIDATE_REFERENCE = /\[(candidate_[0-9a-f]{16,})\]|(candidate_[0-9a-f]{16,})/;

/** What a surface can say about a cited finding: the words for the sentence, and the rest. */
export type Citation = {
  /**
   * What the sentence calls it — the leaf of the finding's first participant.
   *
   * The leaf and not the qualified name, which is the one decision here worth arguing with. A
   * reference sits inside running text at 0.86em, and `persistence.ports.CaseSnapshotRecorder`
   * is thirty-eight characters that break the measure — which is the defect this whole file
   * exists to stop, arriving by a different door. Two findings can share a leaf; the title
   * disambiguates, and the row it opens settles it.
   */
  name: string;
  /** The qualified name and the claim, for the `title` a leaf alone cannot carry. */
  title: string;
};

type CitationLookup = (candidateId: string) => Citation | undefined;

/**
 * Where a reference gets its name, and what pressing it does.
 *
 * Through context rather than a prop, because `Prose` is a renderer that knows nothing about a
 * review and must not start to: it draws a docket row, a policy body, a question and a
 * clarification answer, and every one of those call sites has its own hand-tuned block around
 * it. A provider is one line at the surface that holds the findings.
 *
 * The default resolves nothing, which is correct rather than merely safe: a surface with no
 * review cannot name a finding, and a reference there falls to its last rung and says so.
 */
const CitationContext = createContext<{ find: CitationLookup; open?: (id: string) => void }>({
  find: () => undefined,
});

/**
 * The findings a block of model prose may cite, for everything drawn inside it.
 *
 * `onOpen` is what makes a reference a control rather than a name. Leaving it off is not a
 * degraded state — the clarification panel genuinely has nowhere to open a row — so the
 * reference gives up the affordance instead of keeping a dead one.
 */
export function Citations({
  find,
  onOpen,
  children,
}: {
  find: CitationLookup;
  onOpen?: (candidateId: string) => void;
  children: ReactNode;
}) {
  const value = useMemo(() => ({ find, open: onOpen }), [find, onOpen]);
  return <CitationContext.Provider value={value}>{children}</CitationContext.Provider>;
}

/**
 * A cited finding, drawn as the way to it.
 *
 * `--mark` is the product's one non-verdict chroma, and `ui/design-system.test.ts` names its
 * three jobs: a file, a policy, and a cited finding. The third had nothing spending it until
 * now — the citation chips under an answer are a list below the prose, which is a footnote,
 * and this is the reference inside the sentence at the moment the sentence gives somebody a
 * reason to go. The idiom is `PolicyRef`'s exactly: mono, the mark, and an underline that
 * firms up under the cursor.
 *
 * `inline`, and it is a `<button>` because the docket's open row is state on the page rather
 * than a URL, so there is no `href` to give it. That costs it WCAG 2.5.8's inline exception as
 * `tests/browser/test_mobile.py` first wrote it — a rule aimed at a real control disguised as
 * a link, which this is the other way round. The sweep's exemption now covers an inline-level
 * control in running text whatever its tag; padding a reference out was never the alternative,
 * because a target is measured on its smaller dimension and a leaf of five characters cannot
 * reach 44px across without spacing out the sentence around it.
 */
function CandidateRef({
  candidateId,
  source,
  bare,
}: {
  candidateId: string;
  source: string;
  bare: boolean;
}) {
  const { find, open } = useContext(CitationContext);
  const cited = find(candidateId);

  // Nothing here can name it: an identifier from another review, or one the model made up.
  // `_cited_candidates` drops those from `candidate_ids` and logs them, so the chips below an
  // answer never show this — prose can, because nothing filters a sentence.
  //
  // The whole identifier and not a truncation. A machine string is a thing somebody copies,
  // and half of one is worse than all of it; the box and the face say it is machine
  // vocabulary, and the title says what happened to it.
  if (!cited) {
    return (
      <code
        className={bare ? INLINE_CODE_BARE : INLINE_CODE}
        title={`This review holds no finding under ${candidateId}`}
      >
        {source}
      </code>
    );
  }

  // Named, with nowhere to go. Drawn as the name the model should have written in the first
  // place — no mark and no underline, because both of those promise a way to somewhere.
  if (!open) {
    return (
      <code className={bare ? INLINE_CODE_BARE : INLINE_CODE} title={cited.title}>
        {cited.name}
      </code>
    );
  }

  return (
    <button
      type="button"
      onClick={() => open(candidateId)}
      title={cited.title}
      className={cn(
        "inline text-mark underline decoration-rule-strong underline-offset-2 transition hover:decoration-current",
        QUOTED_NAME,
      )}
    >
      {cited.name}
    </button>
  );
}

/**
 * One run of the source: literal text, the content of a code span, or a cited finding.
 *
 * A union rather than a pair of booleans, so a renderer that forgets a kind is a type error
 * rather than a span drawn as whatever the last branch happened to be. `text` is the source as
 * the model wrote it in every case, which is what the last rung of a reference falls back to.
 */
type Span =
  | { kind: "text"; text: string }
  | { kind: "code"; text: string }
  | { kind: "ref"; text: string; candidateId: string };

/**
 * The index of a closing run of exactly `length` backticks, or -1.
 *
 * Exactly `length`, per CommonMark's delimiter-run rule: a longer or shorter run is content,
 * which is what makes ``` `` ` `` ``` work at all. A regex over `` `([^`]+)` `` cannot express
 * this — on ``` ``a`b`` ``` it matches the opening pair as an empty span and mangles the rest —
 * so runs are scanned rather than paired.
 *
 * A newline ends the search, which is a deliberate deviation from CommonMark, where a span
 * may cross one and the line ending becomes a space. `ModelProse` sets `whitespace-pre-line`
 * on every block of model prose in the product, so a newline is a visible break the site went
 * out of its way to keep and swallowing one into a chip would delete it — and the recorded
 * corpus does contain them: two judgements break a paragraph, and one of the two numbers its
 * points down the page. It also bounds the damage from a stray backtick to one line rather
 * than to the rest of the paragraph.
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
 * A run of literal text, cut on the citations in it.
 *
 * Run over the text between code spans rather than over the whole source, which is what keeps
 * the two grammars from having to know about each other: a backtick inside a reference is
 * impossible, and a reference inside a code span is a string the reader asked to be shown.
 *
 * The pattern is not global and nothing here holds a `lastIndex`. A module-level global regex
 * carries its own cursor between calls, and this runs once per literal run of every string the
 * product draws.
 */
function references(literal: string): Span[] {
  const spans: Span[] = [];
  let rest = literal;

  for (
    let match = CANDIDATE_REFERENCE.exec(rest);
    match;
    match = CANDIDATE_REFERENCE.exec(rest)
  ) {
    const before = rest.slice(0, match.index);
    if (before) spans.push({ kind: "text", text: before });
    spans.push({ kind: "ref", text: match[0], candidateId: match[1] ?? match[2] ?? "" });
    rest = rest.slice(match.index + match[0].length);
  }

  if (rest) spans.push({ kind: "text", text: rest });
  return spans;
}

/**
 * The source split into literal text, code-span content and citations, and nothing else parsed.
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
      spans.push(...references(literal));
      literal = "";
    }
    spans.push({ kind: "code", text: unpad(source.slice(index, closing)) });
    index = closing + length;
  }

  if (literal) spans.push(...references(literal));
  return spans;
}

/**
 * What may stand between a full stop and the next sentence, and what may open one.
 *
 * A terminator is regularly inside a quotation or a bracket — `("… earn its place".)` — so one
 * closing character is allowed to follow it before the space. What opens a sentence is a
 * capital, a quotation mark, an opening bracket, or a backtick: about one recorded string in
 * six quotes an identifier, and a sentence is allowed to start with the name it is about.
 */
const CLOSES_A_QUOTE = "\"')]’”";
const OPENS_A_SENTENCE = /[A-Z"'`([“‘]/;

/**
 * The stop at `index` closing a list marker rather than a sentence.
 *
 * The rule below is otherwise satisfied by a numbered point: `1.` is a stop, then a space,
 * then a backtick, and a sentence is allowed to open on a quoted name. So the marker was cut
 * off the item it numbers and left trailing the paragraph above — "…architecture and
 * policies:" and "1." on one block, the point itself starting the next. One recorded
 * judgement argues this way, and it rendered exactly like that.
 *
 * The digits have to open their own line, which is what separates a marker from a sentence
 * that happens to end on a numeral: "it bears on policy 3. The evidence follows." is still a
 * boundary, because the run of digits there has words in front of it.
 */
function listMarker(source: string, index: number): boolean {
  let scan = index - 1;
  let digits = 0;
  while (scan >= 0 && source[scan] >= "0" && source[scan] <= "9") {
    scan -= 1;
    digits += 1;
  }
  if (!digits) return false;
  while (scan >= 0 && (source[scan] === " " || source[scan] === "\t")) scan -= 1;
  return scan < 0 || source[scan] === "\n";
}

/**
 * How many blocks a paragraph may be cut into, however many sentences it holds.
 *
 * The cut exists to give the eye a place to come back to on a second reading, and one block
 * per sentence does that at the median, which is three. It stops doing it on the tail: the
 * longest recorded judgement is nineteen sentences, and drawn one to a block it is nineteen
 * short paragraphs eight pixels apart — which is not a rhythm, it is a numbered list of
 * assertions, and the model wrote a stream of consciousness that argues with itself twice. The
 * device that makes the median readable misrepresents the tail, and the tail is the case a
 * reading surface is for.
 *
 * Six, because the p90 is five sentences and the cap has to clear the p90 rather than sit on
 * it: the cap changes 9 of the 375 recorded strings and the other 366 — 97.6% — are cut
 * exactly as they were. Measured by running `sentences(string, Infinity)` over all 375 and
 * counting the parts: 22 strings of one sentence, 91 of two, 145 of three, 73 of four, 29 of
 * five, 6 of six, and nine past six. Nearest-rank p90 is therefore five, and the number this
 * paragraph carried for two passes — four — is the p75. The claim it was supporting survives
 * the correction, because it was never the p90 that mattered: what has to be true is that
 * nine strings in ten are cut exactly as they fall, and 97.6% is well past nine in ten.
 *
 * Those nine are 2.4% of the strings and 5.8% of every character the model has written into
 * this product — 12,170 of 210,745, summed over the same run — and they are the arguments a
 * reading surface exists for, which is why they are packed rather than left as they fall.
 *
 * Six and not eight, and it is the tail that settles it rather than the p90. Eight would take
 * three of the nine out of `pack` and leave the nineteen-, fourteen- and thirteen-sentence
 * arguments in it, which are the three that need it; anything past nineteen brings the
 * failure above back in full. Six also lands the blocks where a reader wants them: across the
 * nine, no packed block runs past 473 characters, which is six line boxes at the measure below
 * — counted in a browser, by rendering all 375 strings through the real `ModelProse` at the
 * 617.12px that measure resolved to under Onest, and clustering a Range per character on the
 * vertical centre of its box. Plex Sans brings the same declaration in to 556.80px, so the
 * sweep wants re-running and the block count it yields can only go up. The line
 * figure here said seven, which is what 473 divided by the average of a full line comes to and
 * not what the browser draws.
 *
 * A cap and not a character budget, because what goes wrong on the tail is the *count* of
 * blocks and not their length: eight pixels between two paragraphs reads as a breath, and the
 * same eight pixels repeated nineteen times reads as a list.
 */
const MOST_PARTS = 6;

/** Where a sentence ends and where the next one starts, which are two positions and not one. */
type Boundary = { ends: number; opens: number };

/**
 * Which boundaries survive when a string has more of them than the cap allows.
 *
 * "Evenly", which `MOST_PARTS` promises, has to mean evenly in the quantity a reader
 * experiences, and that is the *height* of a block rather than the number of sentences in it.
 * The model's sentences run from 14 characters to 1,132 in the recorded corpus, so an even
 * count of them per block is even in nothing: packed by count, the longest recorded judgement
 * opened with 741 characters and closed with 275, and the block a reader met first was ten
 * lines at 1440 and nineteen at 390 — the wall the split exists to break, still first, with
 * four short blocks stacked behind it to prove the split had run.
 *
 * Height is counted in characters because this runs before layout and has no box to ask. That
 * is exact rather than approximate, and only because there is exactly one measure: `ModelProse`
 * sets every block this function produces at one width, so a character count is a line count
 * times a constant and the constant divides out of every comparison below. A second measure at
 * the reading size would make that false, which is the other thing `ui/design-system.test.ts`
 * is protecting when it fails the build on a second block at 16px.
 *
 * Least squares, not minimax. Minimax bounds the tallest block and says nothing about the
 * other five: on the 1,322-character judgement it is satisfied by 122 / 354 / 273 / 185 / 30 /
 * 353, which meets its own bound and puts a thirty-character orphan in the middle of the
 * argument. Squared deviation pulls *every* block towards the share, which is what a reader
 * means by even. The exact optimum is a table of six rows by twenty columns and no heuristic
 * is cheaper than filling it — the arithmetic this replaces, which cut equal spans of
 * characters and moved each division to its nearest boundary, was an approximation of this
 * table that also emitted *fewer* than `mostParts` blocks whenever two divisions landed on the
 * same boundary.
 *
 * The opening block is the one asymmetry, and it is the original complaint written as a
 * constraint rather than as a hope. A reader decides whether to read an argument from the block
 * they arrive at, so that block carries no more than its share and the rest of the string
 * absorbs the difference. The share is the mean, so a block at or under it can never be the
 * tallest — which makes "the argument never opens on its own wall" a property of this function
 * and not an observation about today's corpus. One sentence always passes the ceiling, because
 * a sentence is the smallest block there is and no rule makes a 354-character sentence shorter
 * — and that escape is reached, on three of the nine, where the opening sentence is already
 * over the share. The guarantee is narrower there and still holds: the block is the shortest
 * opening the string admits, and on none of the nine is the first block the tallest.
 *
 * WHAT THIS DOES NOT PROMISE, written down because a guarantee stated without its condition is
 * the false comment the rest of this file exists to stop. The ceiling is inside `pack`, and
 * `pack` runs only where the model wrote more sentences than the cap allows — nine of the 375
 * recorded strings. On the other 366 every boundary the model wrote is cut, so the blocks *are*
 * those sentences and the opening block is the first of them: the escape above, reached by every
 * string rather than by three. Applying the ceiling regardless would change nothing, and that is
 * measured rather than reasoned — force this function to run on all 375 and 0 of them come back
 * cut differently, because at `count === mostParts` the table has exactly one feasible partition
 * and `through > 1` exempts the single-sentence first block that partition makes. What is left
 * over is not a packing decision at all: it is a sentence the model wrote that is taller than
 * the rest of its string, and the only rule that could shorten one would cut inside it — which
 * every part being a raw slice is the refusal of. Counted at the measure this block had under Onest — 617.12px — in a browser,
 * the same way every other line figure in this file was: two strings open on seven line boxes,
 * four of the corpus's 1,166 blocks are a single sentence of seven lines or more, and the
 * tallest block anywhere is a 1,132-character sentence at **seventeen** — 32 in a phone's 324px
 * column — sitting second in a four-sentence string this function is never handed. Against
 * which: the nineteen-sentence judgement the cap was built for drew 28 line boxes as one block
 * and 54 on the phone, and now opens on three and five. `docs/known-defects.md` carries the
 * decision to leave that where it is and the reason; `ui/prose.test.tsx` fails if the 366 stop
 * being cut this way, on the recorded string that is worst under it.
 *
 * What that costs is real and worth naming, and it is worth naming in line boxes rather than in
 * characters because a line box is what a reader arrives at. On the 2,139-character judgement
 * the ceiling moves the opening block from 406 characters to 157 and the tallest from 406 to
 * 473: at that same 617.12px measure it is six lines at the front traded for three, at the price of
 * one line on the second block, which goes from five to six. On a phone's 324px column it is
 * eleven traded for five. Both counted by rendering the two packings side by side in the built
 * page and clustering a Range per character. What it buys back is
 * a rhythm the corpus turns out to want anyway — on all nine strings the first block comes out
 * as the opening sentence and nothing packed in behind it, and the model almost always opens by
 * naming what was detected. So a long argument now opens on a two- or three-line statement of
 * the thing in question and argues underneath it.
 *
 * That seam was reached by arithmetic, and reaching it by reading the model's vocabulary is
 * refused deliberately. The corpus closes 102 of 375 on "Therefore", "Thus", "Hence" or
 * "Consequently" and a rule could cut before those, but a layout that keys off what the
 * reasoning *sounds like* is a second reader of the argument, which is the move this repository
 * refuses everywhere else. Punctuation is the model's own formatting and this function may read
 * it; vocabulary is the model's argument and it may not.
 */
function pack(source: string, boundaries: Boundary[], mostParts: number): Set<number> {
  // A block is a subtraction rather than a slice: block `first..through` runs from
  // `opens[first]` to `ends[through]`, so the whitespace at the two cuts that bound it is
  // outside it and the length here is the length the reader is given.
  const count = boundaries.length + 1;
  const opens: number[] = [0];
  const ends: number[] = [];
  boundaries.forEach((boundary) => {
    ends.push(boundary.ends);
    opens.push(boundary.opens);
  });
  ends.push(source.length);
  const span = (first: number, through: number) => ends[through] - opens[first];

  const share = span(0, count - 1) / mostParts;

  // `cost[block][through]` is the least squared deviation that covers the first `through`
  // sentences in exactly `block` blocks, and `opened[block][through]` is where that last block
  // started. Six by twenty at the corpus maximum, which is a few thousand additions on nine of
  // 375 strings and nothing at all on the other 366.
  const cost = Array.from({ length: mostParts + 1 }, () =>
    new Array<number>(count + 1).fill(Infinity),
  );
  const opened = Array.from({ length: mostParts + 1 }, () => new Array<number>(count + 1).fill(-1));
  cost[0][0] = 0;

  for (let block = 1; block <= mostParts; block += 1) {
    for (let through = block; through <= count; through += 1) {
      for (let first = block - 1; first < through; first += 1) {
        if (cost[block - 1][first] === Infinity) continue;
        const length = span(first, through - 1);
        // The ceiling, and the only place any block is held to one. `through > 1` is the escape
        // and it is not a special case: at `through === 1` the block is the opening sentence
        // and there is nothing left to take out of it.
        if (block === 1 && through > 1 && length > share) continue;
        const off = length - share;
        const here = cost[block - 1][first] + off * off;
        // Strictly better, so a tie keeps the earlier arrangement and the same string always
        // packs the same way.
        if (here >= cost[block][through]) continue;
        cost[block][through] = here;
        opened[block][through] = first;
      }
    }
  }

  // Walked back from the end, and it always reaches the start: the first block can always be
  // the opening sentence, and `count > mostParts` leaves enough sentences behind it for the
  // rest. So `mostParts` blocks are always produced, which is the promise the cap makes said
  // exactly rather than approximately.
  const cuts = new Set<number>();
  let through = count;
  for (let block = mostParts; block >= 1; block -= 1) {
    const first = opened[block][through];
    if (block > 1) cuts.add(first - 1);
    through = first;
  }
  return cuts;
}

/**
 * Model prose cut at its own sentence boundaries, byte for byte.
 *
 * The judgement schema asks for "Prose" and says nothing about format, and the model almost
 * always obliges literally: 373 of the 375 recorded reasoning strings hold no newline at all,
 * and the median is 523 characters of unbroken paragraph. A reading surface that wants to
 * give that text a rhythm cannot recover one from whitespace, because on all but two strings
 * there is none to recover. The only seam the text reliably has is the sentence — three of
 * them at the median, one claim each — so that is the seam this finds.
 *
 * The two exceptions are the reason `whitespace-pre-line` is a device and not a guard. Both
 * break a paragraph the model meant to break, and one of them argues its way through a
 * numbered list under that break — so a block the model did write has to survive this, which
 * is what `listMarker` is for. Anything claiming the corpus is uniformly one paragraph is
 * describing a sample rather than the corpus.
 *
 * The rule is deliberately narrow: a terminator, then at most one closing quote or bracket,
 * then whitespace, then something that can open a sentence. A qualified name is safe without
 * an abbreviation list because `src.audiobook.providers.registry` has no space after its
 * dots, and a decimal has none either. What the rule cannot see is a genuine abbreviation
 * followed by a capital — "e.g. The" — and the cost there is one gap in the wrong place, not
 * a changed character: every part is a raw slice of the source, so `__init__` and `*args`
 * come back exactly as they went in and `Prose` still reads the spans out of them.
 *
 * A backtick run is skipped whole, through the same `closingRun` the renderer pairs with, so
 * a full stop inside a quoted name can never become a boundary. Cutting there would leave an
 * unmatched delimiter on each side of the cut and put two literal backticks on screen, which
 * is the one failure this file exists to prevent.
 *
 * The whitespace at a *cut* is dropped, because the layout replaces it with the gap. Join the
 * parts back with a single space and you have the string the model wrote — exactly, on every
 * string that holds no newline, and with the run at each cut collapsed to one space on the two
 * that do. No character that is not whitespace is ever added or lost.
 *
 * Every boundary is found and only some of them are cut, which is what `MOST_PARTS` buys and
 * why the two passes are separate. A boundary that is not cut keeps its own whitespace, in
 * place, inside the part — so packing sentences together restores exactly what the model put
 * between them rather than a space this function guessed at, and the numbered lists survive
 * being packed for the same reason they survive being cut.
 */
export function sentences(source: string, mostParts = MOST_PARTS): string[] {
  // Between the two positions a `Boundary` holds is the whitespace, which a cut drops and a
  // packed boundary keeps.
  const boundaries: Boundary[] = [];
  let index = 0;

  while (index < source.length) {
    if (source[index] === "`") {
      const opening = index;
      while (index < source.length && source[index] === "`") index += 1;
      const length = index - opening;
      const closing = closingRun(source, index, length);
      // An unmatched run is literal text, and the scan resumes after it rather than inside
      // it — `scan` takes the same road, for the same reason: the scan must always advance.
      if (closing !== -1) index = closing + length;
      continue;
    }

    const char = source[index];
    if (char !== "." && char !== "?" && char !== "!") {
      index += 1;
      continue;
    }
    if (char === "." && listMarker(source, index)) {
      index += 1;
      continue;
    }

    let after = index + 1;
    if (after < source.length && CLOSES_A_QUOTE.includes(source[after])) after += 1;
    const gap = after;
    while (after < source.length && /\s/.test(source[after])) after += 1;
    if (after === gap || !OPENS_A_SENTENCE.test(source[after] ?? "")) {
      index = Math.max(after, index + 1);
      continue;
    }

    boundaries.push({ ends: gap, opens: after });
    index = after;
  }

  // A string with no boundary in it is one part, which is one recorded string in seventeen —
  // 22 of the 375, counted by running this function with no cap and keeping the ones that come
  // back as a single part — and every fixture in the tests. The count was right and the
  // fraction it was written as was not: "the twenty-second of the corpus" is 22 strings read as
  // a share, and 22 of 375 is a seventeenth.
  if (!boundaries.length) return [source];

  // Which boundaries to cut at. Below the cap that is all of them, which is 366 of the 375
  // recorded strings: the sentence is the only seam the model reliably wrote, and one block per
  // claim adds nothing the text does not already say. Past the cap some sentences have to share
  // a block, and `pack` is the argument about which of them share one.
  // This branch is also where the opening ceiling stops applying, which is the condition on the
  // guarantee `pack` states — argued in the last paragraph of its comment, where it is also
  // measured.
  const cuts =
    boundaries.length + 1 > mostParts
      ? pack(source, boundaries, mostParts)
      : new Set(boundaries.map((_, position) => position));

  const parts: string[] = [];
  let start = 0;

  boundaries.forEach((boundary, position) => {
    if (!cuts.has(position)) return;
    const part = source.slice(start, boundary.ends).trimEnd();
    if (part) parts.push(part);
    start = boundary.opens;
  });

  const tail = source.slice(start).trimEnd();
  if (tail) parts.push(tail);
  return parts.length ? parts : [source];
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
  // The common case by a wide margin, and the one the docket runs once a row: neither marker
  // in the string means it is its own rendering, with no array and no elements built to say
  // so. Two substring tests rather than one, because a citation is not delimited by a backtick
  // — and `candidate_` is the cheapest thing that can rule one out.
  if (!children.includes("`") && !children.includes("candidate_")) return children;

  const spans = scan(children);
  const className = bare ? INLINE_CODE_BARE : INLINE_CODE;
  // The index is a stable key throughout: the array is rebuilt whole from one string, so a
  // position never holds a different span than it did on the last render of that string.
  return spans.map((span, index) => {
    if (span.kind === "code") {
      return (
        <code key={index} className={className}>
          {span.text}
        </code>
      );
    }
    if (span.kind === "ref") {
      return (
        <CandidateRef
          key={index}
          candidateId={span.candidateId}
          source={span.text}
          bare={bare}
        />
      );
    }
    return span.text;
  });
}

/**
 * A paragraph the model wrote, set the one way the product sets one.
 *
 * This is the exception to the rule the component above states, and the reason it is an
 * exception is that the rule was not holding. `Prose` deliberately owns no block, because a
 * quoted name appears inside a docket row, a citation, a policy body and a question, and each
 * of those has a measure and a clamp argued for where it is used. But three of its call sites
 * are not that: they are the *same paragraph*, in the same voice, at the reading size the
 * design system reserves for it — the model's argument on a finding, the review's synopsis,
 * and a conversation answer. Those three had drifted to `58ch`, `46ch` and `62ch`, only one
 * of them cut into sentences, and `Attribution`'s own doc comment describes two of them as
 * "the same kind of thing" a reader is meant to recognise. Three treatments of one voice is
 * the drift `INLINE_CODE` and `Label` already live here to stop, one level up.
 *
 * `58ch` is the measure, and it is chosen from a floor rather than from a character count.
 * IBM Plex Sans's zero advances 0.600em — 600 units on a 1000 unit em, read off the `hmtx` table
 * of the shipped `plex-sans-400.woff2` — so 1ch is 9.6px at 16px and `58ch` is 556.80px. Under
 * this face the weight is *not* part of the reading, and that is a property of the face rather
 * than a simplification: Plex ships four static cuts and all four advance the zero identically,
 * where Onest was one variable file whose zero narrowed from 665 units to 661.8 between 400 and
 * 600 and made a `ch` on a `font-semibold` block a different width from a `ch` written here. The
 * advances live once, in `ui/font.test-metrics.ts`, with the `fontTools` recipe that reads them
 * off the font; `docs/design-system.md` argues from them.
 *
 * **The floor below is Onest's and the measure above it is Plex Sans's, and until the sweep is
 * re-run this paragraph is comparing two faces.** The widest unbreakable token the corpus set
 * *in Onest* is a 71-character qualified name at 541.7px,
 * and 48 distinct tokens across 51 of the 375 strings are wider than the 324px column a phone
 * gives this block. Both figures come from measuring every whitespace-separated run in the
 * corpus inside a real `ModelProse`, with a Range over the paragraph's own text node; the 543px
 * this used to say was 1.3px out and measured in a probe span rather than in the component.
 * The 48 is one rounding from being 47, and it is worth saying so where it is printed: sorted by
 * width, the last token over the floor is `src.audiobook.synthesis.providers.registry),` at
 * 324.89px against a 324px column, and the same name without its trailing comma is 320.72px and
 * sits under. The floor itself rests on the 541.7px, which clears that column by 217px; the 48
 * describes the tail and is not a threshold anything is chosen from. A
 * measure under that floor breaks a name the model is arguing about across two lines, which is
 * the one thing `wrap-anywhere` cannot do gracefully.
 *
 * How much headroom that leaves has changed and is not yet a measured number. Onest put `58ch`
 * at 617.12px against a 541.7px floor — 75px. Plex Sans puts the same declaration at 556.80px,
 * 15px above a floor that was read in the other face, and the token itself is set in the new one
 * now, so both ends of that subtraction have moved. `features/review/finding-detail.test.tsx`
 * asserts the inequality and it passes; what nobody has is the second reading that would make it
 * mean something. `docs/known-defects.md` carries the re-sweep, and this is the figure in the
 * product most likely to have moved the wrong way.
 *
 * Both counts are over the whitespace-separated runs that fall *outside* a backticked span,
 * with their punctuation left attached, because that is what the line breaker sees: UAX #14
 * forbids a break after an opening bracket and before a closing one, so the widest of them is
 * `(src.audiobook.preparation.providers.base.NarrationPreparationProvider)` with its brackets
 * and not the name inside them. Count the backticked names in as though they were body text
 * and the floor comes out around 600px, which is the arithmetic the next paragraph exists to
 * refuse.
 *
 * "In this face" is the load-bearing half, and reading the floor without it is how the number
 * gets argued up. A backticked name is not set in the body face at 16px: `INLINE_CODE` draws it
 * as a chip in IBM Plex Mono at `0.86em` plus about 10px of border and padding, and the two
 * widest names in the corpus are backticked — 74 characters, 621px as chips under Onest, wider
 * than the measure and wider than any measure a 26.4px line could sweep. Those two do not set
 * the floor and cannot: the chip carries `max-w-full` and `wrap-anywhere` precisely so a name
 * too big for its column folds inside its own box, where the box says the fragments are one
 * name. Only a name the model wrote *without* backticks has nothing around it to say so, and
 * that is the case this measure has to clear. The `46ch` this replaces on the synopsis is
 * 441.60px and under the floor by any reading of it.
 *
 * Above the floor the ceiling is the return sweep, and the figures that describe it were
 * counted in a browser rather than divided out of the measure. How, in enough detail to run
 * again: serve the built bundle, so the face is the shipped woff2 and the CSS is the real one,
 * and wait on `document.fonts.check` for every weight involved, because `font-display: swap`
 * otherwise answers with a fallback whose zero is 0.6299em; take the corpus as the union of
 * `core_finding_cache.finding_json -> reasoning` and
 * `core_review_snapshots.review_json -> findings[].reasoning` from a read-only copy of
 * `.archcompass/workspace.sqlite3`, which is 231 and 148 strings sharing four; render all 375
 * through *this component*, chips and all; and measure each `<p>` with a Range per character,
 * clustering the boxes on the vertical centre of each rect at a 0.6px tolerance, one cluster to
 * a line. Across the **3,248** line boxes that comes to over the whole corpus, a line that is
 * not the last of its block carries a measured average of **75.7** characters — 2,082 such
 * lines — and the fullest anywhere is **90**. The last line of a block is short by construction
 * and says nothing about a measure, which is why it is left out: count every line instead and
 * the average reads **64.5**, which flatters the number by describing the ragged edge rather
 * than the sweep.
 *
 * WHAT "CHARACTERS ON A LINE" MEANS HERE, because it is two choices and each moves every figure
 * in this comment.
 *
 * *Which* characters, first: the block's **rendered** text, which is what a Range indexes and
 * what a reader counts. A quoted name contributes the characters inside the chip and not the
 * backticks around it, so a block holding one is a couple of characters shorter here than the
 * string the model wrote. That matters on the 64 of 375 strings that carry a span and on no
 * others.
 *
 * *Where the space goes*, second. A soft wrap happens at a space and that space is drawn on no
 * line at all, so it belongs to either line or to neither. It is counted here as belonging to
 * **the line it ended**: a line's count runs from its own first visible character up to the next
 * line's first, and the last line of a block takes the rest of the block. The reason is that
 * those spans then partition the block — they sum to its own rendered length, so the figures can
 * be checked against something other than a second run of the same script. They do, for all
 * **1,166** blocks the corpus packs into. Count the visible run instead, first ink to last ink,
 * and 1,058 of those 1,166 stop adding up, 75.7 reads 74.7, 64.5 reads 63.9, and 90 reads 89.
 *
 * The two readings are not one character apart everywhere, and the difference between them is
 * **0.97** — which is just 75.70 minus 74.73, and is stated that way deliberately. It was carried
 * here as a histogram of which lines differ by one and which by none, and that histogram has now
 * been wrong twice in opposite directions: a pass "corrected" 0.97 to 0.98 on it, and 0.97 was
 * right. A figure that two readings of the same sweep already give by subtraction does not need a
 * second derivation, and a second derivation is a second thing to get wrong.
 *
 * What the histogram was reaching for is worth keeping and belongs to the floor argument above
 * rather than here: this corpus does break names at this measure, and `WIDEST_UNBREAKABLE_TOKEN_PX`
 * is where that is counted, against a number a test can resolve.
 *
 * That is a separate question from what is *drawn*, and the two are independent. On what is
 * drawn: "measuring the string rather than the render" names two sweeps, and both were run.
 * Flatten every chip back to body text — `plainProse` first, so a backticked name is drawn as
 * the name — and it gives 3,237 line boxes and **76.07** characters. Draw the recorded string
 * literally instead, backticks and all, and it gives the same 3,237 boxes and **76.24**. The
 * sans is narrower than the chip it replaces, so narrower text fits more of it on a line:
 * measuring the
 * string loses eleven line boxes and reads between a third and half a character **generous**,
 * under either reading. The render is what a reader sweeps. The **73** three passes of this
 * comment carried was attributed to that flattening, and could not have come from it — flattening
 * cannot push the count down. 73.1 is this sweep at **56ch**, which is the likeliest place a 73 came
 * from, and the 3,326 line boxes that travelled with it is reproduced by no method stated in any
 * file here. Both are deleted rather than corrected, because a counterfactual whose method
 * nobody wrote down is a number nobody can check.
 *
 * 90 is the outside edge of what `leading-[1.65]` gets an eye back from, which is what the
 * leading is buying and why this is not `62ch`: the same corpus at 62ch measures **81.6** on
 * average and **96** at its fullest, and 96 is past it. The climb is steady rather than sudden —
 * 73.1 at 56ch, 75.7 at 58, 77.3 at 59, 78.7 at 60, 80.3 at 61, 81.6 at 62, all under the
 * soft-wrap convention stated above — so the measure is
 * at the top of its band rather than in the middle of it, and that is the trade the floor
 * forces: 541.7px of qualified name has to fit on one line, so the band this can be chosen from
 * starts high.
 *
 * One `<p>` per sentence with `mt-2` between them, up to six, because the string has no other
 * seam: the model writes one claim to a sentence and three of them at the median. 8px is half
 * a line box against 26.4px — enough for the eye to find the next start on a second reading,
 * too little to claim paragraph structure the model did not write. `sentences` cuts on raw
 * slices and steps over a backticked name whole, so what is on screen is what was recorded.
 *
 * The six is the tail, and it is `MOST_PARTS` rather than a number here because it is a fact
 * about the corpus and not about this block. The sentence above is true at three sentences and
 * false at nineteen: repeated that many times the same 8px stops reading as a breath and
 * starts reading as a list, which is paragraph structure the model did not write — the exact
 * claim the gap was chosen to avoid making. Past the cap the sentences are packed instead,
 * and the whitespace the model put between the packed ones comes back untouched.
 *
 * Evenly by *length*, and never opening on the tallest block. Packing an even number of
 * sentences into each block reads as even only if the model's sentences are the same length,
 * and on the nine strings that reach the cap they never are: the longest recorded judgement
 * packed by count opened with 741 characters and closed with 275, so the wall the split was
 * built to break survived as the first block. `pack` balances the blocks by squared deviation
 * from their share and holds the opening block at or under that share, which puts the same
 * judgement at 157 / 473 / 368 / 369 / 306 / 461 — three lines at this measure saying what was
 * detected, five on a phone, and the argument underneath them. On none of the nine is the first
 * block the tallest, and the reason that is a guarantee rather than a tally is argued beside
 * `pack` — where it is also a test, because the ceiling that makes it true can be deleted
 * without anything else in this file noticing.
 *
 * It is a guarantee about the nine and not about the other 366. Under the cap every boundary is
 * cut, so the blocks are the model's own sentences and one of them can be a wall on its own: the
 * worst recorded is 673 characters in two sentences, seven line boxes then two — 17 then 4 in a
 * phone's column. No ceiling
 * reaches that, because the block is already one sentence — `pack` says why, with the figures,
 * and `docs/known-defects.md` records that it stays.
 *
 * `whitespace-pre-line` is a device and not a guard. Two recorded judgements break a
 * paragraph of their own and one of them numbers its points under that break, and this is what
 * draws them as the model wrote them; `closingRun` names this class as its reason for refusing
 * to pair a span across a newline.
 *
 * `className` is for the gap above the block and nothing else. `cn` is tailwind-merge, so a
 * measure passed here would replace the one above — which is exactly the drift this component
 * was made to end, and `ui/design-system.test.ts` fails the build on a second block set at the
 * reading size anywhere in the tree.
 */
export function ModelProse({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("min-w-0 max-w-[58ch] text-[16px] leading-[1.65] text-ink", className)}>
      {sentences(children).map((sentence, index) => (
        <p
          key={index}
          className={cn("whitespace-pre-line text-pretty wrap-anywhere", index > 0 && "mt-2")}
        >
          <Prose>{sentence}</Prose>
        </p>
      ))}
    </div>
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
export function plainProse(text: string, find?: CitationLookup): string {
  if (!text.includes("`") && !text.includes("candidate_")) return text;
  return scan(text)
    .map((span) => {
      if (span.kind === "code") return span.text;
      // The same rungs as the drawn reference, flattened: the name where the caller brought a
      // lookup, and the bare identifier where it did not. The brackets come off either way —
      // they are punctuation the model wrote for a renderer, which is the reason a backtick
      // does.
      if (span.kind === "ref") return find?.(span.candidateId)?.name ?? span.candidateId;
      return span.text.replace(/`/g, "");
    })
    .join("");
}
