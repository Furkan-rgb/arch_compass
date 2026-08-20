import type { ReactNode } from "react";

import { cn } from "../lib/cn";
import type { Tone } from "../lib/format";

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
  title,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span title={title} className={cn("font-mono text-[12px] text-ink-2 wrap-anywhere", className)}>
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
 * Dropping the box also puts the path back on the text baseline of whatever it sits beside,
 * which is where a reader looks for it.
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
  return (
    <span
      title={`${path}${span}`}
      className={cn(
        // `truncate` and `max-w-full`: an absolute path is one word and is wider than a
        // phone, and a reference that widens its own column is worse than an elided one.
        "block max-w-full truncate font-mono text-[11px] font-medium text-ink",
        "underline decoration-rule-strong underline-offset-2",
        className,
      )}
    >
      {path}
      {span ? <span className="text-ink-3">{span}</span> : null}
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
