import { twMerge } from "tailwind-merge";

/**
 * Join class names, and let the last one win where two of them mean the same thing.
 *
 * The whole of our styling glue, and it used to be `filter(Boolean).join(" ")`. That is
 * fine right up until a caller overrides something a component already sets, which is the
 * entire point of every `className` prop here. `<ButtonLink className="hidden sm:block">`
 * put `hidden` and the button's own `inline-flex` on one element, both won their own
 * declaration, and the cascade — not the caller — decided which applied. The button stayed
 * visible on a phone for a while on the strength of that, and nothing about the markup
 * looked wrong.
 *
 * `twMerge` knows which Tailwind utilities are in the same group and drops the earlier of
 * any two. Later wins, which is the order every call site already reads as: the base classes
 * first, the caller's `className` last.
 *
 * It only resolves utilities it recognises. Arbitrary properties and our own project classes
 * pass through untouched and can still collide with each other — this narrows the problem
 * to the cases twMerge cannot see, rather than removing it.
 */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return twMerge(classes.filter(Boolean).join(" "));
}
