import type { ReactNode } from "react";

import { cn } from "../lib/cn";
import { Label } from "./panel";

/**
 * The heading block every app page opens with, and the two things it was spending badly.
 *
 * **The title was the loudest thing on the page and said nothing.** 28px of display type set
 * to the page's own name — "Reviews", "Repositories", "Architecture cases" — which is already
 * the active nav item, already the URL, and already what the reader just clicked. The
 * experience doc made this argument about the review page's `h1` and removed it there; the
 * same `h1` was still the opening move on six other pages. It is 17px now, and the
 * description under it takes full ink, because the description is the line that is actually
 * telling somebody something. Emphasis is taken *off* the thing that does not need it rather
 * than added to the thing that does, which is the general rule this system already states.
 *
 * **The eyebrow was a fifth copy of the `Label` recipe.** Four properties, retyped, at
 * `tracking-[0.16em]` — a value that appears nowhere in the type scale — on the very first
 * line of every app page, which is to say the element meant to look identical everywhere
 * differed where a reader meets it first. `Label` is the recipe, and it is exported from
 * `ui/panel.tsx` precisely so this stops happening.
 */
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
        {eyebrow ? <Label className="mb-1.5">{eyebrow}</Label> : null}
        <h1 className="max-w-3xl font-display text-[17px] font-semibold tracking-tight text-ink">
          {title}
        </h1>
        {description ? (
          <p className="mt-2 max-w-2xl text-sm leading-6 text-ink">{description}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </header>
  );
}

/**
 * A heading for a group of panels. It has no callers today, which is the only reason it is
 * still `text-[15px]` rather than deleted: `PanelHeader`'s `h2` is 15px and this is the same
 * semantic level, and a product with three sizes for one level is a product where the level
 * means nothing. It was `text-lg` — 18px, larger than the page title above it.
 */
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
        <h2 className="font-display text-[15px] font-semibold tracking-tight text-ink">{title}</h2>
        {description ? (
          <p className="mt-1 text-sm leading-6 text-ink-3">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}
