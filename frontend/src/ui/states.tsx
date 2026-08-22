import type { ReactNode } from "react";

import { cn } from "../lib/cn";

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

export function LoadingPanel({ label, rows = 3 }: { label: string; rows?: number }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-rule bg-surface p-5"
    >
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
    </div>
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
        tone === "notice" && "border-rule bg-sunken/70 text-ink-2",
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
      // `wrap-anywhere`: the message is whatever the server or the fetch threw, which is
      // regularly a URL or an absolute path with no break opportunity in it at all.
      className="animate-rise rounded-md border border-material/30 bg-material-soft px-4 py-3 text-sm leading-6 text-material wrap-anywhere"
    >
      <strong className="mr-1.5 font-semibold">{title}:</strong>
      {message}
      {action ? <div className="mt-2.5 flex flex-wrap items-center gap-2">{action}</div> : null}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
  className,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-dashed border-rule-strong bg-surface/40 px-6 py-12 text-center",
        className,
      )}
    >
      <div className="font-display text-base font-semibold text-ink">{title}</div>
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
