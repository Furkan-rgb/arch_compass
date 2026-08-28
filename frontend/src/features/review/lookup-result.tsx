import type { ReactNode } from "react";

import type { InvestigationLookup } from "../../api";
import { cn } from "../../lib/cn";
import { highlight } from "../../lib/highlight";
import { NumberedCode } from "../../ui/code";
import { ArrowRight } from "../../ui/icons";
import { PathRef } from "../../ui/meta";

/**
 * A lookup result drawn as the thing it is, rather than as one grey wall of text.
 *
 * Every result on this surface used to go into one `<code>` at one ink, uncoloured. The user's
 * report was that the code is not colour coded, and it is not — but wrapping the whole surface
 * in `highlight()` would be wrong on nearly half of it, and `lib/highlight.ts` says why in as
 * many words: colours are a claim about what the tokens mean, and code shown in the wrong
 * colours is worse than code shown in none. A list of file paths is not Python. A single line
 * torn out of the middle of a file is not an excerpt a grammar can read.
 *
 * So the dispatch is on `item.tool`, which is a record of what was called, rather than on the
 * shape of the text, which would be a guess. Six tools appear in the store and each is a
 * different shape:
 *
 * | tool              | of 955 | what a result is                                          |
 * | ----------------- | -----: | --------------------------------------------------------- |
 * | `read_file`       |    501 | Python, with a right-aligned line-number gutter baked in   |
 * | `grep`            |    369 | a bare list of paths; sometimes a refusal; rarely, content |
 * | `related_code`    |     39 | a count, then rows of name / kind / location, then arrows  |
 * | `glob`            |     38 | one line: a Python list repr, up to 13,111 characters      |
 * | `search_code`     |      7 | a count, then the same rows as `related_code`              |
 * | `search_policies` |      1 | Markdown                                                   |
 *
 * Measured against a read-only copy of `.archcompass/workspace.sqlite3` on 2026-08-27 —
 * `core_review_snapshots.review_json -> investigation_manifest[].lookups[]`, 955 lookups over
 * 7 reviews. Result length: 1,489 characters at the median, 4,374 at p90, 13,111 at the
 * maximum, and the maximum is a `glob`, on one line.
 *
 * **A tool this file does not name still renders**, through `PlainResult` at the bottom, which
 * is what the whole surface used to be. `flagged_signals`, `ls`, `describe_code` and
 * `read_code` are all reachable from the investigator and none of them occurs in the store, so
 * every rule above is written for a shape somebody has actually produced and nothing is
 * designed for a shape that has never been seen.
 */
export function LookupResult({ item }: { item: InvestigationLookup }) {
  const args = item.arguments ?? {};
  if (item.tool === "read_file") return <ReadFileResult result={item.result} path={args.file_path} />;
  if (item.tool === "grep") return <GrepResult result={item.result} />;
  if (item.tool === "glob") return <GlobResult result={item.result} />;
  if (item.tool === "related_code" || item.tool === "search_code") {
    return <NodeRowsResult result={item.result} />;
  }
  // The one registered grammar this surface can reach for nothing. `ui/markdown.tsx` and its
  // renderer are ~160KB and were deliberately split out of the review bundle — one lookup in
  // 955 comes nowhere near paying for that — but `markdown` is already one of the nine
  // grammars in `lib/highlight.ts`, which `finding-detail.tsx` pulls in for every evidence
  // excerpt on the surface this fold sits on. So the headings are told from the body by the
  // tokeniser that is already here, and the document is not re-rendered as a document.
  if (item.tool === "search_policies") return <PlainResult result={item.result} language="markdown" />;
  return <PlainResult result={item.result} />;
}

/**
 * The box every result sits in, which is the one the fold already had.
 *
 * **A hairline and no fill**, which is the shape a block takes when its container has already
 * spent the ground it would have used. This carried `bg-sunken` — the ramp's name for a code
 * block — while the fold it renders in was `--surface-2`. The fold body is `--sunken` now, so
 * the same declaration became a fill on an identical fill: 1.00:1, with a `--rule` hairline at
 * 1.28:1 light and 1.46:1 dark left as the entire boundary. That is the "outlines around
 * nothing" defect the design system's own diagnosis names, arriving from the other direction —
 * not a chip painted the colour of its container, but a container repainted the colour of its
 * chip.
 *
 * There is no fill that would have worked, and that is worth saying rather than leaving the
 * reader to hunt for one. In dark `--sunken` is the *top* of the neutral ramp, so nothing steps
 * up from it; `--surface` and `--surface-2` are both below it there and above it in light, which
 * is the theme-inverting step this comment used to reject. And this box has two containers, not
 * one: a finding's fold at `--sunken` and a conversation bubble that is not. A boundary is the
 * only device that reads the same on both.
 *
 * So `--rule-strong`, which the system holds a grouping boundary to 1.6:1 for and which measures
 * 1.67:1 on `--sunken` and 1.69:1 on `--surface` in light, 2.32 and 2.34 in dark. `--rule` is
 * under that floor on every one of those grounds, and the rule for a rule that low is to delete
 * it and use space — which is not available here, because the cap and the scroll below need a
 * box with an edge to be clipped by. The policy cards one fold over took the same decision for
 * the same reason.
 *
 * `max-h-64` and `scrollbar-slim` are the other half and neither is negotiable. A 13,111-
 * character result still needs its cap, and the slim scrollbar exists because a Mac hides an
 * overlay scrollbar until it is touched — so a block that ran off its own edge simply ended,
 * mid-line, against a rule.
 *
 * It is a `div` rather than the `<pre>` it was, because four of the six tools' results are not
 * preformatted text at all — they are a list, a state, or a set of rows. The two that are, a
 * read file and a policy, carry their own `<pre>`.
 *
 * `bare` is for the one shape that brings its own padding. `NumberedCode` sets `px-3` on the
 * number column and `py-2.5` on the row holding both columns, so a box adding `px-3 py-2`
 * around it would draw the padding twice.
 */
function ResultBox({
  children,
  bare,
}: {
  children: ReactNode;
  bare?: boolean;
}) {
  return (
    <div
      className={cn(
        "scrollbar-slim mt-1 max-h-64 overflow-auto rounded-md border border-rule-strong",
        !bare && "px-3 py-2",
      )}
    >
      {children}
    </div>
  );
}

/**
 * The application's own trailing sentence about a result, which is not part of the result.
 *
 * `read_file` ends 382 of its 501 results with `[Read 100 lines (lines 1-100 of 624 total).
 * 112 lines remaining from offset 100.]`, and `grep` ends 4 of its 369 with a `Note:`
 * paragraph — one explaining that its patterns are literal, three saying the search stopped
 * early and the matches above are incomplete. Both are prose the tool wrote about its own
 * answer. Left in the body they are a 101st line of Python and a stray paragraph in a list of
 * paths; the second of them is the more expensive, because "these results are incomplete" is
 * exactly the kind of thing a reader weighing a verdict has to see rather than skim past in a
 * monospace wall.
 */
function ResultNote({ children }: { children: ReactNode }) {
  return (
    <p className="mt-2 border-t border-rule pt-2 text-[11px] leading-5 text-ink-2 [overflow-wrap:anywhere]">
      {children}
    </p>
  );
}

/** A result that says nothing came back — a state, not a line of text. */
function NoResult({ children }: { children: ReactNode }) {
  return <p className="text-[11px] leading-5 text-ink-2">{children}</p>;
}

/**
 * The one type every result on this surface is set in.
 *
 * 11px on a 20px leading, which is what the label above a result, the extent beside it, the path
 * rows, the node rows' own three fields, the tool's own trailing note and the plain fallback are
 * already set in. Measured with `getComputedStyle` against the built bundle rather than read off
 * a class list, on the fold `tests/browser/test_lookups.py` draws: 73 elements carry text of
 * their own, and 70 of them resolve to 11px/20px.
 *
 * **The other three are two things, and one of them is an exception to the sentence above.**
 * One is `investigation.closing`, the sentence the judging model wrote, at 13px/24px — a
 * different register, and the fold's own paragraph rather than part of the record. The other two
 * are the `PathRef` that ends a node row: it declares `text-[11px]` and no leading, so it takes
 * the document's unitless 1.5 and its path and its line span draw at **11px on 16.5px**. The
 * node rows are 11px/20px in their name and their kind and 11px/16.5px in their location, and
 * the sentence above said 20px for all of it for as long as nothing measured the second number.
 * `tests/browser/test_lookups.py` asserts the pair now, with a count on each of the two
 * exceptions, so a third leading cannot arrive here in silence the way this one did.
 *
 * **The split it replaces was 33 elements against 37, on that same fold.** `NumberedCode` was
 * lifted out of `SourceExcerpt` and came with the pinned excerpt's 12px on a 1.65 leading, so a
 * `read_file` body drew a step larger than everything around it, and which size a reader got was
 * decided by which tool the model happened to call. Put `RESULT_TYPE` back to the excerpt's pair
 * and rebuild and the fold measures 33 elements at 11px/20px, 37 at 12px/19.8px, and the same 2
 * and 1 exceptions — 73 either way. By frequency the larger half is the bigger one too: 501 of
 * the 955 stored lookups are a `read_file`, 52% against 48%. Either size is defensible on its
 * own; two undeclared sizes answering one question is the fault the fold beside this one spent a
 * pass having removed, where a policy note was set at 14px or at 13px depending on whether a
 * policy bore on the finding.
 *
 * **11px rather than 12px, because a transcript is a record and not an exhibit.** The pinned
 * excerpt is the evidence a finding rests on and keeps its own 12px; this is the trace of what
 * was looked at, and a `read_file` body here sits between a path list and a `Note:` line that
 * are both 11px. The counts do not settle it and this comment claimed for one pass that they did
 * — "29 elements to spare seven" was a reading of an older, three-line fixture, and on the fold
 * as it now stands the 12px half is the larger one. What settles it is the register.
 *
 * It is one string covering both of `NumberedCode`'s columns and it has to stay one: they line
 * up by sharing a size and a leading, and that parameter is typed as the two pairs the product
 * sets rather than as a `string`, so a caller cannot hand it a size with no leading beside it.
 * `tests/browser/test_lookups.py` measures both halves — every number still beside its own line,
 * and every element in the fold at one of the three types named above.
 */
const RESULT_TYPE = "text-[11px] leading-5";

/**
 * `read_file`: the gutter split off, then the file's own language.
 *
 * All 501 stored results carry a right-aligned gutter on every line — `"  1  \"\"\"Provider
 * protocol…"` — and all 501 are `.py`. The gutter has to come off before the body reaches a
 * grammar: `  1  """Provider` handed to Python colours the number as a literal and the parse
 * can go wrong from there, which is the confidently-wrong colouring this product would rather
 * not have at all. `ui/code.tsx` already solved the same problem for a pinned excerpt, so
 * `NumberedCode` draws both — the body highlighted once as one document, the numbers as a
 * separate column that lines up because the two share a line height and neither wraps.
 *
 * The numbers are re-derived from the first line rather than carried through per line, and
 * that is safe because they are contiguous: all 501 stored results number their lines
 * `n, n+1, …` with no gap, so `startLine + index` reproduces the file's own numbering exactly.
 *
 * `languageForPath` comes off `arguments.file_path`, which is evidence rather than a guess —
 * and a `read_file` of something the table does not name simply arrives uncoloured, which is
 * `NumberedCode`'s own behaviour and needs nothing here.
 */
function ReadFileResult({ result, path }: { result: string; path?: string }) {
  const { body, note } = splitTrailer(result);
  const gutter = splitGutter(body);
  if (!gutter) {
    // No gutter on some line of it, so nothing here knows which characters are the file's.
    // Guessing where to cut would mean colouring a shifted string, which is the failure this
    // whole file is about; the raw text is the honest answer.
    return <PlainResult result={result} />;
  }
  return (
    <ResultBox bare>
      <NumberedCode
        code={gutter.code}
        startLine={gutter.startLine}
        path={path}
        type={RESULT_TYPE}
      />
      {note ? (
        <div className="px-3 pb-2">
          <ResultNote>{note}</ResultNote>
        </div>
      ) : null}
    </ResultBox>
  );
}

/**
 * `grep`: paths, a refusal, or — rarely — matched lines. Never colour.
 *
 * 320 of the 369 stored results are a bare list of absolute paths with no line numbers and no
 * matched text; 38 are exactly `No matches found`; 7 are grouped content, and those 7 are
 * exactly the 7 called with `output_mode: "content"`. The remaining 4 are one of the first two
 * shapes with a `Note:` paragraph after it. **Not one is in `path:line:content` form**, which
 * is the shape a reader of this tool would expect and the shape it would be tempting to write
 * a parser for: the tool groups by file and indents the matches under it.
 *
 * None of it is coloured, and the content form is where that decision is load-bearing rather
 * than incidental. A grep line is one line torn out of the middle of a file — it is regularly
 * the inside of a docstring, a continuation of a call that opened three lines above, or a bare
 * `"CATEGORIES",` in a list — and a grammar handed one line has no way to know which. That is
 * the "coin toss on a four-line excerpt" argument in `lib/highlight.ts` at its worst case, one
 * line rather than four.
 *
 * What helps a reader scanning 320 of these is not colour but structure, which is why the path
 * list gets the directory recessive and the basename in full ink. The eye is looking for a
 * filename.
 */
function GrepResult({ result }: { result: string }) {
  const { body, note } = splitTrailer(result);
  if (body.trim() === "No matches found") {
    return (
      <ResultBox>
        <NoResult>Nothing in the repository matched.</NoResult>
        {note ? <ResultNote>{note}</ResultNote> : null}
      </ResultBox>
    );
  }
  const paths = pathLines(body);
  if (paths) {
    return (
      <ResultBox>
        <PathList paths={paths} />
        {note ? <ResultNote>{note}</ResultNote> : null}
      </ResultBox>
    );
  }
  return <PlainResult result={result} />;
}

/**
 * `glob`: the worst reading experience on the surface, and colour is not its fix.
 *
 * All 38 stored results are a single-line Python list repr — `['/.claude/settings.json',
 * '/.github/workflows/format.yml', …]` — and the longest is 13,111 characters on one line,
 * inside a 256px-high box. Wrapped anywhere it becomes an unreadable brick; unwrapped it is a
 * horizontal scroll several screens long. The defect is that a list is being drawn as a
 * sentence, so the repair is to draw it as a list.
 *
 * **When the parse fails the raw string is what renders**, through `PlainResult`, which is
 * what this surface did for every result before today. A result nobody can read is a bad
 * outcome; a result nobody can see is a worse one, and a parser that silently drops what it
 * did not understand is how the second happens. `parsePythonList` returns `null` rather than a
 * partial list for exactly that reason — see its own note on the round trip.
 */
function GlobResult({ result }: { result: string }) {
  const paths = parsePythonList(result);
  if (!paths) return <PlainResult result={result} />;
  if (!paths.length) {
    return (
      <ResultBox>
        <NoResult>No file matched the pattern.</NoResult>
      </ResultBox>
    );
  }
  return (
    <ResultBox>
      <PathList paths={paths} />
    </ResultBox>
  );
}

/**
 * `related_code` and `search_code`: a count, then rows of three fields.
 *
 * A row is `  archcompass.persistence.findings.SQLiteCoreFindingCache  [class]
 * src/archcompass/persistence/findings.py:13-75` — a qualified name, a kind, and a location,
 * separated by two spaces. All 102 rows across the 46 stored results parse; the five kinds
 * seen are `method`, `class`, `function`, `module` and `interface`.
 *
 * The three fields are given three weights rather than one: the name is what the reader is
 * looking for and takes full ink, the kind is a qualifier and recedes, and the location goes
 * through `PathRef` — the product's one device for "this is the way back to the source", which
 * copies `path:line` and offers an editor link where somebody has named an editor. A row here
 * is the same kind of reference an evidence block carries, so it is the same component.
 *
 * `related_code` also emits `A --references--> B  (by parse)`, which is a relationship, and
 * the atlas already has a vocabulary for one: an arrow drawn from the dependent to what it
 * depends on. `features/atlas/controls.tsx` says that in as many words to a reader of the map,
 * and every stored edge is written in that direction — so the arrow here points the same way
 * the map's would, and the relation is named beside it rather than left as the raw
 * `--references-->`. 46 of the 53 stored arrows are `references`, 4 `imports`, 3 `implements`.
 *
 * **The header is only a header when it is a count.** Two of the 39 `related_code` results are
 * not a listing at all — they are the tool refusing a name it does not recognise, in a full
 * sentence — and drawing that sentence as a count line over an empty list would read as a
 * listing that failed. A first line that does not open with a number is the whole result.
 */
function NodeRowsResult({ result }: { result: string }) {
  const lines = result.split("\n");
  const [header, ...rest] = lines;
  if (!/^\d/.test(header)) return <PlainResult result={result} />;
  return (
    <ResultBox>
      <p className="text-[11px] leading-5 text-ink-3 [overflow-wrap:anywhere]">{header}</p>
      {rest.length ? (
        <ul className="mt-1.5 grid gap-1.5">
          {rest.map((line, index) => (
            <li key={index}>{nodeRow(line)}</li>
          ))}
        </ul>
      ) : null}
    </ResultBox>
  );
}

const NODE_ROW = /^ {2}(\S+) {2}\[(\w+)] {2}(\S+?):(\d+)-(\d+)$/;
const NODE_ARROW = /^ {2}(\S+) --(\w+)--> (\S+) {2}\((.+)\)$/;

function nodeRow(line: string) {
  const row = NODE_ROW.exec(line);
  if (row) {
    return (
      <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="font-mono text-[11px] leading-5 text-ink [overflow-wrap:anywhere]">
          {row[1]}
        </span>
        <span className="font-mono text-[11px] leading-5 text-ink-3">{row[2]}</span>
        <PathRef path={row[3]} line={Number(row[4])} endLine={Number(row[5])} />
      </span>
    );
  }
  const arrow = NODE_ARROW.exec(line);
  if (arrow) {
    return (
      <span className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
        <span className="font-mono text-[11px] leading-5 text-ink-2 [overflow-wrap:anywhere]">
          {arrow[1]}
        </span>
        {/* The relation named, then the arrow that says which way it runs — the map's own
            reading, where "an arrow points from a dependent to what it depends on" and every
            stored edge is written in that direction. The glyph is `aria-hidden` and the word
            carries the meaning, which is the argument `features/atlas/detail.tsx` makes about
            its own edge list: an SVG path is not something to announce. */}
        <span className="inline-flex items-baseline gap-1 text-[11px] leading-5 text-ink-3">
          {arrow[2]}
          <ArrowRight aria-hidden="true" className="size-3 self-center" />
        </span>
        <span className="font-mono text-[11px] leading-5 text-ink-2 [overflow-wrap:anywhere]">
          {arrow[3]}
        </span>
        <span className="text-[11px] leading-5 text-ink-3">{arrow[4]}</span>
      </span>
    );
  }
  // A row this does not recognise is still a row. It renders as its own text rather than
  // disappearing, for the reason `GlobResult` gives about a partial parse.
  return (
    <span className="block font-mono text-[11px] leading-5 text-ink-2 whitespace-pre-wrap [overflow-wrap:anywhere]">
      {line}
    </span>
  );
}

/**
 * A list of paths, with the directory recessive and the basename in full ink.
 *
 * This draws 323 grep results and 38 glob results — 361 of the 955, the second largest thing
 * on the surface after `read_file` — and what a reader does with all of them is the same: scan
 * for a filename. Undifferentiated, a row is 39.4 characters of identical grey at the mean and
 * the basename the eye is hunting for is the last 16.5 of them.
 *
 * **323, and not the 320 `GrepResult` counts above.** That 320 is the results which are a bare
 * path list and nothing else. Three more are a path list with a `Note:` paragraph after it, and
 * `GrepResult` takes the note off before this is reached, so those draw a list too. How many
 * results arrive in a given shape and how many reach this component are two questions, and
 * answering the second with the first is exactly how the 358 that stood here came to be three
 * short of the 361.
 *
 * It is deliberately not a `PathRef` a row. That component elides from the head, reserves a
 * 44px touch target and offers an editor link, all of which are right for *a* reference and
 * wrong for a list of hundreds: the eliding would hide the very segment being scanned for, and
 * one stored glob answers with 273 paths, whose targets would stack to 12,012px of control
 * inside a 256px box. 3,573 rows over the 361 results — 3 to a result at the median, 9.9 at
 * the mean.
 */
function PathList({ paths }: { paths: string[] }) {
  return (
    <ul className="grid gap-0.5">
      {paths.map((path, index) => {
        const cut = path.lastIndexOf("/");
        return (
          <li
            key={index}
            className="font-mono text-[11px] leading-5 text-ink-3 [overflow-wrap:anywhere]"
          >
            {cut >= 0 ? path.slice(0, cut + 1) : null}
            <span className="text-ink">{path.slice(cut + 1)}</span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * What every result used to be, and what anything unrecognised still is.
 *
 * `whitespace-pre-wrap` with `wrap-anywhere`, so a result wider than a phone folds instead of
 * running off the block's edge. `language` is passed only where the tool's own name says what
 * the text is — `search_policies` returns Markdown — and where it is absent `highlight`
 * escapes and returns the text, which is the same string React would have rendered.
 *
 * This is the only path in this file that reaches `innerHTML`, along with `NumberedCode`, and
 * both go through `highlight()`: it escapes what it cannot colour and its tokeniser escapes
 * what it can. Every other branch above hands its strings to React as text nodes. "renders a
 * result containing `<script>` as text, on every shape" in `investigation.test.tsx` holds that
 * for all six.
 */
function PlainResult({ result, language }: { result: string; language?: string }) {
  return (
    <ResultBox>
      <pre className="whitespace-pre-wrap font-mono text-[11px] leading-5 text-ink-2 wrap-anywhere">
        <code
          className={language ? `language-${language}` : undefined}
          dangerouslySetInnerHTML={{ __html: highlight(result, language) }}
        />
      </pre>
    </ResultBox>
  );
}

/**
 * The tool's trailing sentence about its own answer, split off the answer.
 *
 * Two forms, and both are anchored to the end of the string after a blank line so nothing in
 * the middle of a result can be mistaken for one: `read_file` writes `[Read 100 lines …]` in
 * brackets, and `grep` writes a paragraph opening `Note:`. 382 of 501 `read_file` results and
 * 4 of 369 `grep` results carry one; no other tool in the store writes either.
 */
export function splitTrailer(result: string): { body: string; note: string } {
  const bracketed = /\n\n\[([^\]]*)]$/.exec(result);
  if (bracketed) return { body: result.slice(0, bracketed.index), note: bracketed[1] };
  const noted = /\n\n(Note: [\s\S]*)$/.exec(result);
  if (noted) return { body: result.slice(0, noted.index), note: noted[1] };
  return { body: result, note: "" };
}

/**
 * A numbered listing split into its numbers and its code.
 *
 * Every line has to carry a number, and `null` when one does not. A partial split would hand a
 * grammar a body that is code on some lines and `  42  code` on others, which is worse than
 * not colouring at all — the whole argument of this file. The separator is two spaces, which
 * is what the tool emits; the leading padding that right-aligns the number varies with the
 * width of the file's last line number and is not part of either column.
 */
export function splitGutter(body: string): { startLine: number; code: string } | null {
  const lines = body.split("\n");
  const split = lines.map((line) => /^ *(\d+) {2}([\s\S]*)$/.exec(line));
  if (split.some((match) => match === null)) return null;
  const numbers = split.map((match) => Number(match![1]));
  return { startLine: numbers[0], code: split.map((match) => match![2]).join("\n") };
}

/** Every non-empty line is an absolute path, or `null` and it is not a path list. */
export function pathLines(body: string): string[] | null {
  const lines = body.split("\n").filter((line) => line.trim());
  if (!lines.length) return null;
  return lines.every((line) => /^\/\S*$/.test(line)) ? lines : null;
}

/**
 * A Python `repr` of a list of strings, as strings — or `null`, which is a real answer.
 *
 * All 38 stored `glob` results parse, and none of their paths contains a quote, a backslash or
 * the `', '` the separator is made of. That is what makes the round trip below a check rather
 * than a formality: the parsed list is re-`repr`'d and compared against the input, so anything
 * carrying an escape this does not implement fails the comparison and comes back `null`
 * instead of coming back subtly wrong. A path silently mangled by a half-implemented unescape
 * is the failure mode worth designing against here — the reader has no way to tell.
 *
 * `null` is not "render nothing". `GlobResult` falls back to the raw string, which is exactly
 * what the surface showed before this file existed.
 */
export function parsePythonList(result: string): string[] | null {
  const trimmed = result.trim();
  if (!trimmed.startsWith("[") || !trimmed.endsWith("]")) return null;
  const inner = trimmed.slice(1, -1).trim();
  if (!inner) return [];
  const items = [...inner.matchAll(/'([^'\\]*)'|"([^"\\]*)"/g)].map(
    (match) => match[1] ?? match[2],
  );
  if (!items.length) return null;
  const quote = inner.startsWith('"') ? '"' : "'";
  const rebuilt = `[${items.map((item) => `${quote}${item}${quote}`).join(", ")}]`;
  return rebuilt === trimmed ? items : null;
}
