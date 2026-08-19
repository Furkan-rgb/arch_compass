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

export type SectionState = { name: string; present: boolean };

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

/** Which required sections a draft already carries with something written under them. */
export function sectionStates(body: string): SectionState[] {
  const found = sectionsIn(body);
  return REQUIRED_SECTIONS.map((name) => ({
    name,
    present: Boolean(found.get(name.toLowerCase())),
  }));
}

export function missingSections(body: string): string[] {
  return sectionStates(body)
    .filter((section) => !section.present)
    .map((section) => section.name);
}

const PROMPTS: Record<string, string> = {
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

/** A starting document with every required section present and prompted. */
export function policyTemplate(): string {
  return REQUIRED_SECTIONS.map((name) => `## ${name}\n\n${PROMPTS[name]}`).join("\n\n") + "\n";
}
