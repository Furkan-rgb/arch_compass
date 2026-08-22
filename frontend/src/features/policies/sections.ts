/**
 * The shape a policy document has to have.
 *
 * The workspace stores a policy as a Markdown file and re-reads it with the same parser it
 * uses for the bundled corpus, which requires these nine `##` sections and refuses a file
 * that is missing one or leaves one empty. That rule lived only in the failure message
 * before: the form accepted any prose and the save failed afterwards. Mirroring it here is
 * what lets the editor scaffold the sections and say, while the author is writing, which of
 * them are still outstanding.
 *
 * Kept in the author's own casing; the parser compares case-insensitively.
 */
export const REQUIRED_SECTIONS = [
  "Intent",
  "Guidance",
  "Signals",
  "Diagnostic questions",
  "Likely consequences",
  "Exceptions",
  "Positive example",
  "Counterexample",
  "Related policies",
] as const;

export type SectionState = { name: string; prompt: string; present: boolean };

/** The same split the workspace parser performs: `^## Heading` up to the next one. */
export function sectionsIn(body: string): Map<string, string> {
  const found = new Map<string, string>();
  const matches = [...body.matchAll(/^##[ \t]+(.+?)[ \t]*$/gm)];
  matches.forEach((match, index) => {
    const start = (match.index ?? 0) + match[0].length;
    const end = index + 1 < matches.length ? (matches[index + 1].index ?? body.length) : body.length;
    found.set(match[1].trim().toLowerCase(), body.slice(start, end).trim());
  });
  return found;
}

/**
 * What each section is for, said where the author is writing rather than inside the draft.
 *
 * These were the body of the scaffold, which made them a document the parser accepted and
 * the judge would have read. They are a hint now: the checklist prints one under every
 * section still outstanding, so the guidance arrives at the moment it is needed and never
 * as the policy.
 */
export const SECTION_PROMPTS: Record<string, string> = {
  Intent: "What this policy protects, in one or two sentences.",
  Guidance: "What to do. Be specific enough to act on.",
  Signals: "What in a repository suggests this policy applies.",
  "Diagnostic questions": "What to ask when the evidence is ambiguous.",
  "Likely consequences": "What tends to happen when this is ignored.",
  Exceptions: "When not to apply this, and why that is legitimate.",
  "Positive example": "A short example of the shape this policy wants.",
  Counterexample: "A short example of the shape it argues against.",
  "Related policies": "Policies that reinforce or trade off against this one.",
};

/** Whitespace and case removed, so a prompt that was reflowed is still the same prompt. */
function normalise(text: string): string {
  return text.replace(/\s+/g, " ").trim().toLowerCase();
}

/**
 * Which required sections somebody has actually written, rather than which have a heading.
 *
 * "Has text under it" was the whole test, and the scaffold below used to write its own
 * prompt under every heading — so an untouched template reported nine of nine written and
 * the form offered to save it. What that saved was a policy whose body read *"What this
 * policy protects, in one or two sentences."* nine times, into the corpus retrieval draws
 * on and the judge reads as authored guidance.
 *
 * The scaffold no longer carries the prompts, and this compares against them anyway. The
 * prompt is on screen beside the section it belongs to, which is one paste away from being
 * in the box — and a section holding the question it was asked is not an answer to it.
 */
export function sectionStates(body: string): SectionState[] {
  const found = sectionsIn(body);
  return REQUIRED_SECTIONS.map((name) => {
    const prompt = SECTION_PROMPTS[name];
    const written = found.get(name.toLowerCase()) ?? "";
    return { name, prompt, present: Boolean(written) && normalise(written) !== normalise(prompt) };
  });
}

export function missingSections(body: string): string[] {
  return sectionStates(body)
    .filter((section) => !section.present)
    .map((section) => section.name);
}

/**
 * The nine headings, in order, with nothing written under them.
 *
 * A scaffold is a shape to fill in, not a draft. This one used to arrive with its own
 * prompts as the prose, which the workspace parser accepts and this page counted as written
 * — so the shortest path from opening the form to a saved policy was a title, a description
 * and a body of nine instructions to the author. The prompts live in `SECTION_PROMPTS` and
 * are shown beside the checklist instead.
 */
export function policyTemplate(): string {
  return REQUIRED_SECTIONS.map((name) => `## ${name}\n`).join("\n") + "\n";
}
