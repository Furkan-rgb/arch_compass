import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";

import { useCopy } from "../lib/clipboard";
import { cn } from "../lib/cn";
import { CheckIcon, CopyIcon } from "./icons";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "quiet" | "danger" | "link";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANTS: Record<ButtonVariant, string> = {
  // The one action a screen is asking for, in the one hue the product has. `danger` below is
  // the same red at a wash rather than a fill — a destructive action is consequential, not
  // primary, and fill against wash is what keeps the two apart now that both are red.
  primary:
    "border-accent-fill bg-accent-fill text-accent-on-fill hover:border-accent-strong hover:bg-accent-strong active:translate-y-px",
  // `bg-control` rather than `bg-surface`: a secondary button lands on the void, on a panel
  // and inside a sunken block, and on this ground it has to read as raised above all three.
  // One flat grey can only be brighter than one of them, so in dark the token is a film that
  // steps up from whatever is behind it, and the rim is the light along its top edge.
  //
  // Two things changed on the most-used button in the product. `border-rule-control` is the
  // edge: in light `--control` and `--surface` are both `#ffffff`, so a secondary button on a
  // panel is a white box whose only boundary was a 1.41:1 hairline — under the 3:1 a boundary
  // a reader has to find is held to, and here the boundary is the whole affordance. And the
  // hover used to declare two things one of which was dead: `hover:border-rule-strong` set
  // the colour the base class had already set, leaving a 1.19:1 fill shift as the entire
  // response to a pointer. The edge is what moves now, which is the device this system
  // already uses for a state — an edge appearing rather than a fill inverting.
  secondary:
    "border-rule-control bg-control text-ink shadow-rim hover:border-ink-3 hover:bg-control-2 active:translate-y-px",
  ghost: "border-transparent text-ink-2 hover:bg-sunken hover:text-ink active:translate-y-px",
  quiet:
    "border-rule bg-sunken text-ink-2 hover:border-rule-strong hover:text-ink active:translate-y-px",
  // The one variant with no answer to a press at all, which is the variant that deletes
  // things — where a person most needs to know the press registered before the request comes
  // back. It now moves the fill as well as the border, and pushes down like the other four.
  danger:
    "border-material/30 bg-material-soft text-material hover:border-material/55 hover:bg-material/15 active:translate-y-px",
  // A control that goes somewhere instead of recording something.
  //
  // The three voices give a bordered control at control size to **Decided** — "the record of
  // what a person chose" — and an open finding had five of them, two of which choose nothing.
  // "Answer it" is `onOpen("clarification")` in `docket.tsx` and "Judgement context" opens a
  // drawer; both leave the row and write no `StandingDecision`. A reader could not tell a way
  // out from a disposition by looking, and `docs/design-system.md` says the honest response to
  // an element that does not sit in one of the three voices is to stop on it, not to hand it
  // the nearest recipe.
  //
  // So the difference is drawn as shape. This is `PolicyRef`'s gesture in sans at control
  // size: no fill, no rim, no border to pick the box up by, full ink, and an underline resting
  // at `--rule-strong` that goes to the ink on hover. The same device `ui/markdown.tsx` gives
  // an anchor, which is the second place it was typed; this is the registry, so it is not
  // typed a third.
  //
  // It takes no chroma and specifically no `--mark`. The mark is the accent under another name
  // and it is spent on reaching *the source a claim came from* — a file, a policy, a cited
  // finding. The clarification round and the context drawer are places in the product, not
  // sources, and `design-system.test.ts` is explicit that the moment the mark paints a button
  // it is an accent again.
  //
  // `px-0` is why this record is applied after `SIZES` in `buttonClass`: the words are the
  // target, and a link carrying a size's side padding reads as a box whose edges were rubbed
  // out. The `border` and the `min-h-*` from the base and the size stay, so the 44px touch box
  // and the focus ring are the same geometry every other control has.
  //
  // The `disabled:` recipe above still draws a control film and an edge, which would turn an
  // off link into a small grey box. Neither call site disables one; if a third ever does, that
  // recipe is what wants the variant-aware branch, not this line.
  link: "border-transparent px-0 text-ink underline decoration-rule-strong underline-offset-4 hover:decoration-current active:translate-y-px",
};

// 44px is the charter's fifth principle, and `md` is what a button is unless somebody says
// otherwise — so `md` is the size that has to clear it. It was 40, which is why three call
// sites had already written `min-h-11` back on by hand. `sm` stays at 32 because it is the
// dense inline size; where a `sm` control is genuinely tapped, the call site grows its box
// and hands the extra height back with a negative margin.
/**
 * `sm` grows to the 44px floor on a coarse pointer and stays 32px on a fine one.
 *
 * The floor is a *touch* requirement, so answering it by width would be answering a
 * different question — and would cost a mouse user the density this size exists for. A
 * pseudo-element cannot answer it either: `getBoundingClientRect` ignores an absolutely
 * positioned `::after`, so a 32px button with an extended `::after` still measures 32,
 * and a finger is no more fooled than the test is. The box has to be the target.
 */
const SIZES: Record<ButtonSize, string> = {
  sm: "min-h-8 pointer-coarse:min-h-11 gap-1.5 px-2.5 text-xs",
  md: "min-h-11 gap-2 px-3.5 text-sm",
  lg: "min-h-12 gap-2.5 px-5 text-[15px]",
};

export function buttonClass(variant: ButtonVariant = "primary", size: ButtonSize = "md") {
  return cn(
    // `rounded-sm` is the control step. A button used to be `md` because `md` was 2px like
    // everything else; now the ladder has five real values, `md` is a block inside a panel,
    // and a button that took it would be rounder than the panel it sits in relative to its
    // own height.
    "inline-flex select-none items-center justify-center rounded-sm border font-semibold transition duration-150",
    // Off is drawn with tokens, not with an opacity, and this is the whole reason why.
    //
    // `opacity-45` composites an element toward whatever is behind it, foreground and
    // background together — so on the primary it took white on `#971b1a` down to a `#d09898`
    // fill with a white label, **2.43:1**, and in doing so manufactured a fifth pink out of
    // the one hue the system has. On `/start` and on Ask that pink was the only chromatic
    // object on the screen, which put the eye on the one control that cannot be pressed; in
    // dark it read as an armed destructive button rather than as a disabled one. The other
    // four variants fared no better, landing between 2.04:1 and 2.41:1.
    //
    // The replacement is the `secondary` recipe with the meta ink: a control's edge, a
    // control's fill, and a label at `--ink-3`, which `tokens.test.ts` measures at 5:1 or
    // better against every ground in both themes — precisely the guarantee an alpha throws
    // away. No rim, because an off control is not raised. The variant selectors are attribute
    // and pseudo-class selectors, so each of these outranks the variant's own single class
    // whatever order `cn` leaves them in.
    //
    // `aria-disabled` gets the same drawing and the same inert pointer as `disabled`. What it
    // keeps is the tab stop — see `Button` below for when that is the right trade.
    "disabled:pointer-events-none disabled:border-rule-control disabled:bg-control disabled:text-ink-3 disabled:shadow-none",
    "aria-disabled:pointer-events-none aria-disabled:border-rule-control aria-disabled:bg-control aria-disabled:text-ink-3 aria-disabled:shadow-none",
    // The size before the variant, so a variant can refuse a size's padding. `cn` is
    // tailwind-merge and resolves last-wins per group, and `link` is the only variant that
    // names a spacing class at all — the other five say colour, shadow and a press. None of
    // those shares a group with `px-*`, `gap-*`, `min-h-*` or a font size, so this order moves
    // nothing that was already on screen: `text-accent-on-fill` is the text-colour group and
    // `text-sm` is the font-size group, and both survive in either order. `button.test.ts`
    // holds that rather than leaving it to a reading: it takes the fifteen pairs of an older
    // variant and a size and checks each one still carries every class its size declares.
    SIZES[size],
    VARIANTS[variant],
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /**
   * Off, but still reachable — for the one action a screen exists to perform.
   *
   * A real `disabled` attribute takes the control out of the tab order, which is right for a
   * button among several and wrong for the *only* thing a page is asking somebody to do. On
   * `/start`, "Run review" is disabled until a repository is chosen and the reason for it sits
   * in a sibling span; a keyboard or screen-reader user tabbed from the scope list straight
   * past the page's whole purpose and was never told it existed, let alone why it was off.
   *
   * So this is `aria-disabled`: announced as unavailable, focusable, and inert — the click is
   * dropped here rather than left to a handler that has to remember. Pair it with
   * `aria-describedby` pointing at the sentence that says why, or it announces a wall with no
   * door. Everything else keeps the real attribute, which is still the better default.
   */
  inactive?: boolean;
};

export function Button({
  className,
  variant = "primary",
  size = "md",
  type = "button",
  inactive,
  onClick,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      aria-disabled={inactive || undefined}
      onClick={inactive ? undefined : onClick}
      className={cn(buttonClass(variant, size), className)}
      {...props}
    />
  );
}

export function ButtonLink({
  className,
  variant = "primary",
  size = "md",
  ...props
}: LinkProps & { variant?: ButtonVariant; size?: ButtonSize }) {
  return <Link className={cn(buttonClass(variant, size), className)} {...props} />;
}

export function ExternalButtonLink({
  className,
  variant = "secondary",
  size = "md",
  children,
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
}) {
  return (
    <a className={cn(buttonClass(variant, size), className)} {...props}>
      {children}
    </a>
  );
}

/**
 * Put something on the clipboard, and say for a moment and a half that it worked.
 *
 * Ghost and icon-only, because it sits beside the thing it copies rather than being an
 * action a screen is asking for — an excerpt, a path, a run id. The word is `sr-only`: what
 * it copies is named there (*Copy the path*), so the button is askable for by name and a
 * listener is told which of several on a page they have landed on.
 *
 * The mark changing to a tick is the whole confirmation, and it is deliberately not a toast:
 * the reader is looking directly at the control they just pressed, and a message in the
 * corner of the screen for something that took no time would be reporting the obvious. A
 * copy that *fails* says nothing here either — `useCopy` returns false and the tick never
 * appears, which is the honest signal, and a caller that needs to say more can pass
 * `onCopied`.
 */
export function CopyButton({
  value,
  label,
  className,
  onCopied,
}: {
  value: string;
  /** What is being copied, for the accessible name: "Copy the path". */
  label: string;
  className?: string;
  onCopied?: (ok: boolean) => void;
}) {
  const { copied, copy } = useCopy();
  const Glyph = copied ? CheckIcon : CopyIcon;
  return (
    <button
      type="button"
      onClick={() => void copy(value).then((ok) => onCopied?.(ok))}
      className={cn(
        buttonClass("ghost", "sm"),
        "min-w-8 px-0 pointer-coarse:min-w-11",
        // The confirmation is a state of the control, so it takes full ink rather than the
        // ghost's secondary — the difference is what makes the swap visible at this size.
        copied && "text-ink",
        className,
      )}
    >
      <Glyph className="size-3.5" aria-hidden="true" />
      <span className="sr-only">{copied ? `${label} — copied` : label}</span>
    </button>
  );
}

/**
 * A pressed/unpressed control for filters — a button, not a checkbox pretending to be one.
 *
 * What is on is *raised*, not inverted. `bg-ink text-canvas` is the loudest fill the system
 * can draw, and a row of them — a set of filters at rest is usually a row of them — reads as
 * a row of alarms rather than as a setting nobody has touched. So a pressed toggle wears the
 * `secondary` button's recipe: the control film, a rim along its top edge, full-strength ink.
 * White in light, a step up from the ground in dark: one gesture, not one colour.
 *
 * This is the same treatment `components/ui/toggle.tsx` gives a Radix switch, deliberately.
 * Two toggles that look different are two toggles a reader has to learn separately.
 */
export function ToggleButton({
  pressed,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { pressed: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      className={cn(
        // 44px is a *touch* requirement, so it is answered on a coarse pointer and nowhere
        // else — the same split `Button`'s `sm` size makes. A segmented control of three
        // chips is one line of text and two words of count; holding it at 44px with a mouse
        // spent a third of the queue's header on a strip that says which filter is on.
        "inline-flex min-h-8 pointer-coarse:min-h-11 items-center gap-1.5 whitespace-nowrap rounded-sm border px-2.5 text-xs font-semibold transition duration-150",
        // A toggle for an empty set stays readable — it is telling you the count is zero,
        // which is information — but stops offering to filter to nothing.
        //
        // The class beside that sentence used to be `opacity-40`, which measured 1.76–1.92:1
        // on every ground in both themes: the count a reader was meant to be told was the
        // least readable text on the strip, and the comment said the opposite. So the state
        // is drawn instead of dimmed — the unpressed look, which already reads as "not on",
        // and no pointer, which is what says "not offering". The zero does the rest; it is
        // the reason the chip is off, and it is set in the tier `tokens.test.ts` measures.
        "disabled:pointer-events-none disabled:border-transparent disabled:text-ink-3",
        // `hover:border-ink-3` on the pressed branch, because the pressed branch had no hover
        // of any kind — and a filter strip's resting state is usually several chips on at
        // once, so most of the strip was inert to a pointer most of the time, with nothing
        // saying it could be turned back off. The fill cannot carry it: `--control` is the
        // panel colour in light. The edge can, on both grounds.
        pressed
          ? "border-rule-control bg-control text-ink shadow-rim hover:border-ink-3"
          : "border-transparent text-ink-3 hover:bg-sunken hover:text-ink",
        className,
      )}
      {...props}
    />
  );
}
