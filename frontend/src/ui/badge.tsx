import type { ReactNode } from "react";

import { cn } from "../lib/cn";
import {
  type Descriptor,
  type MarkShape,
  type Tone,
  dispositionOf,
  statusOf,
  strengthOf,
  verdictOf,
} from "../lib/format";
import { Mark } from "./mark";

/**
 * A tone as a pill: the word in the text tier, the fill in the wash, the border in the edge.
 * This is the one place in the product that holds all three tiers of a signal at once, which
 * is why the tier rule is argued here rather than pointed at.
 *
 * The tiers are split on what WCAG asks of each — 4.5:1 of a word, 3:1 of a meaningful
 * graphic — so they cannot be swapped without one of them being wrong. `text-material` on
 * `bg-material-wash` is 7.66:1 in light and 4.87:1 in dark, which is the lowest text cell in
 * the system and still clears the floor for a sentence; `border-material-edge` is the graphic
 * tier, and the only reason it is allowed to be that saturated is that no word is ever set in
 * it.
 *
 * **The border is not trim, it is the shape.** A wash is a tint under a word rather than a
 * silhouette: `--material-wash` measures 1.15:1 against a panel in light, and against
 * `--sunken` in dark it is 1.00:1 — so a badge on an opened fold, drawn by its fill alone,
 * would have no outline at all in one of the two themes. What draws the pill is the edge, at
 * 3.37:1 to 6.43:1 over the wash it encloses, in every theme and on every ground.
 *
 * v1 wrote this as `bg-material-soft` inside `border-material/25`, and both halves were the
 * same mistake pointing in two directions. The fill was named as though it were a panel tone
 * and was taken up as one, which is why the wash is renamed rather than retuned. The border
 * was an alpha of the *text* token, which composites to a real step in dark and to almost
 * nothing in light, so the chip had an edge in one theme and a smudge in the other.
 */
const TONES: Record<Tone, string> = {
  neutral: "border-rule-strong bg-sunken text-ink-2",
  marked: "border-rule-strong bg-sunken text-ink",
  material: "border-material-edge bg-material-wash text-material",
  held: "border-held-edge bg-held-wash text-held",
  cleared: "border-cleared-edge bg-cleared-wash text-cleared",
};

/**
 * And the mark in the graphic tier, because the mark is the one thing in the pill that is not
 * a word.
 *
 * A glyph is a meaningful graphic — 3:1, not 4.5:1 — and the edge tier is what that floor
 * buys: the same value the border is drawn in, so the two drawn parts of a badge are one
 * colour and the read part is another. The lowest cell is 3.37:1, `--cleared-edge` on
 * `--cleared-wash` in light.
 *
 * `neutral` and `marked` are ink and have no second tier, so the mark inherits the word's
 * colour there rather than reaching for a fourth grey. Empty means inherit.
 */
const GLYPH_TONES: Record<Tone, string> = {
  neutral: "",
  marked: "",
  material: "text-material-edge",
  held: "text-held-edge",
  cleared: "text-cleared-edge",
};

/**
 * The three tones that are a verdict. The other two are ink, and the split is written by
 * exclusion on purpose: a sixth tone added to `lib/format` lands on the verdict side and has
 * to carry a mark until somebody says otherwise, which is the safe direction for the rule
 * below.
 */
type VerdictTone = Exclude<Tone, "neutral" | "marked">;

/**
 * A verdict tone may not be worn without a mark, and the type is what says so.
 *
 * *Colour is never the only carrier* is the load-bearing half of this palette rather than a
 * belt-and-braces one, and this is the component that spends it: simulated under deuteranopia
 * the three verdicts separate by only ΔE 4.3–6.0 in the light theme, which is close enough
 * that the hue is the redundancy and the glyph, the word and the row's left edge are the
 * signal. `glyph` was optional, so `<Badge tone="material">Material</Badge>` compiled — a
 * verdict carried by a colour and a word, and for a reader with a red-green deficiency by a
 * word.
 *
 * Stated in the type rather than defaulted from the tone, because a tone does not determine a
 * mark and must not look as though it does: `cleared` is worn by the verdict's tick, by an
 * accepted finding's flag and by a delta's minus, and `lib/format` is the one table that
 * decides which. So a caller naming a verdict tone names the mark with it, and `tsc -b` is
 * what fails when it does not.
 */
type BadgeProps = {
  children: ReactNode;
  className?: string;
  title?: string;
} & ({ tone?: Tone; glyph: MarkShape } | { tone?: Exclude<Tone, VerdictTone>; glyph?: undefined });

export function Badge({ tone = "neutral", glyph, children, className, title }: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        // `rounded-full`, not a step on the ladder. The ladder says how operable a thing is
        // and a badge is not operable at all — it is a word about a row, and the shape that
        // reads as "a word about something" rather than as a control is a pill. It is also
        // the one shape a reader will not confuse with the `rounded-sm` buttons in the
        // decision bar, which sit a few centimetres away and take the same size text.
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.08em]",
        TONES[tone],
        className,
      )}
    >
      {/* Larger than the 11px word beside it rather than smaller. A badge sets its text in
          uppercase at tracking, which reads bigger than it measures; a mark matched to the
          cap height comes out visibly the junior of the two, and at that size a pause closes
          into a dot. */}
      {glyph ? <Mark shape={glyph} className={cn("size-[1.25em]", GLYPH_TONES[tone])} /> : null}
      {children}
    </span>
  );
}

function DescriptorBadge({
  descriptor,
  className,
}: {
  descriptor: Descriptor;
  className?: string;
}) {
  return (
    <Badge
      tone={descriptor.tone}
      glyph={descriptor.glyph}
      className={className}
      title={descriptor.description}
    >
      {descriptor.label}
    </Badge>
  );
}

export const VerdictBadge = ({ verdict, className }: { verdict: string; className?: string }) => (
  <DescriptorBadge descriptor={verdictOf(verdict)} className={className} />
);

export const StatusBadge = ({ status, className }: { status: string; className?: string }) => (
  <DescriptorBadge descriptor={statusOf(status)} className={className} />
);

export const StrengthBadge = ({ strength, className }: { strength: string; className?: string }) => (
  <DescriptorBadge descriptor={strengthOf(strength)} className={className} />
);

export const DispositionBadge = ({
  disposition,
  className,
}: {
  disposition: string;
  className?: string;
}) => <DescriptorBadge descriptor={dispositionOf(disposition)} className={className} />;

/**
 * A quiet label for counts and categories — no semantic tone, no shouting.
 *
 * `max-w-full` and `wrap-anywhere` because a tag is not always a word. Half the call sites
 * put a qualified name in one — `src.audiobook.synthesis.providers.base.SynthesisProvider`
 * is a single token to the line breaker, wider than a phone, and a row of these is
 * `flex-wrap`, which wraps *between* tags and can do nothing about one that is too wide by
 * itself. It escaped the panel instead, and on the finding an `overflow-hidden` ancestor
 * quietly sliced it mid-identifier.
 *
 * **And it has a ground of its own now.** It painted `bg-surface-2` while most of what it sits
 * in — a panel's strip, a card's footer, the fold in the context rail — paints `bg-surface-2`
 * too, so the fill was the ground it was drawn on and the chip was an outline around nothing,
 * held apart by `--rule` at 1.28:1. Both halves move, in the order `docs/design-system.md`
 * puts them: a fill that is a real step off the ground it lies on — `--sunken`, 1.16:1 under a
 * strip and 1.25:1 under a panel, in both themes and in the same direction, which an alpha of
 * a ramp token would not have been — and then the boundary that *groups* rather than the one
 * that separates things already apart, `--rule-strong` at 1.69:1 in light and 2.35:1 in dark
 * against the 1.6:1 a grouping boundary is held to.
 *
 * `--sunken` is what `Badge`'s neutral tone paints as well, and that is the same decision
 * twice rather than a coincidence: a chip with nothing to signal is an inset, not a raised
 * thing.
 */
export function Tag({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-xs border border-rule-strong bg-sunken px-2 py-0.5 text-xs text-ink-2 wrap-anywhere",
        className,
      )}
    >
      {children}
    </span>
  );
}

/**
 * A live dot for provider/model availability. Paired with text, never used alone.
 *
 * `running` is the one value here that is not on the severity scale, and it is deliberately
 * not on it: work being in flight is not a grade, and `lib/format`'s `Tone` stays the closed
 * five-value union so nothing can hand `Badge` or `ui/meta.tsx` a sixth. It lives in this
 * prop's own type instead, which is as far as it can travel.
 *
 * It paints `bg-accent-edge` — the accent, said out loud, rather than `bg-material-edge`, which
 * is the same red through a name that claims a verdict. The rail already spends `material` on a
 * recorded provider failure a few centimetres away, so borrowing it would put two identical
 * dots in one bar meaning "your reasoning provider returned 401" and "a review is running".
 * That widens the accent's budget from four jobs to five; `ui/design-system.test.ts` and
 * `docs/design-system.md` both record the widening rather than hide it.
 *
 * **All five hue-bearing dots are in the graphic tier, and that is what a dot is.** The system
 * splits each signal on the WCAG line — a word clears 4.5:1, a graphic clears 3:1 — and files
 * edges, glyphs, bars and *dots* on the graphic side. This map held the text tier for a
 * revision, which is a wasted signal rather than a contrast failure: a 6px circle drawn in the
 * value picked to be readable as prose is the quietest of the two reds available to it. Moving
 * three of five would have left a map with mixed tiers, so what unblocked it was
 * `--accent-edge` in `styles.css` — the same alias one tier down, minted so the one dot here
 * that is not a verdict has somewhere to go. `neutral` and `marked` stay on the ink ramp, which
 * has no tiers and needs none.
 *
 * The alias runs `--accent: var(--material)` now rather than the other way round, and this is
 * the one file that has to know it, because a custom property computes where it is
 * *declared*: `--accent` resolves on `:root` against the page's `--material` and inherits as a
 * colour rather than as a reference. So `.on-band` redeclares it — and `--accent-edge` with it —
 * which is what keeps this dot right on the one ground that never inverts. It renders in two
 * places: the topbar rail, where the band hands it the dark theme's `#e8403b`, and the phone
 * drawer's panel, where the page's own `#d72e2d` measures 4.85:1. Without the redeclaration the
 * band's value would follow it onto that panel at 4.01:1 — still over the graphic tier's floor,
 * and still the wrong red for the ground it is on. See `styles.css`.
 */
export function StatusDot({
  tone = "neutral",
  pulse,
}: {
  tone?: Tone | "running";
  pulse?: boolean;
}) {
  const fill: Record<Tone | "running", string> = {
    neutral: "bg-ink-3",
    marked: "bg-ink",
    material: "bg-material-edge",
    held: "bg-held-edge",
    cleared: "bg-cleared-edge",
    running: "bg-accent-edge",
  };
  return (
    <span
      aria-hidden="true"
      className={cn("size-1.5 shrink-0 rounded-full", fill[tone], pulse && "animate-breathe")}
    />
  );
}
