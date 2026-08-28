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
 * 12.5px at weight 500, which is the row the type scale gives this component's own job —
 * *evidence: provenance, identities, paths, namespaces, fingerprints*. It sat at 11px, the
 * smallest size in the product, which is where the product's longest strings were: a
 * 64-character fingerprint and an absolute path, set in the face whose stems are thinnest at
 * that size. Contrast is computed on a colour pair and says nothing about stroke, so a mono
 * at 11px on a 6:1 ground is not the reading a sans at 11px on the same ground is — which is
 * why this row moves and the sans rows around it do not. The weight is the other half of the
 * same repair rather than emphasis.
 *
 * A call site that genuinely wants a smaller string still says so — but a size written on a
 * `Mono` is now an override rather than a restatement of this default, which is worth knowing
 * before reading one as deliberate.
 */
export function Mono({
  children,
  className,
  ...props
}: { children: ReactNode; className?: string } & HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      {...props}
      className={cn("font-mono text-[12.5px] font-medium text-ink-2 wrap-anywhere", className)}
    >
      {children}
    </span>
  );
}

/**
 * A source path with an optional line span: the way back to the file a claim was measured
 * from, and the one place in this file that has to say "this goes somewhere".
 *
 * It says it in `--mark`, and this is the component that hue was added for. A route back to a
 * file is not a grade: under the one-hue system a path wore the accent red, which said *act
 * on this* about a citation, and the fold that holds nothing but provenance was where a
 * reader could no longer tell which of the three voices they were in. The fourth signal means
 * *where this came from* and nothing else, so it can be spent here without competing with a
 * verdict.
 *
 * The two tiers split on what the paint is doing. The word takes `--mark`, the text tier,
 * which clears 4.5:1 on every ground; the underline takes `--mark-edge`, which is a graphic
 * and has only 3:1 to clear — 3.41:1 on `--sunken` in light, the tightest ground it lands on.
 * Swapping them would be a contrast bug in one direction and a wasted signal in the other.
 * Hovering moves the rule to the text tier, which is darker in light and brighter in dark:
 * "more", in whichever direction the theme means it.
 *
 * The affordance is still an underline and a weight rather than a chip. A box is what this
 * system puts around a *block*, not around a reference, and beside `Mono` — the same face at
 * the same size — a chip added a hairline and nothing else.
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
          "block min-w-0 max-w-full truncate font-mono text-[12.5px] font-medium text-mark",
          "underline decoration-mark-edge underline-offset-2 transition hover:decoration-mark",
          // A line of this type is under 20px tall, which is a small thing to hit with a
          // thumb, and this is a real control — it copies. The padding takes the touch box
          // past 44px; the matching negative margin takes those 28px straight back out of
          // the layout, so nothing on the page moves. Every row this sits in aligns on the
          // baseline, which padding does not shift, so the visual result is unchanged.
          "-my-3.5 py-3.5",
        )}
      >
        <bdi>
          {path}
          {/* The line span stays neutral while the path carries the hue. It is a quantity
              rather than the route — the part of the string that says *which file* is the
              part worth spending a signal on — and a row's colour budget is one thing. */}
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

/**
 * A definition list row: a dim key, and the value it is there to carry.
 *
 * The value is the darkest thing in the row and the key is the quietest, and this pair is the
 * defect the ink ramp was rebuilt for. It used to be `ink-2` on the value against `ink-3` on
 * the key — two tiers that measure 1.54:1 against each other, so the Provenance fold read as
 * one grey separated by a change of case, and every ink in it passed its own contrast test
 * against the ground. A key and a value are now `ink-3` and `ink`: 3.01:1 apart in light and
 * 2.84:1 in dark, which is two colours rather than one colour with two names.
 *
 * The row carries its own space, top and bottom, because `MetaList` no longer draws a rule
 * between rows and something has to hold them apart.
 */
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
    <div
      className={cn("grid grid-cols-[minmax(88px,auto)_minmax(0,1fr)] gap-3 py-2.5", className)}
    >
      {/* `Label`, not a fourth copy of its four properties. This one had drifted to
          `tracking-[0.08em]`, and `as` is on that component precisely so a `dt` can have it. */}
      <Label as="dt">{label}</Label>
      <dd className="min-w-0 text-sm leading-6 text-ink">{children}</dd>
    </div>
  );
}

/**
 * The rows are held apart by space, and by nothing else.
 *
 * This was `divide-y divide-rule`, which put nine hairlines down the Provenance fold at
 * 1.28:1 — under the 1.6:1 a boundary carrying structure has to clear, and so not a division
 * a reader sees. What it added was a grey band between every pair of rows in a block already
 * made of grey. Space separates for free, at any contrast, in both themes, and the only thing
 * it costs is height: each row pays 10px above and below, so rows sit 20px apart against the
 * 12px between a key and its own value, and the pairing reads before the list does.
 */
export function MetaList({ children, className }: { children: ReactNode; className?: string }) {
  return <dl className={cn("grid", className)}>{children}</dl>;
}

/** A number that matters, with its name underneath. Used in strips of two to four. */
/**
 * A tone as a text colour, and the only place outside the tone table that names the hues.
 *
 * Anything showing a number or a word in a verdict's colour paints it through here, so the
 * hue always arrives from `lib/format` rather than being picked at the call site — which is
 * how a "cleared" green ended up on a finished clone and a "held" amber on a pinned setting.
 *
 * These are the bare tokens, which is the text tier: every one clears 4.5:1 on all four
 * grounds in both themes, because everything this table paints is a word or a number somebody
 * reads. `TONE_EDGE` below is the same three hues in the graphic tier, and the two do not
 * swap — an `-edge` token on a word is a contrast failure, and a word's token on a 3px bar
 * paints it in the value that had to darken to stay readable.
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
 * `lib/format`, never from the call site. What differs is the job, and with it the tier: an
 * edge is read at a glance down a column, before any word on any row has been read, so it is
 * the one place a verdict is allowed to be a bar of colour rather than a mark and a word, and
 * it is drawn in `-edge` rather than in the token the same verdict's *word* is set in. A bar
 * is a graphic, so it has 3:1 to clear rather than 4.5:1 — which is what lets these stay
 * saturated where the word of the same verdict has to darken to stay readable.
 *
 * That does not make it colour carrying meaning alone. Every row this paints also states its
 * verdict as a sign and as a word; the edge is the third statement, and the only one that
 * survives peripheral vision.
 */
export const TONE_EDGE: Record<Tone, string> = {
  // `neutral` and `marked` are not verdicts and have no signal to spend: a row that is
  // nothing in particular gets the boundary token, and one being pointed at gets ink.
  neutral: "border-l-rule-strong",
  marked: "border-l-ink",
  material: "border-l-material-edge",
  held: "border-l-held-edge",
  cleared: "border-l-cleared-edge",
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
          {/* `text-ink-3`, not `text-ink-3/50`. Halving the tier composites to `#b2b1ae` in
              light — 2.14:1 against a panel, below every step of the declared ink ramp, and
              invisible to `tokens.test.ts`, which measures the three named inks and cannot
              see an alpha applied in a class. It is the general rule now as well: a tone
              mixed from an alpha of a ramp token composites to a real step in one theme and
              to nothing in the other. `--ink-3` sits where it does *because* the tier was
              measured and placed; halving it at a call site puts the separator back below
              where the ramp starts. A middot at 12px is already the quietest mark on the
              line without help. */}
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
