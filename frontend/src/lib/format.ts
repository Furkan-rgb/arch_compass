/**
 * The product's vocabulary, in one place.
 *
 * Verdicts, review states and policy strengths are strings on the wire. Every screen that
 * shows one needs the same three things — a word a reader recognises, a glyph so the meaning
 * survives without colour, and a tone — so they are decided here rather than at each call
 * site.
 */

export type Tone = "neutral" | "marked" | "material" | "held" | "cleared";

/**
 * The mark a descriptor wears, named rather than drawn.
 *
 * These were literal characters (`▲ ◆ ●`) until the glyphs turned out to be the one part of
 * the type that neither shipped face contains — every one fell back to whatever the operating
 * system had, at three optical sizes on three baselines. They were hand-cut SVG for a while
 * after that. `ui/mark.tsx` resolves them to Lucide now; this stays a plain union so the
 * vocabulary below is still data — no JSX in `lib`, and a descriptor is still something a
 * test can compare.
 *
 * Three registers, and which one a thing wears is a meaning rather than a style:
 *
 * - **A sign** — `alert`, `pause`, `check`, and the three a run can be in — for the things
 *   being *graded*: the model's verdict, and a review's own state. A grade has to read before
 *   its key is learnt, and the geometric shapes did not: three distinguishable marks, three
 *   meaningless ones, leaving a first-time reader with only the hue to go on, which is the
 *   exact dependence "a colour never carries meaning alone" exists to prevent.
 * - **A step on a scale** — `solid`, `hollow`, `dashed` — for a position that is not a grade.
 *   Deliberately abstract; see the note above `STRENGTHS`.
 * - **A person's own move** — `flag`, `clock`, `slash` — for what somebody decided, which is
 *   never the same kind of statement as what the model found. See the note above
 *   `DISPOSITIONS`.
 * - **A difference between two reviews** — `plus`, `minus`, `swap`, `equals` — for how a
 *   candidate moved from one revision to the next. Diff notation, because that is what a
 *   delta is: it says a candidate arrived, left, was judged differently or was not, and none
 *   of those four is a claim about whether the candidate is any good. Owned by
 *   `features/review/surfaces.tsx` rather than by a table here, because the delta states are
 *   computed from two reviews rather than read off one wire value.
 */
export type MarkShape =
  | "alert"
  | "pause"
  | "check"
  | "failed"
  | "running"
  | "stopped"
  | "solid"
  | "hollow"
  | "dashed"
  | "flag"
  | "clock"
  | "slash"
  | "plus"
  | "minus"
  | "swap"
  | "equals";

export type Descriptor = {
  label: string;
  tone: Tone;
  /** Which mark says this without colour. Drawn by `ui/mark.tsx`. */
  glyph: MarkShape;
  description?: string;
};

/**
 * The model's three verdicts — the one scale in the product that is a judgement of something.
 *
 * These wear signs rather than shapes because the verdict is the single value a reader must
 * be able to take in without having read a key: what wants me, what is waiting on me, what is
 * done. The tone reinforces it and never carries it alone.
 */
const VERDICTS: Record<string, Descriptor> = {
  material: {
    label: "Material",
    tone: "material",
    glyph: "alert",
    description: "The evidence supports an architectural concern worth acting on.",
  },
  held: {
    label: "Held",
    tone: "held",
    glyph: "pause",
    description: "Judgement is waiting on context the repository cannot supply.",
  },
  cleared: {
    label: "Cleared",
    tone: "cleared",
    glyph: "check",
    description: "The candidate was assessed and found unproblematic.",
  },
};

/**
 * A review's own state, which reads on the same scale as a verdict and so wears the same
 * signs: finished, waiting on a person, went wrong.
 *
 * `running` and `cancelled` are the two that are not a grade — one is under way and one
 * stopped — so they keep the abstract half-circle and ring.
 */
const STATUSES: Record<string, Descriptor> = {
  completed: { label: "Completed", tone: "cleared", glyph: "check" },
  awaiting_answers: { label: "Awaiting answers", tone: "held", glyph: "pause" },
  running: { label: "Running", tone: "marked", glyph: "running" },
  // Not `alert`: a run that broke is not a material finding, and the two sit one page apart.
  failed: { label: "Failed", tone: "material", glyph: "failed" },
  cancelled: { label: "Cancelled", tone: "neutral", glyph: "stopped" },
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
 * The first answer gave the strongest policy the indigo accent, on the argument that the
 * accent meant "the thing to look at" everywhere else. That argument was right and its
 * answer is gone: there is no accent hue in this system, because chroma is spent on
 * verdicts and nothing else.
 *
 * So the step is carried by weight and rule instead. `marked` is ink on a stronger border,
 * the other two recede to the neutral, and the glyph and the word carry the distinction —
 * which is what those exist for. Emphasis without alarm, and no hue at all.
 *
 * The same argument decides the marks. When the verdicts took the caution sign, a required
 * policy could not follow them: an alert triangle on the strongest policy would say the very
 * thing this comment exists to deny. So the step is a filled centre, then an outline, then a
 * dashed outline — solid to faint, which is a scale and nothing more.
 */
const STRENGTHS: Record<string, Descriptor> = {
  required: { label: "Required", tone: "marked", glyph: "solid" },
  preferred: { label: "Preferred", tone: "neutral", glyph: "hollow" },
  guidance: { label: "Guidance", tone: "neutral", glyph: "dashed" },
};

/**
 * What a person decided — which is not the same kind of statement as what the model found,
 * and must not look like one.
 *
 * Accepting a finding is a commitment to act on it, not a report that it went away; a tick
 * would say the second, which is why `accept` flags rather than ticks. Park is explicitly
 * later, and waive is explicitly not. A decision may share a verdict's *tone*, because it
 * answers one — never its mark. This is where the charter's separation between the model's
 * verdict and the person's decision becomes visible.
 */
const DISPOSITIONS: Record<string, Descriptor> = {
  accept: { label: "Accepted", tone: "cleared", glyph: "flag" },
  park: { label: "Parked", tone: "held", glyph: "clock" },
  waive: { label: "Waived", tone: "neutral", glyph: "slash" },
};

function lookup(table: Record<string, Descriptor>, value: string): Descriptor {
  return table[value] ?? { label: humanise(value), tone: "neutral", glyph: "hollow" };
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
  // Seconds are here for the one place a reader is watching the clock rather than reading a
  // record: a provider probe, and a run's elapsed time. "just now" is the right answer for a
  // review filed forty seconds ago and the wrong one for a reachability check, where the
  // question being asked is exactly how stale the answer is.
  ["second", 1_000],
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

/**
 * Freshness of an indexed atlas, as a position on a scale rather than as a grade.
 *
 * It used to answer with a verdict tone — `cleared` for Fresh, `held` for Ageing, `material`
 * for Stale — and that is the one hue in the product saying *the evidence supports an
 * architectural concern worth acting on*, spent on an index nobody had rebuilt this week.
 * `verdict-hues.test.ts` allows this file to name a hue because of `verdictOf`, which is the
 * table that decides which **verdict** takes which tone; a second table in the same file
 * dressing something else in the same three was exactly what that allowance was not for.
 *
 * So it answers with a `MarkShape` from the step set — solid, outline, dashed — which is what
 * `docs/design-system.md` reserves for a position that is not a grade. The word beside it
 * already says which step it is, so nothing is carried by the shape alone.
 *
 * The distance leads and the clock is the fallback, because the reviewer's question is
 * whether the atlas still describes the code on disk and only one of the two answers it. By
 * the clock, an index built 61 minutes ago against an untouched checkout read "Ageing" and
 * one built 50 minutes ago with twelve commits landed since read "Fresh" — the wrong answer
 * twice, in the two cases somebody would actually act on. `commitsBehind` is `null` where
 * the workspace cannot say (a folder outside git, or a commit the checkout no longer holds),
 * and only then is age all there is to go on.
 */
export function atlasFreshness(
  indexedAt: string | null | undefined,
  commitsBehind?: number | null,
  now = Date.now(),
  headCommitSha?: string | null,
): { label: string; step: MarkShape } {
  if (typeof commitsBehind === "number") {
    if (commitsBehind <= 0) return { label: "Current", step: "solid" };
    return { label: `${plural(commitsBehind, "commit")} behind`, step: "dashed" };
  }
  // A checkout that has a HEAD but could not be asked how far this atlas is from it — a
  // rewritten history, or a repository re-cloned since. The relationship to the code on disk
  // is unknown, which is not the same as young: an atlas built four minutes ago at a commit
  // this checkout has never heard of read "Fresh", with a solid mark, and nothing on the card
  // said the distance could not be measured. `docs/charter.md`: an explicit unknown outranks
  // an implied one. Where there is no HEAD at all — a folder outside git — there is no
  // distance to be missing, and the clock is honestly all there is.
  if (headCommitSha) return { label: "Distance unknown", step: "dashed" };
  if (!indexedAt) return { label: "Never indexed", step: "dashed" };
  const age = now - Date.parse(indexedAt);
  if (Number.isNaN(age)) return { label: "Never indexed", step: "dashed" };
  if (age < 3_600_000) return { label: "Fresh", step: "solid" };
  if (age < 604_800_000) return { label: "Ageing", step: "hollow" };
  return { label: "Stale", step: "dashed" };
}
