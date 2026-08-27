import type { HTMLAttributes, ReactNode } from "react";

import { useCopy } from "../lib/clipboard";
import { cn } from "../lib/cn";
import { editorHref, useEditorScheme } from "../lib/editor";
import type { Tone } from "../lib/format";
import { CheckIcon, OpenExternalIcon } from "./icons";
import { Label } from "./panel";

/**
 * Identifiers, paths, commits, fingerprints, model identities. Monospace, always.
 *
 * `wrap-anywhere` because every one of those is a single word to the line breaker and most
 * of them are wider than a phone — `openai/gpt-4o-2024-08-06@sha256:9f2c…` in a `MetaRow`
 * on a 390px screen has nowhere to break, so it painted past its cell and took the page
 * sideways with it. Where an ancestor asks for `truncate` instead, that wins: `truncate`
 * sets `white-space: nowrap`, which inherits, and nothing can wrap under it.
 *
 * 11px, which is the row the type scale gives this component's own job — *provenance, meta
 * lines, identities, namespaces*. It defaulted to 12, the row reserved for footnotes and
 * counts, and 44 of its 80 call sites wrote a smaller size back on by hand. A default nobody
 * chose for the common case is the same drift the `Label` docstring exists to prevent, one
 * component over. The sites that genuinely want 12px or more still say so.
 */
export function Mono({
  children,
  className,
  ...props
}: { children: ReactNode; className?: string } & HTMLAttributes<HTMLSpanElement>) {
  return (
    <span {...props} className={cn("font-mono text-[11px] text-ink-2 wrap-anywhere", className)}>
      {children}
    </span>
  );
}

/**
 * A source path with an optional line span: the way back to the file a claim was measured
 * from, and the one place in this file that has to say "this goes somewhere".
 *
 * It said it with a chip — a border and a fill — on top of `--mark`. `--mark` is ink now, on
 * the argument that a fourth hue beside three verdicts makes a reader work out which of the
 * four carries meaning. That left the box doing the whole job, and a box is what this system
 * puts around a *block*, not around a reference; beside `Mono`, which is the same face at
 * the same size, the only difference was a hairline.
 *
 * So the affordance is an underline and a weight, which is what the rest of the system uses
 * for "this leads to the source" and what survives being the same colour as its neighbours.
 *
 * **And now it leads somewhere.** For a long time this was an underline that went nowhere:
 * it wore the one decoration the system reserves for "this goes to the source" and did
 * nothing at all when pressed, which is a worse promise than no promise. Pressing it copies
 * `path:line` — the form an editor's *go to file* box takes, and the form a reviewer pastes
 * into a message — and where somebody has said which editor they use, an *open* control
 * appears beside it. The link is not offered by default; see `lib/editor.ts` for why.
 */
export function PathRef({
  path,
  line,
  endLine,
  className,
}: {
  path: string;
  line?: number | null;
  endLine?: number | null;
  className?: string;
}) {
  const span = line ? (endLine && endLine !== line ? `:${line}-${endLine}` : `:${line}`) : "";
  const { copied, copy } = useCopy();
  // `path:line` rather than the rendered span: a range reads well on screen and is not what
  // any editor or any search box accepts.
  const value = line ? `${path}:${line}` : path;
  const href = editorHref(path, line, useEditorScheme());

  return (
    <span className={cn("flex min-w-0 max-w-full items-baseline gap-1.5", className)}>
      {/* Still `title` rather than `ui/tooltip.tsx`, deliberately. The full path is already
          in the accessible name, so the attribute is not the only route to it — it is the
          pointer's route to an elided string, which is the one thing `title` is decent at.
          And a `PathRef` is not one control: a docket of forty findings draws one per
          evidence block, and a Radix root under each of them is machinery per row for a
          string a reader can also just widen the window to see. */}
      <button
        type="button"
        onClick={() => void copy(value)}
        title={`${path}${span} — click to copy`}
        aria-label={copied ? `Copied ${value}` : `Copy ${value}`}
        className={cn(
          // `truncate` and `max-w-full`: an absolute path is one word and is wider than a
          // phone, and a reference that widens its own column is worse than an elided one.
          //
          // It elides from the *head*, which is the half that was wrong. `truncate` always
          // cuts the right-hand end, and for an absolute path the right-hand end is the only
          // part that distinguishes one checkout from another: two lineages under
          // `…/cases/boundary-review/repository` and `…/cases/layering-review/repository`
          // rendered as the same string on a phone, both ending at "…/examples/ca". Setting
          // the box `rtl` moves the ellipsis to the start; the `<bdi>` inside keeps the
          // string itself reading left to right, and `text-align: left` keeps the row's
          // alignment. The accessible name and the `title` carry the whole path either way.
          "[direction:rtl] [text-align:left]",
          "block min-w-0 max-w-full truncate font-mono text-[11px] font-medium text-ink",
          "underline decoration-rule-strong underline-offset-2 transition hover:decoration-ink",
          // 11px type on a 16px line is a 16px-tall thing to hit with a thumb, and this is a
          // real control — it copies. The padding makes the touch box 44px; the matching
          // negative margin takes those 28px straight back out of the layout, so nothing on
          // the page moves. Every row this sits in aligns on the baseline, which padding
          // does not shift, so the visual result is identical to the 16px version.
          "-my-3.5 py-3.5",
        )}
      >
        <bdi>
          {path}
          {span ? <span className="text-ink-3">{span}</span> : null}
        </bdi>
      </button>
      {/* The tick is the whole confirmation, and it occupies no space until it is earned —
          a control that reserves room for a state it is usually not in makes every path on
          the page 14px narrower for the one moment it is. */}
      {copied ? <CheckIcon aria-hidden="true" className="shrink-0 text-[13px] text-ink" /> : null}
      {/* The same trick the copy button above carries, and for the same reason: this is a real
          control — it is the one that does the thing a reviewer actually wants — and at
          `p-0.5` around a 13px glyph it was a 17px target sitting beside a sibling
          deliberately grown to 44. The padding makes the box 44 tall; the negative margin
          takes it straight back out of the layout, so nothing moves. The width comes on a
          coarse pointer only, where a finger needs it. */}
      {href ? (
        <a
          href={href}
          title={`Open ${path} in your editor`}
          className="-my-3.5 shrink-0 rounded-xs px-1.5 py-3.5 pointer-coarse:px-3 text-[13px] text-ink-3 transition hover:text-ink"
        >
          <OpenExternalIcon aria-hidden="true" />
          <span className="sr-only">Open in your editor</span>
        </a>
      ) : null}
    </span>
  );
}

/** A definition list row: a small dim key, a readable value. */
export function MetaRow({
  label,
  children,
  className,
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid grid-cols-[minmax(88px,auto)_minmax(0,1fr)] gap-3 py-2", className)}>
      {/* `Label`, not a fourth copy of its four properties. This one had drifted to
          `tracking-[0.08em]`, and `as` is on that component precisely so a `dt` can have it. */}
      <Label as="dt">{label}</Label>
      <dd className="min-w-0 text-sm leading-6 text-ink-2">{children}</dd>
    </div>
  );
}

export function MetaList({ children, className }: { children: ReactNode; className?: string }) {
  return <dl className={cn("divide-y divide-rule", className)}>{children}</dl>;
}

/** A number that matters, with its name underneath. Used in strips of two to four. */
/**
 * A tone as a text colour, and the only place outside the tone table that names the hues.
 *
 * Anything showing a number or a word in a verdict's colour paints it through here, so the
 * hue always arrives from `lib/format` rather than being picked at the call site — which is
 * how a "cleared" green ended up on a finished clone and a "held" amber on a pinned setting.
 */
export const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-ink-2",
  marked: "text-ink",
  material: "text-material",
  held: "text-held",
  cleared: "text-cleared",
};

/**
 * A tone as a left edge, for a row in a list of rows.
 *
 * The same hues as `TONE_TEXT` and for the same reason — the colour arrives from
 * `lib/format`, never from the call site. What differs is the job: an edge is read at a
 * glance down a column, before any word on any row has been read, so it is the one place a
 * verdict is allowed to be a bar of colour rather than a mark and a word.
 *
 * That does not make it colour carrying meaning alone. Every row this paints also states its
 * verdict as a sign and as a word; the edge is the third statement, and the only one that
 * survives peripheral vision.
 */
export const TONE_EDGE: Record<Tone, string> = {
  neutral: "border-l-rule-strong",
  marked: "border-l-ink",
  material: "border-l-material",
  held: "border-l-held",
  cleared: "border-l-cleared",
};

export function Statistic({
  label,
  value,
  detail,
  tone = "ink",
  className,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: Tone | "ink";
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <div
        className={cn(
          "font-display text-2xl font-semibold tabular-nums tracking-tight",
          tone === "ink" ? "text-ink" : TONE_TEXT[tone],
        )}
      >
        {value}
      </div>
      {/* And a fifth, at `tracking-[0.1em]`. The name under a number is a block label. */}
      <Label className="mt-1">{label}</Label>
      {detail ? <div className="mt-1 truncate text-xs text-ink-3">{detail}</div> : null}
    </div>
  );
}

/** Dot-separated inline metadata. Wraps rather than truncating on small screens. */
export function MetaLine({ items, className }: { items: ReactNode[]; className?: string }) {
  const visible = items.filter(Boolean);
  return (
    <div className={cn("flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-3", className)}>
      {visible.map((item, index) => (
        <span key={index} className="inline-flex items-center gap-2">
          {/* `text-ink-3`, not `text-ink-3/50`. Halving the tier composited to `#afafaf` in
              light — 2.00:1 against a panel, below every step of the declared ink ramp, and
              invisible to `tokens.test.ts`, which measures the three named inks and cannot
              see an alpha applied in a class. `--ink-3` sits at `#5f5f5f` *because* the tier
              was measured and moved; halving it at a call site put the separator back below
              where the tier was before the correction. A middot at 12px is already the
              quietest mark on the line without help. */}
          {index > 0 ? (
            <span aria-hidden="true" className="text-ink-3">
              ·
            </span>
          ) : null}
          {item}
        </span>
      ))}
    </div>
  );
}
