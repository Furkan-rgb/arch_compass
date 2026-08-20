/**
 * The product's vocabulary, in one place.
 *
 * Verdicts, review states and policy strengths are strings on the wire. Every screen that
 * shows one needs the same three things — a word a reader recognises, a glyph so the meaning
 * survives without colour, and a tone — so they are decided here rather than at each call
 * site.
 */

export type Tone = "neutral" | "accent" | "material" | "held" | "cleared";

export type Descriptor = {
  label: string;
  tone: Tone;
  /** A text mark, not an emoji: it has to read as part of the type, and be announced. */
  glyph: string;
  description?: string;
};

const VERDICTS: Record<string, Descriptor> = {
  material: {
    label: "Material",
    tone: "material",
    glyph: "▲",
    description: "The evidence supports an architectural concern worth acting on.",
  },
  held: {
    label: "Held",
    tone: "held",
    glyph: "◆",
    description: "Judgement is waiting on context the repository cannot supply.",
  },
  cleared: {
    label: "Cleared",
    tone: "cleared",
    glyph: "●",
    description: "The candidate was assessed and found unproblematic.",
  },
};

const STATUSES: Record<string, Descriptor> = {
  completed: { label: "Completed", tone: "cleared", glyph: "●" },
  awaiting_answers: { label: "Awaiting answers", tone: "held", glyph: "◆" },
  running: { label: "Running", tone: "accent", glyph: "◐" },
  failed: { label: "Failed", tone: "material", glyph: "▲" },
  cancelled: { label: "Cancelled", tone: "neutral", glyph: "○" },
};

/**
 * How binding a policy is — which is emphasis, not alarm.
 *
 * The three hues are a severity scale: red is something to act on, amber is something
 * waiting on a person, green is something settled. That reading holds for a verdict, for a
 * review's state and for a standing decision, and it does not hold here. A required policy
 * is not a problem; it is the policy a reviewer should read first. Painted in the verdict
 * red it turned the policy library into a list of alarms, sitting one nav item away from a
 * workbench where that exact red means "a material architectural concern was found".
 *
 * So the strongest policy takes the accent, which everywhere else in this interface means
 * "the thing to look at", and the other two take the neutral. The glyph and the word carry
 * the step between them, which is what those exist for.
 */
const STRENGTHS: Record<string, Descriptor> = {
  required: { label: "Required", tone: "accent", glyph: "▲" },
  preferred: { label: "Preferred", tone: "neutral", glyph: "◆" },
  guidance: { label: "Guidance", tone: "neutral", glyph: "○" },
};

const DISPOSITIONS: Record<string, Descriptor> = {
  accept: { label: "Accepted", tone: "cleared", glyph: "●" },
  park: { label: "Parked", tone: "held", glyph: "◆" },
  waive: { label: "Waived", tone: "neutral", glyph: "○" },
};

function lookup(table: Record<string, Descriptor>, value: string): Descriptor {
  return table[value] ?? { label: humanise(value), tone: "neutral", glyph: "○" };
}

export const verdictOf = (value: string) => lookup(VERDICTS, value);
export const statusOf = (value: string) => lookup(STATUSES, value);
export const strengthOf = (value: string) => lookup(STRENGTHS, value);
export const dispositionOf = (value: string) => lookup(DISPOSITIONS, value);

/** Verdicts in the order a reviewer should meet them: what needs a human comes first. */
export const VERDICT_ORDER = ["material", "held", "cleared"] as const;

export function verdictRank(verdict: string): number {
  const index = VERDICT_ORDER.indexOf(verdict as (typeof VERDICT_ORDER)[number]);
  return index === -1 ? VERDICT_ORDER.length : index;
}

export function humanise(value: string): string {
  const spaced = value.replaceAll("_", " ").trim();
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : value;
}

/** `/home/me/work/payments` → `payments`. The tail is what a reader recognises. */
export function repositoryName(path: string): string {
  const parts = path.split("/").filter(Boolean);
  return parts.at(-1) || path;
}

/** Keep the first and last segments, elide the middle: `src/…/orders/gateway.py`. */
/**
 * A qualified name split into the part that locates it and the part that names it.
 *
 * A queue row identifies a thing; it is not a place to read a sentence. Showing the
 * namespace small and dim above the leaf gives both without either of them being able to
 * push the rail sideways: the namespace is clipped, the leaf wraps at any character.
 */
export function splitQualified(name: string): { namespace: string; leaf: string } {
  const cut = name.lastIndexOf(".");
  if (cut <= 0) return { namespace: "", leaf: name };
  return { namespace: name.slice(0, cut), leaf: name.slice(cut + 1) };
}

export function shortPath(path: string, keep = 2): string {
  const parts = path.split("/").filter(Boolean);
  if (parts.length <= keep + 1) return path;
  return `${parts[0]}/…/${parts.slice(-keep).join("/")}`;
}

export function shortId(value: string, length = 8): string {
  return value.length <= length ? value : value.slice(0, length);
}

const UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["year", 31_536_000_000],
  ["month", 2_592_000_000],
  ["week", 604_800_000],
  ["day", 86_400_000],
  ["hour", 3_600_000],
  ["minute", 60_000],
];

/** "4 minutes ago", without pulling in a date library. */
export function relativeTime(value: string | null | undefined, now = Date.now()): string {
  if (!value) return "unknown";
  const stamp = Date.parse(value);
  if (Number.isNaN(stamp)) return "unknown";
  const elapsed = now - stamp;
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, milliseconds] of UNITS) {
    if (Math.abs(elapsed) >= milliseconds) {
      return formatter.format(-Math.round(elapsed / milliseconds), unit);
    }
  }
  return "just now";
}

export function absoluteTime(value: string | null | undefined): string {
  if (!value) return "—";
  const stamp = new Date(value);
  if (Number.isNaN(stamp.valueOf())) return "—";
  return stamp.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

/** Freshness of an indexed atlas, stated the way a reviewer asks about it. */
export function atlasFreshness(indexedAt: string | null | undefined, now = Date.now()) {
  if (!indexedAt) return { label: "Never indexed", tone: "neutral" as Tone };
  const age = now - Date.parse(indexedAt);
  if (Number.isNaN(age)) return { label: "Never indexed", tone: "neutral" as Tone };
  if (age < 3_600_000) return { label: "Fresh", tone: "cleared" as Tone };
  if (age < 604_800_000) return { label: "Ageing", tone: "held" as Tone };
  return { label: "Stale", tone: "material" as Tone };
}
