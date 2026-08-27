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

const TONES: Record<Tone, string> = {
  neutral: "border-rule-strong bg-sunken text-ink-2",
  marked: "border-rule-strong bg-sunken text-ink",
  material: "border-material/25 bg-material-soft text-material",
  held: "border-held/30 bg-held-soft text-held",
  cleared: "border-cleared/25 bg-cleared-soft text-cleared",
};

export function Badge({
  tone = "neutral",
  glyph,
  children,
  className,
  title,
}: {
  tone?: Tone;
  glyph?: MarkShape;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
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
      {glyph ? <Mark shape={glyph} className="size-[1.25em]" /> : null}
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
 */
export function Tag({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-xs border border-rule bg-surface-2 px-2 py-0.5 text-xs text-ink-2 wrap-anywhere",
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
 * It paints `bg-accent` — the accent, said out loud, rather than `bg-material`, which is the
 * same red through a name that claims a verdict. The rail already spends `material` on a
 * recorded provider failure a few centimetres away, so borrowing it would put two identical
 * dots in one bar meaning "your reasoning provider returned 401" and "a review is running".
 * That widens the accent's budget from four jobs to five; `ui/design-system.test.ts` and
 * `docs/design-system.md` both record the widening rather than hide it.
 *
 * `bg-accent` and not the lifted band value, because this dot also renders on a page surface
 * in the phone drawer, where `#f27166` measures 2.63:1. `.on-band` is what lifts it for the
 * one ground that never inverts; see `styles.css`.
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
    material: "bg-material",
    held: "bg-held",
    cleared: "bg-cleared",
    running: "bg-accent",
  };
  return (
    <span
      aria-hidden="true"
      className={cn("size-1.5 shrink-0 rounded-full", fill[tone], pulse && "animate-breathe")}
    />
  );
}
