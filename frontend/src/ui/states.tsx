import type { ElementType, ReactNode } from "react";

import { cn } from "../lib/cn";
import { Panel, PanelBody } from "./panel";

/** A skeleton block. Shape first, then content — the layout never jumps. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      // `xs`: a skeleton is mostly a 12px bar standing in for a line of text, and the
      // control step on something that short reads as a lozenge.
      className={cn("animate-shimmer rounded-xs bg-sunken", className)}
    />
  );
}

/**
 * The panel that stands where a panel is about to be, rendered *through* `Panel` rather than
 * beside it.
 *
 * It used to reproduce the raised recipe by hand — `rounded-lg border border-rule bg-surface`
 * — and drop `shadow-rim` on the way, so in dark its top edge was lost against the void while
 * the real panel replacing it half a second later had a rim saying where the surface starts.
 * A surface appeared to gain an edge on load, which is the opposite of what a placeholder is
 * for. Composing the component is what keeps the rim coming from the token.
 */
export function LoadingPanel({ label, rows = 3 }: { label: string; rows?: number }) {
  return (
    <Panel role="status" aria-live="polite">
      <PanelBody>
        <div className="flex items-center gap-2.5 text-sm font-medium text-ink-2">
          {/* The label is printed right beside it, so the spinner does not say it again. */}
          <Spinner label="" />
          {label}
        </div>
        <div className="mt-5 grid gap-2.5">
          {Array.from({ length: rows }, (_, index) => (
            <Skeleton key={index} className={cn("h-3", index === rows - 1 ? "w-1/2" : "w-full")} />
          ))}
        </div>
      </PanelBody>
    </Panel>
  );
}

/**
 * The one mark that says the workspace is doing something.
 *
 * Two things were wrong with it and both came from the same assumption — that it would
 * always sit beside a word. It does not: it is the entire progress signal on a pressed
 * button and inside a chip, so `aria-hidden` left those places announcing nothing at all.
 * And under `prefers-reduced-motion` every animation in the stylesheet collapses to
 * `0.001ms`, which froze the ring mid-rotation — a circle with one dark quarter, stopped,
 * reads as a rendering fault rather than as work in progress.
 *
 * So: a word for anyone listening, and a mark that is *deliberately* still for anyone who
 * asked for stillness. `.spinner` in `styles.css` is where the second half lives, because
 * a media query cannot be written as a utility on the element.
 *
 * `label` where the caller can say what is being waited on. The default is the honest
 * minimum, and a caller that already prints "Reading the repository…" beside it passes an
 * empty string rather than having the page say it twice.
 */
export function Spinner({ className, label = "Working" }: { className?: string; label?: string }) {
  return (
    // The word goes *inside* the ring rather than beside it. A sibling would be a second
    // child of whatever flex row the spinner was dropped into, and a `gap` counts an
    // invisible item the same as a visible one — so half the call sites would have gained a
    // few pixels of space from a change that is meant to be inaudible and invisible.
    <span
      aria-hidden={label ? undefined : true}
      className={cn(
        "spinner inline-block size-3.5 animate-spin rounded-full border-2 border-rule-strong border-t-ink",
        className,
      )}
    >
      {label ? <span className="sr-only">{label}</span> : null}
    </span>
  );
}

/**
 * A standing note about how something is set up, or about what the workspace is doing.
 *
 * Exists to keep the verdict palette out of it. `cleared`, `held` and `material` are the
 * three things a model can say about a candidate, and the workbench reads them as grades —
 * so a pinned setting rendered in `held` amber says "a judgement is pending on your
 * configuration", and a finished clone in `cleared` green says the clone was found sound.
 * Neither is a verdict, and both were saying so in the product's own colour language.
 *
 * Two tones, and neither is a hue at all: `notice` is a fact about the setup and recedes;
 * `working` is the workspace acting or asking, and is emphasised in ink. There is no accent
 * hue left to reach for, which is the point — see `docs/design-system.md`.
 */
export function Notice({
  tone = "notice",
  title,
  children,
  className,
}: {
  tone?: "notice" | "working";
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-md border px-3.5 py-3 text-sm leading-6",
        // Two grounds off the declared ramp, not one ground and an alpha of it. `bg-sunken/70`
        // composited to `#f1f1f1` in light and `#1a1a1a` in dark — two invented greys, each a
        // different distance from its panel, so the pair read one way in one theme and another
        // in the other. `--surface-2` is a strip that recedes into the panel and `--sunken` is
        // a block set apart from it, in both themes and in the same direction, which is
        // exactly the difference between a standing note and the workspace asking something.
        tone === "notice" && "border-rule bg-surface-2 text-ink-2",
        tone === "working" && "border-rule-strong bg-sunken text-ink-2",
        className,
      )}
    >
      {title ? (
        <strong
          className={cn(
            "block text-[11px] font-bold uppercase tracking-[0.08em]",
            tone === "working" ? "text-ink" : "text-ink-3",
          )}
        >
          {title}
        </strong>
      ) : null}
      <div className={title ? "mt-1.5" : undefined}>{children}</div>
    </div>
  );
}

/**
 * The length past which a thrown message stops being a sentence and starts being a stack.
 *
 * Three lines of 14px in this block is roughly this many characters. It is a threshold rather
 * than a measurement because nothing can measure the wrap at render time, and being wrong
 * either way costs a disclosure nobody opens or a disclosure nobody needed.
 */
const LONG_MESSAGE = 180;

/**
 * `action` is the way out, and it is optional because most of the fifteen call sites do not
 * have one yet.
 *
 * A failed request is the one state in this product that regularly resolves itself: the
 * workspace is a local process, and a laptop that slept or a server restarted by the run it
 * was executing both produce an error that a second attempt answers. Fifteen `ErrorNotice`s
 * across `src/features` say what went wrong and offer nothing, so the only recovery the
 * product documents is a page reload.
 *
 * Rendered below the message rather than beside it: the sentence is a variable-length thing
 * from the server and a control on the same line moves as the sentence does.
 */
export function ErrorNotice({
  error,
  title = "That did not go through",
  action,
}: {
  error: unknown;
  title?: string;
  action?: ReactNode;
}) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div
      role="alert"
      className="animate-rise rounded-md border border-material/30 bg-material-soft px-4 py-3 text-sm leading-6 text-material"
    >
      {/* Clamped, because this renders whatever was thrown and a fetch against a local
          workspace regularly throws several hundred characters carrying a URL and a stack
          fragment. Uncapped, the reddest and loudest region on the page became the longest
          one, and the `action` that gets the reader out of it — the one state in this product
          that regularly resolves itself — was pushed below the fold of the block.

          `line-clamp-3` is the only display utility on this element on purpose: a clamp sets
          `display: -webkit-box` itself, and a second display class beside it wins and cancels
          it silently. `wrap-anywhere` stays, because the message is regularly a URL or an
          absolute path with no break opportunity in it at all. */}
      <p className="line-clamp-3 wrap-anywhere">
        <strong className="mr-1.5 font-semibold">{title}:</strong>
        {message}
      </p>
      {message.length > LONG_MESSAGE ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-semibold">Show the full message</summary>
          <p className="mt-1.5 font-mono text-[11px] leading-5 wrap-anywhere">{message}</p>
        </details>
      ) : null}
      {action ? <div className="mt-2.5 flex flex-wrap items-center gap-2">{action}</div> : null}
    </div>
  );
}

/**
 * What a surface says when it has nothing to show, which is the whole of the page's content
 * at that moment — and therefore has to be a heading and has to have a ground.
 *
 * `as` defaults to `h2`, because each of these stands where a section's list would, under the
 * page's `h1`; a caller already inside an `h2` passes `as="h3"`. It was a `div`, so a reader
 * moving by heading landed on the page title and then on nothing at all. The escape hatch is
 * the one `Label` in `ui/panel.tsx` already establishes for this exact class of problem.
 *
 * `text-[15px]` matches `PanelHeader`, which is the same semantic level. It was `text-base` —
 * 16px, the one size the type scale reserves for the model's reasoning and nothing else.
 *
 * `bg-surface`, not `bg-surface/40`. Forty per cent of the surface composited to `#f9f9f9` in
 * light, a sixth grey one step off `--surface-2`, and to `#050505` in dark — *below every
 * named surface*, 1.03:1 from the canvas, so an empty state in dark was a dashed outline
 * around nothing. It is a panel with nothing in it yet, which is what `--surface` is for, and
 * it puts "nothing is darker than the page" back to being true.
 */
export function EmptyState({
  title,
  children,
  action,
  className,
  as: Heading = "h2",
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
  as?: ElementType;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-dashed border-rule-strong bg-surface px-6 py-12 text-center",
        className,
      )}
    >
      <Heading className="font-display text-[15px] font-semibold text-ink">{title}</Heading>
      {children ? (
        <div className="mx-auto mt-2 max-w-md text-sm leading-6 text-ink-3">{children}</div>
      ) : null}
      {action ? <div className="mt-5 flex justify-center gap-2">{action}</div> : null}
    </div>
  );
}

/** Announce a transient result to a screen reader without stealing focus. */
export function LiveRegion({ children }: { children: ReactNode }) {
  return (
    <p aria-live="polite" className="sr-only">
      {children}
    </p>
  );
}
