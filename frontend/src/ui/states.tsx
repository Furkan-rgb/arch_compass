import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/** A skeleton block. Shape first, then content — the layout never jumps. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-shimmer rounded-sm bg-sunken", className)}
    />
  );
}

export function LoadingPanel({ label, rows = 3 }: { label: string; rows?: number }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-rule bg-surface p-5 shadow-panel"
    >
      <div className="flex items-center gap-2.5 text-sm font-medium text-ink-2">
        <Spinner />
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

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-block size-3.5 animate-spin rounded-full border-2 border-accent/25 border-t-accent",
        className,
      )}
    />
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
 * Two tones, and neither is a hue the queue uses: `notice` is a fact about the setup and is
 * neutral; `working` is the workspace acting or asking, which is what the accent already
 * means everywhere else.
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
        tone === "working" && "border-accent/25 bg-accent-soft text-ink-2",
        className,
      )}
    >
      {title ? (
        <strong
          className={cn(
            "block text-[11px] font-bold uppercase tracking-[0.08em]",
            tone === "working" ? "text-accent" : "text-ink-3",
          )}
        >
          {title}
        </strong>
      ) : null}
      <div className={title ? "mt-1.5" : undefined}>{children}</div>
    </div>
  );
}

export function ErrorNotice({ error, title = "That did not go through" }: { error: unknown; title?: string }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div
      role="alert"
      className="animate-rise rounded-md border border-material/30 bg-material-soft px-4 py-3 text-sm leading-6 text-material"
    >
      <strong className="mr-1.5 font-semibold">{title}:</strong>
      {message}
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
