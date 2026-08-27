import type { Investigation, InvestigationLookup } from "../../api";
import { humanise, plural } from "../../lib/format";
import { Prose } from "../../ui/prose";
import { LookupResult } from "./lookup-result";

/**
 * One lookup said the way a person would say it, rather than as the call it was.
 *
 * `related_code({node_id: "node_a1", kind: "implementations"})` is the record; "asked what
 * implements node_a1" is what a reader is trying to find out. The raw tool name is the
 * fallback, so a tool added later still renders rather than disappearing.
 */
export function lookupLabel(item: InvestigationLookup): string {
  const args = item.arguments ?? {};
  // `qualified_name` is what the atlas tools take; `node_id` is what they took before the
  // model stopped being handed internal handles. Both are read, because a stored review is
  // an immutable record and one written last month must still render as a sentence.
  const subject = args.qualified_name ?? args.node_id;
  // The repository tools, which are most of what a judgement does. They arrived with the
  // filesystem the judge reads the reviewed revision through, and nothing here knew their
  // names — so the majority of every trace rendered as `read_file` with no file in it, on a
  // surface whose whole job is to say what was checked.
  if (item.tool === "ls" && args.path) return `listed ${args.path}`;
  if (item.tool === "read_file" && args.file_path) return `read ${args.file_path}`;
  if (item.tool === "glob" && args.pattern) return `looked for files matching ${args.pattern}`;
  if (item.tool === "grep" && args.pattern) {
    // `path` narrows the search and `glob` narrows it by name; either is worth saying,
    // because "searched for Protocol" and "searched tests for Protocol" are different checks.
    const within = args.path ?? args.glob;
    return within
      ? `searched ${within} for ${args.pattern}`
      : `searched the code for ${args.pattern}`;
  }
  if (item.tool === "search_policies" && args.query) {
    return `looked for policies about ${args.query}`;
  }
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
 * Only the endings that are news are here, and every one of them is the same news: the
 * looking stopped before it was finished. A natural end is deliberately absent. It is the
 * one termination that tells a reader nothing the lookup count beside it has not already
 * told them — "it ended when it ended" — so it earns no clause and is left unsaid.
 *
 * `null` is deliberately not a natural end either. It means the reason was not recorded —
 * which is true of every investigation stored before terminations existed, and of nothing
 * else — and letting it fall silent with the natural ends would tell a reader the search
 * was complete on the strength of a missing field.
 */
const ENDINGS: Record<string, string> = {
  model_call_limit: "cut short: no turns left",
  lookup_limit: "cut short: no lookups left",
  investigation_size_limit: "cut short: too much gathered",
  provider_error: "cut short: the model stopped answering",
  // `Termination` has eight members and this map covered five of them, which were not the
  // five that happen. Over the 147 stored investigations the endings are `natural_end` 143,
  // `repeated_tool_call` 3 and `malformed_judgement` 1; the other four written here have
  // never occurred once. So the second commonest real ending was falling through to
  // `humanise` and printing "ended: Repeated tool call" — the enum member itself, title-cased,
  // in the one line this fold has to say something in.
  //
  // Not "no lookups left", which is what a spent budget would be. `domain/review.py` calls it
  // a stuck loop rather than a search: the same question put to the same tool a third time,
  // against a repository that cannot change while it is judged and tools that only read. The
  // third answer is the second answer. So the clause says what the pass saw.
  repeated_tool_call: "cut short: it began repeating itself",
  wall_clock_limit: "cut short: out of time",
  malformed_judgement: "cut short: the answer could not be used",
};

function ending(termination: string | null | undefined): string {
  if (!termination) return "end not recorded";
  return ENDINGS[termination] ?? `ended: ${humanise(termination)}`;
}

/**
 * What the closed fold says, which has to be what is inside it.
 *
 * A fold labelled only "Looked up" makes a reader open it to find out whether it was worth
 * opening. The count is half the answer; the other half is whether the looking ran out, and
 * that half is only worth printing when the answer is yes. A pass that stopped of its own
 * accord adds no clause at all: the count has already said how much looking there was, and
 * "the pass stopped looking" after it repeats the fact in worse words. A pass that was cut
 * short says so, and a stored review whose reason was never recorded says that instead of
 * borrowing the silence that now means a natural end.
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
  if (investigation.termination === "natural_end") return counted;
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
              {/* Drawn as the shape the tool it names produces, rather than as one grey wall
                  of preformatted text. The dispatch, the six shapes and the argument for
                  dispatching on the tool rather than on the text are all in
                  `lookup-result.tsx`; the block, its ground and its cap have not moved and
                  are argued there too. */}
              <LookupResult item={item} />
            </li>
          ))}
        </ul>
      ) : null}
      {investigation.closing ? (
        // Written by the same judge loop that writes a finding's reasoning, and about the
        // same code, so it quotes identifiers the same way and is drawn the same way.
        <p className="mt-3 max-w-[46ch] text-[13px] leading-6 text-ink-2 wrap-anywhere">
          <Prose>{investigation.closing}</Prose>
        </p>
      ) : null}
      {investigation.withheld ? (
        /* The application's own sentence, verbatim: it names the way back rather than
           describing a fault, and paraphrasing it would lose the instruction. */
        <p className="mt-3 max-w-[46ch] text-[12px] leading-5 text-ink-3 [overflow-wrap:anywhere]">
          <Prose>{investigation.withheld}</Prose>
        </p>
      ) : null}
      {investigation.lookups.length && investigation.termination !== "natural_end" ? (
        /* Said whether or not it was recorded, and said differently. A reader weighing a
           verdict needs to know the difference between "the repository is silent" and "we
           stopped asking" — and, for a review stored before terminations were kept, that
           nobody knows which of the two it was.

           The guard is on `lookups`, not on `termination`. Guarding on `termination` made
           the second branch unreachable: a stored review from before the field existed has
           `termination: null`, which is exactly the case the sentence is for, and it was
           the one case that silently rendered nothing. */
        <p className="mt-3 max-w-[46ch] text-[12px] leading-5 text-ink-3 [overflow-wrap:anywhere]">
          {investigation.termination
            ? `The lookups stopped early — ${ending(investigation.termination)}. What the review
               concluded was reached from what had been gathered by then.`
            : `It is not recorded why this looking ended, so it may be incomplete.`}
        </p>
      ) : null}
    </>
  );
}
