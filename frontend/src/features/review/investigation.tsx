import type { Investigation, InvestigationLookup } from "../../api";
import { humanise, plural } from "../../lib/format";

/**
 * One lookup said the way a person would say it, rather than as the call it was.
 *
 * `related_code({node_id: "node_a1", kind: "implementations"})` is the record; "asked what
 * implements node_a1" is what a reader is trying to find out. The raw tool name is the
 * fallback, so a tool added later still renders rather than disappearing.
 */
export function lookupLabel(item: InvestigationLookup): string {
  const args = item.arguments ?? {};
  // `qualified_name` is what the tools take; `node_id` is what they took before the model
  // stopped being handed internal handles. Both are read, because a stored review is an
  // immutable record and one written last month must still render as a sentence.
  const subject = args.qualified_name ?? args.node_id;
  if ((item.tool === "search_code" || item.tool === "find_code") && args.name) {
    return `searched for ${args.name}`;
  }
  if (item.tool === "describe_code" && subject) return `inspected ${subject}`;
  if (item.tool === "related_code" && subject) {
    const relation = args.relation ?? args.kind;
    if (relation) return `asked what ${humanise(relation).toLowerCase()} ${subject}`;
  }
  if (item.tool === "read_code" && subject) return `read the code at ${subject}`;
  if (item.tool === "flagged_signals") {
    return args.codes ? `checked signals ${args.codes}` : "checked what was already flagged";
  }
  return item.tool;
}

function resultExtent(result: string): string {
  return `${plural(result.split("\n").length, "line")} back`;
}

/**
 * How an investigation ended, in the reader's words rather than the enum's.
 *
 * `null` is deliberately not "finished". It means the reason was not recorded — which is
 * true of every investigation stored before terminations existed, and of nothing else — and
 * calling that a natural end would tell a reader the search was complete on the strength of
 * a missing field.
 */
const ENDINGS: Record<string, string> = {
  natural_end: "the pass stopped looking",
  model_call_limit: "cut short: no turns left",
  lookup_limit: "cut short: no lookups left",
  investigation_size_limit: "cut short: too much gathered",
  provider_error: "cut short: the model stopped answering",
};

function ending(termination: string | null | undefined): string {
  if (!termination) return "why it ended was not recorded";
  return ENDINGS[termination] ?? `ended: ${humanise(termination)}`;
}

/**
 * What the closed fold says, which has to be what is inside it.
 *
 * A fold labelled only "Looked up" makes a reader open it to find out whether it was worth
 * opening. The count is half the answer and how the looking ended is the other half.
 *
 * It used to say "settled the hinge" or "the repository was silent", off a `resolved` flag
 * the investigating model set. Nothing here settles a hinge any more — the judge does, and
 * the finding beside this says what it decided. What this can answer for is how much looking
 * there was and whether it ran out.
 */
export function investigationSummary(investigation: Investigation): string {
  if (!investigation.lookups.length) {
    if (investigation.withheld) return "nothing could be looked up";
    // Cut short before it asked anything, which is not the same as having asked and found
    // nothing — and the old wording ("no lookup was made") read like a choice.
    return investigation.termination && investigation.termination !== "natural_end"
      ? ending(investigation.termination)
      : "no lookup was made";
  }
  const counted = plural(investigation.lookups.length, "lookup");
  if (!investigation.candidate_id) return counted;
  return `${counted} · ${ending(investigation.termination)}`;
}

/**
 * The transcript itself, without a wrapper.
 *
 * Two surfaces show this and they need different containers — a finding's fold is
 * full-bleed against the panel's rules, and a chat bubble's walls a bleed would burst
 * through. So the fold is the caller's and the record is here.
 */
export function InvestigationTranscript({ investigation }: { investigation: Investigation }) {
  return (
    <>
      {investigation.lookups.length ? (
        <ul className="grid gap-3">
          {investigation.lookups.map((item, index) => (
            <li key={`${item.tool}-${index}`}>
              <p className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="font-mono text-[11px] leading-5 text-ink-2 [overflow-wrap:anywhere]">
                  {lookupLabel(item)}
                </span>
                <span className="text-[11px] leading-5 text-ink-3">{resultExtent(item.result)}</span>
              </p>
              <pre className="mt-1 max-h-64 overflow-auto rounded-md border border-rule bg-surface px-3 py-2">
                <code className="font-mono text-[11px] leading-5 text-ink-2">{item.result}</code>
              </pre>
            </li>
          ))}
        </ul>
      ) : null}
      {investigation.closing ? (
        <p className="mt-3 max-w-[62ch] text-[13px] leading-6 text-ink-2 wrap-anywhere">
          {investigation.closing}
        </p>
      ) : null}
      {investigation.withheld ? (
        /* The application's own sentence, verbatim: it names the way back rather than
           describing a fault, and paraphrasing it would lose the instruction. */
        <p className="mt-3 max-w-[62ch] text-[12px] leading-5 text-ink-3 [overflow-wrap:anywhere]">
          {investigation.withheld}
        </p>
      ) : null}
      {investigation.termination && investigation.termination !== "natural_end" ? (
        /* Said whether or not it was recorded, and said differently. A reader weighing a
           verdict needs to know the difference between "the repository is silent" and "we
           stopped asking" — and, for a review from before this was kept, that nobody knows. */
        <p className="mt-3 max-w-[62ch] text-[12px] leading-5 text-ink-3 [overflow-wrap:anywhere]">
          {investigation.termination
            ? `The lookups stopped early — ${ending(investigation.termination)}. What the review
               concluded was reached from what had been gathered by then.`
            : `It is not recorded why this looking ended, so it may be incomplete.`}
        </p>
      ) : null}
    </>
  );
}
