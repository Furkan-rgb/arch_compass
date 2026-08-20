import type { ReactNode } from "react";

import { cn } from "../lib/cn";
import {
  type Descriptor,
  type Tone,
  dispositionOf,
  statusOf,
  strengthOf,
  verdictOf,
} from "../lib/format";

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
  glyph?: string;
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
      {glyph ? (
        <span aria-hidden="true" className="text-[9px] leading-none opacity-80">
          {glyph}
        </span>
      ) : null}
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

/** A live dot for provider/model availability. Paired with text, never used alone. */
export function StatusDot({ tone = "neutral", pulse }: { tone?: Tone; pulse?: boolean }) {
  const fill: Record<Tone, string> = {
    neutral: "bg-ink-3",
    marked: "bg-ink",
    material: "bg-material",
    held: "bg-held",
    cleared: "bg-cleared",
  };
  return (
    <span
      aria-hidden="true"
      className={cn("size-1.5 shrink-0 rounded-full", fill[tone], pulse && "animate-breathe")}
    />
  );
}
