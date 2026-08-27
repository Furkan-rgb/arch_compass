import { cn } from "../lib/cn";
import { highlight, languageForPath } from "../lib/highlight";
import { CopyButton } from "./button";
import { PathRef } from "./meta";

/**
 * Code in two columns: the line numbers, and the code.
 *
 * Lifted out of `SourceExcerpt` because a second surface needs the same two columns without
 * the box around them. `features/review/lookup-result.tsx` draws the body of a `read_file`
 * lookup, which arrives from the tool with its numbers already baked into the text as a
 * right-aligned gutter — the one shape that cannot be handed to a Python grammar as it
 * stands, because `  1  def foo():` colours the number as a literal and can derail the parse
 * from there. Splitting the gutter off and rendering it as a column is exactly what this
 * already did, so the transcript takes this rather than growing a second copy of it.
 *
 * It is not `SourceExcerpt` itself over there for one reason: that component's copy button is
 * absolutely positioned against the box, and the transcript's box is the `max-h-64` scroller
 * the fold caps every result with. A button pinned inside a vertical scrollport travels with
 * the content, which is the failure the comment on that button describes, one axis over.
 */
export function NumberedCode({
  code,
  startLine,
  path,
  language,
  className,
}: {
  /** The code alone. Any gutter the source carried must already be off it. */
  code: string;
  /** What the first line of `code` is numbered; the rest count up from it. */
  startLine?: number | null;
  /** The file it was read from; the extension is what decides the colouring. */
  path?: string | null;
  /** Overrides the path, for code that arrived without one — a Markdown fence. */
  language?: string;
  className?: string;
}) {
  const lines = code.split("\n");
  const resolved = language ?? languageForPath(path);
  // The whole excerpt is highlighted once and the numbers are a separate column, because
  // highlighting line by line would end a docstring at every newline and start a new one.
  // The two columns line up because they share a line height and neither of them wraps.
  const coloured = highlight(code, resolved);

  return (
    <div className={cn("scrollbar-slim overflow-x-auto", className)}>
      <div className="flex min-w-full py-2.5 font-mono text-[12px] leading-[1.65]">
        {/* `--ink-3` flat, not `text-ink-3/70`. The tier was split into two values precisely
            so it would clear the AA bar on every ground in both themes; an alpha on top of
            it composited to `#8b8b8b` on this block in light — 3.0:1 — and threw that
            guarantee away on the one line of an excerpt that says which lines of the file
            the claim is about. */}
        <div aria-hidden="true" className="shrink-0 select-none px-3 text-right tabular-nums text-ink-3">
          {lines.map((_, index) => (
            <div key={index}>{startLine ? startLine + index : index + 1}</div>
          ))}
        </div>
        {/* The excerpt is the file's own text, so it stays selectable and copyable without
            the numbers coming with it. */}
        <pre className="min-w-0 flex-1 text-ink">
          <code
            className={resolved ? `language-${resolved}` : undefined}
            dangerouslySetInnerHTML={{ __html: coloured || " " }}
          />
        </pre>
      </div>
    </div>
  );
}

/**
 * A pinned source excerpt.
 *
 * Line numbers are rendered beside the code rather than baked into it, so the excerpt can
 * still be selected and copied as the file's own text.
 */
export function SourceExcerpt({
  excerpt,
  startLine,
  path,
  language,
  className,
}: {
  excerpt: string;
  startLine?: number | null;
  /** The file it was read from; the extension is what decides the colouring. */
  path?: string | null;
  /** Overrides the path, for code that arrived without one — a Markdown fence. */
  language?: string;
  className?: string;
}) {
  const body = excerpt.replace(/\n$/, "");

  return (
    <div className={cn("relative rounded-md border border-rule bg-sunken pr-9", className)}>
      {/* On the box rather than inside the scroller: a button positioned inside an
          `overflow-x-auto` element travels with the code when the excerpt is wider than its
          column, and ends up somewhere in the middle of line one.

          The `pr-9` is the other half of that, and it is on the box rather than on the `pre`
          for the same reason. Reserving the room as padding *inside* the scroller only works
          while the excerpt already fits: the moment it is wider than its column — which is
          most of them, inside the readings column on a laptop — the reserved gutter scrolls
          away to the right and the button lands on top of the `def` line the excerpt was
          pinned for. A gutter on the box is outside the scrollport, so nothing can travel
          under it at any scroll position.

          `--control` rather than the block's own ground: a button filled with `--sunken` is
          the same grey as the code it sits on, so only the icon's strokes said a control was
          there. `--control` is the token that means "this is operable", and it steps away
          from the block in the right direction in both themes — which `bg-surface` would not,
          being brighter than `--sunken` in light and darker in dark.

          Selecting forty lines by hand was the alternative, and it takes the line numbers
          with it on any browser that does not honour `user-select: none` in a copy. What
          goes on the clipboard here is the file's own text, which is what an editor wants
          back. */}
      <CopyButton
        value={body}
        label="Copy the excerpt"
        className="absolute right-1 top-1 z-10 border-rule-control bg-control"
      />
      <NumberedCode code={body} startLine={startLine} path={path} language={language} />
    </div>
  );
}

export function EvidenceBlock({
  description,
  path,
  startLine,
  endLine,
  excerpt,
  className,
}: {
  description: string;
  path?: string | null;
  startLine?: number | null;
  endLine?: number | null;
  excerpt?: string | null;
  className?: string;
}) {
  return (
    // A hairline card, with no fill of its own. It used to be `bg-surface`, and its only
    // ground is the exhibit strip, which is `--surface-2` — so in light it read as a card
    // lifted off the strip and in dark, where `--surface` is seven values *below*
    // `--surface-2`, as a well cut into it. One element meaning the opposite thing in the two
    // themes is the ordering rule at the top of `styles.css` running backwards. The edge
    // draws the card in both, and the only fill inside it is the excerpt's own `--sunken`,
    // which steps away from the strip in the theme's own direction.
    <div className={cn("rounded-md border border-rule", className)}>
      <div className="flex flex-wrap items-start justify-between gap-2 px-3 py-2.5">
        <p className="min-w-0 text-sm leading-6 text-ink">{description}</p>
        {/* The one thing on an evidence block that leads somewhere else. It used to be told
            apart by `--mark`, which is ink now; `PathRef` carries the underline and the
            weight that replaced it, so the affordance stays in one place rather than being
            re-decided beside every excerpt. */}
        {path ? <PathRef path={path} line={startLine} endLine={endLine} /> : null}
      </div>
      {excerpt ? (
        <div className="px-3 pb-3">
          <SourceExcerpt excerpt={excerpt} startLine={startLine} path={path} />
        </div>
      ) : null}
    </div>
  );
}
