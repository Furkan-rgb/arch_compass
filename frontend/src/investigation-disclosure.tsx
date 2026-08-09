import { ChevronRight, FileSearch } from "lucide-react";

import { cn } from "@/lib/utils";

import type { InvestigationLookup, RecordedInvestigation } from "./types";

/**
 * What the review checked before it asked, folded shut beside the questions.
 *
 * A question earns its place by being unanswerable from the repository, and until this
 * record existed the page could not show that the run had tried: a reader met a question
 * with no way to tell "the code is silent on this" from "nobody looked". The record is
 * the run's own transcript — each lookup as it was made and what came back, verbatim —
 * so the proof is the thing itself rather than a claim about it.
 *
 * Closed by default, deliberately. The questions are the work the reader came to do; the
 * transcript is the audit trail behind them, wanted mostly when a question smells like
 * something the code should have settled. A native `details` keeps the fold free of
 * state this page would otherwise have to own.
 *
 * An abandoned investigation renders inside the same fold rather than as an alert of its
 * own: the note is the honest caption on however much was gathered before the failure —
 * the questions below were asked the way every question was asked before looking existed
 * — not an error the reader can act on.
 */
function callLabel(item: InvestigationLookup): string {
  const args = item.arguments ?? {};
  if (item.tool === "search_source" && typeof args.query === "string") {
    return `searched for “${args.query}”`;
  }
  if (item.tool === "read_source" && typeof args.path === "string") {
    const from = typeof args.start_line === "number" ? `:${args.start_line}` : "";
    return `read ${args.path}${from}`;
  }
  return item.tool;
}

function resultExtent(result: string): string {
  const lines = result.split("\n").length;
  return `${lines} line${lines === 1 ? "" : "s"} back`;
}

export function InvestigationDisclosure({
  investigation,
  title = "What the review checked before asking",
}: {
  investigation: RecordedInvestigation;
  /** The fold's own line. The default fits a run's record; an answer's record says what
      the answer checked, because the checking there belongs to one reply and not to the
      review. */
  title?: string;
}) {
  const lookups = investigation.lookups ?? [];
  const closing = (investigation.closing ?? "").trim();
  const abandoned = (investigation.abandoned ?? "").trim();
  if (lookups.length === 0 && !abandoned) return null;
  return (
    <details
      className={cn(
        "group mb-[var(--gap-lg)] max-w-[96ch] rounded-panel border border-dashed",
        "border-rule bg-surface px-[var(--card-pad)] py-3",
      )}
    >
      <summary
        className={cn(
          "flex cursor-pointer list-none flex-wrap items-baseline gap-x-2 gap-y-1",
          "text-ui leading-[1.6] text-ink-2 [&::-webkit-details-marker]:hidden",
        )}
      >
        <FileSearch aria-hidden className="size-[14px] flex-none self-center text-ink-3" />
        <span className="font-semibold">{title}</span>
        <span className="text-meta text-ink-3">
          {lookups.length} lookup{lookups.length === 1 ? "" : "s"}
          {abandoned ? " · cut short" : ""}
        </span>
        <ChevronRight
          aria-hidden
          className={cn(
            "ml-auto size-[14px] flex-none self-center text-ink-3",
            "transition-transform group-open:rotate-90 motion-reduce:transition-none",
          )}
        />
      </summary>
      <ul className="m-0 mt-3 grid list-none grid-cols-[minmax(0,1fr)] gap-3 p-0">
        {lookups.map((item, index) => (
          <li key={`${item.tool}-${index}`}>
            <p className="m-0 mb-1 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-meta">
              <code className="text-meta text-ink-2 [overflow-wrap:anywhere]">{callLabel(item)}</code>
              <span className="text-meta text-ink-3">
                {resultExtent(item.result ?? "")}
              </span>
            </p>
            <pre className="max-h-64 overflow-auto">
              <code>{item.result ?? ""}</code>
            </pre>
          </li>
        ))}
      </ul>
      {closing ? (
        <p className="m-0 mt-3 max-w-[78ch] text-ui leading-[1.55] text-ink-2 [overflow-wrap:anywhere]">
          {closing}
        </p>
      ) : null}
      {abandoned ? (
        <p
          className={cn(
            "m-0 mt-3 max-w-[78ch] rounded-control border border-dashed border-rule",
            "[overflow-wrap:anywhere]",
            "px-3 py-2 text-ui leading-[1.55] text-ink-3",
          )}
        >
          The investigation was cut short — {abandoned}. The questions below were asked
          from what had been gathered by then.
        </p>
      ) : null}
    </details>
  );
}
