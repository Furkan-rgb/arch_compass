import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { useId } from "react";

import { cn } from "../lib/cn";
import { SearchIcon } from "./icons";

/**
 * `rounded-sm` is the control step, and an input almost always sits beside a `Button`.
 *
 * Three things in here were drawn rather than reasoned, and all three were measured.
 *
 * **The edge.** Every input, textarea, select and search box in the product is identified as
 * a control by one hairline. It was `border-rule-strong`, which is 1.41:1 on `bg-control` in
 * light and 1.38:1 in dark — and in light `--control` and `--surface` are both `#ffffff`, so
 * a field dropped in a panel has no fill difference underneath either and the hairline is the
 * whole affordance. `--rule-control` is the value that clears the 3:1 a boundary a reader has
 * to find is held to. `--rule` and `--rule-strong` are untouched: they separate structure,
 * which is a different job and reads correctly at a whisper.
 *
 * **The focus ring.** `outline-none` used to sit here, killing the one focus indicator the
 * product declares — `outline: 2px solid var(--ink)` in `@layer base` — and replacing it with
 * `focus:ring-2 focus:ring-ink/15`, a 1.39:1 wash that leaves a 1px border swap as the whole
 * visible signal. That was three focus treatments in one interface, two of them under the
 * 3:1 WCAG asks of an indicator, and `ring-2` compiles to a box-shadow, which is the thing
 * the rim rule exists to keep out. The base rule paints a field now, exactly as it paints
 * every button. `focus:border-ink` stays: a field's own edge darkening is useful on top of
 * the ring, and it is not standing in for one.
 *
 * **The invalid state.** A rejected control carries the mark, rather than a red sentence
 * underneath it carrying the whole meaning on hue alone. `ui/field.tsx` is on the
 * `verdict-hues.test.ts` allowlist for exactly this — a rejected field is the red end of the
 * scale — so it is the same `var(--accent)` the error text already uses and not a second red.
 * Written as an arbitrary variant because Tailwind's built-in `aria-*` set stops at
 * `required` and `selected`; `aria-[invalid=true]` is the same selector, spelled out.
 */
export const controlClass =
  "w-full rounded-sm border border-rule-control bg-control px-3 py-2 text-sm text-ink transition placeholder:text-ink-3 focus:border-ink aria-[invalid=true]:border-material disabled:cursor-not-allowed disabled:opacity-55";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(controlClass, className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea className={cn(controlClass, "min-h-24 resize-y leading-6", className)} {...props} />
  );
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(controlClass, "pr-8", className)} {...props} />;
}

/**
 * A labelled control. The label is always rendered and always associated — the id is
 * generated when the caller does not supply one, so no field can be shipped unlabelled.
 *
 * The render prop hands the child `aria-invalid` as well as `id` and `aria-describedby`,
 * because `aria-invalid` appeared nowhere in the whole frontend: no control in the product
 * was ever programmatically marked invalid, so a field could announce its error as a
 * *description* while reporting itself valid. The error paragraph is a live region for the
 * other half of it — validation that fails after a submit left the screen reader told nothing
 * and the sighted keyboard user, whose focus is still in the field, looking at a red line
 * below the fold of their attention.
 */
export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  hint?: ReactNode;
  error?: ReactNode;
  children: (props: {
    id: string;
    "aria-describedby": string | undefined;
    "aria-invalid": true | undefined;
  }) => ReactNode;
  className?: string;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("min-w-0", className)}>
      <label htmlFor={id} className="block text-xs font-semibold text-ink">
        {label}
      </label>
      {hint ? (
        <p id={hintId} className="mt-1 text-xs leading-5 text-ink-3">
          {hint}
        </p>
      ) : null}
      <div className="mt-1.5">
        {children({
          id,
          "aria-describedby": describedBy,
          "aria-invalid": error ? true : undefined,
        })}
      </div>
      {error ? (
        <p role="alert" id={errorId} className="mt-1.5 text-xs text-material">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function SearchInput({
  value,
  onValueChange,
  label,
  placeholder,
  className,
}: {
  value: string;
  onValueChange: (value: string) => void;
  label: string;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={cn("relative min-w-0", className)}>
      {/* A drawn mark, not a typed `/`. The slash was two faults in one span: an ASCII
          character standing in for an icon, which is the half of "a mark is drawn, never
          typed" that no pattern can catch and review has to; and a promise, because a leading
          `/` in a search field is the developer-tool convention for "press slash to focus
          this" and nothing in the frontend binds that key. On the repositories page it had a
          second wrong reading — that field searches paths, and the next line on the page is
          an absolute one. `SearchIcon` was already two components away in the palette. */}
      <SearchIcon
        aria-hidden="true"
        className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-ink-3"
      />
      <input
        type="search"
        aria-label={label}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onValueChange(event.target.value)}
        className={cn(controlClass, "pl-8")}
      />
    </div>
  );
}

/**
 * A checkbox and the sentence explaining it, which is one control and two pieces of text
 * rather than one very long accessible name.
 *
 * The description used to sit inside the `<label>`, so it became part of the checkbox's own
 * name and a screen reader announced the whole paragraph where the control's name belongs. It
 * is a sibling now, pointed at by `aria-describedby` — the pattern `Field` above already uses.
 *
 * `rounded-sm` because this is a control you operate, not a block inside a panel: the radius
 * ladder says 6 for the first and 10 for the second, and a clickable `<label>` with
 * `cursor-pointer` painted at 10 is content behaving as a control. The hover moves the edge
 * rather than the fill for the same reason `ToggleButton` does — `--rule` to `--rule-strong`
 * against an unchanged fill is a 1.25:1 to 1.41:1 move, which is to say pointing at it
 * produced nothing perceptible. The ground stays `--surface-2`: this is a strip set into a
 * panel, and `bg-control` would put the field-edge problem back one component over.
 */
export function Checkbox({
  checked,
  onChange,
  title,
  description,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  title: string;
  description?: string;
}) {
  const id = useId();
  const descriptionId = description ? `${id}-description` : undefined;
  return (
    <div className="rounded-sm border border-rule bg-surface-2 p-3 text-sm transition hover:border-ink-3">
      <label htmlFor={id} className="flex cursor-pointer items-start gap-3">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          aria-describedby={descriptionId}
          onChange={(event) => onChange(event.target.checked)}
          className="mt-0.5 size-4 accent-[var(--ink)]"
        />
        <span className="min-w-0 font-semibold text-ink">{title}</span>
      </label>
      {description ? (
        <p id={descriptionId} className="mt-0.5 pl-7 text-xs leading-5 text-ink-3">
          {description}
        </p>
      ) : null}
    </div>
  );
}
