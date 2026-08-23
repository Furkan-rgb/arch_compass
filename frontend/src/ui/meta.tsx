import type { HTMLAttributes, ReactNode } from "react";

import { useCopy } from "../lib/clipboard";
import { cn } from "../lib/cn";
import { editorHref, useEditorScheme } from "../lib/editor";
import type { Tone } from "../lib/format";
import { CheckIcon, OpenExternalIcon } from "./icons";

/**
 * Identifiers, paths, commits, fingerprints, model identities. Monospace, always.
 *
 * `wrap-anywhere` because every one of those is a single word to the line breaker and most
 * of them are wider than a phone — `openai/gpt-4o-2024-08-06@sha256:9f2c…` in a `MetaRow`
 * on a 390px screen has nowhere to break, so it painted past its cell and took the page
 * sideways with it. Where an ancestor asks for `truncate` instead, that wins: `truncate`
 * sets `white-space: nowrap`, which inherits, and nothing can wrap under it.
 */
export function Mono({
  children,
  className,
  ...props
}: { children: ReactNode; className?: string } & HTMLAttributes<HTMLSpanElement>) {
  return (
    <span {...props} className={cn("font-mono text-[12px] text-ink-2 wrap-anywhere", className)}>
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
          "block min-w-0 max-w-full truncate text-left font-mono text-[11px] font-medium text-ink",
          "underline decoration-rule-strong underline-offset-2 transition hover:decoration-ink",
          // 11px type on a 16px line is a 16px-tall thing to hit with a thumb, and this is a
          // real control — it copies. The padding makes the touch box 44px; the matching
          // negative margin takes those 28px straight back out of the layout, so nothing on
          // the page moves. Every row this sits in aligns on the baseline, which padding
          // does not shift, so the visual result is identical to the 16px version.
          "-my-3.5 py-3.5",
        )}
      >
        {path}
        {span ? <span className="text-ink-3">{span}</span> : null}
      </button>
      {/* The tick is the whole confirmation, and it occupies no space until it is earned —
          a control that reserves room for a state it is usually not in makes every path on
          the page 14px narrower for the one moment it is. */}
      {copied ? <CheckIcon aria-hidden="true" className="shrink-0 text-[13px] text-ink" /> : null}
      {href ? (
        <a
          href={href}
          title={`Open ${path} in your editor`}
          className="shrink-0 rounded-xs p-0.5 text-[13px] text-ink-3 transition hover:text-ink"
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
      <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">{label}</dt>
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
      <div className="mt-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-3">
        {label}
      </div>
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
          {index > 0 ? (
            <span aria-hidden="true" className="text-ink-3/50">
              ·
            </span>
          ) : null}
          {item}
        </span>
      ))}
    </div>
  );
}
