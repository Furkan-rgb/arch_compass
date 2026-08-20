import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/** The heading block every app page opens with. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: ReactNode;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "mb-6 flex flex-col justify-between gap-4 border-b border-rule pb-5 lg:flex-row lg:items-end",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow ? (
          <div className="mb-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-ink-3">
            {eyebrow}
          </div>
        ) : null}
        <h1 className="max-w-3xl font-display text-2xl font-semibold tracking-[-0.02em] text-ink sm:text-[28px]">
          {title}
        </h1>
        {description ? (
          <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-2">{description}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </header>
  );
}

export function SectionHeading({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-3", className)}>
      <div className="min-w-0">
        <h2 className="font-display text-lg font-semibold tracking-tight text-ink">{title}</h2>
        {description ? (
          <p className="mt-1 text-sm leading-6 text-ink-3">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}
