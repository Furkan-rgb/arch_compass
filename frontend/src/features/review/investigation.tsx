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
  if (item.tool === "find_code" && args.name) return `looked for ${args.name}`;
  if (item.tool === "describe_code" && args.node_id) return `inspected ${args.node_id}`;
  if (item.tool === "related_code" && args.node_id && args.kind) {
    return `asked what ${humanise(args.kind).toLowerCase()} ${args.node_id}`;
  }
  if (item.tool === "read_code" && args.node_id) return `read the code at ${args.node_id}`;
  if (item.tool === "flagged_signals") {
    return args.codes ? `checked signals ${args.codes}` : "checked what was already flagged";
  }
  return item.tool;
}

function resultExtent(result: string): string {
  return `${plural(result.split("\n").length, "line")} back`;
}

/**
 * What the closed fold says, which has to be what is inside it.
 *
 * A fold labelled only "Looked up" makes a reader open it to find out whether it was worth
 * opening. The count is half the answer and what came of it is the other half.
 */
export function investigationSummary(investigation: Investigation): string {
  if (!investigation.lookups.length) {
    return investigation.withheld ? "nothing could be looked up" : "cut short before any lookup";
  }
  const counted = plural(investigation.lookups.length, "lookup");
  if (investigation.abandoned) return `${counted} · cut short`;
  if (!investigation.candidate_id) return counted;
  return `${counted} · ${investigation.resolved ? "settled the hinge" : "the repository was silent"}`;
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
      {investigation.abandoned ? (
        <p className="mt-3 max-w-[62ch] text-[12px] leading-5 text-ink-3 [overflow-wrap:anywhere]">
          The lookups stopped early — {investigation.abandoned}. What follows was reached from
          what had been gathered by then.
        </p>
      ) : null}
    </>
  );
}
