import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { BEARINGS } from "./bearings";
import { CASE_FILE } from "./case-file";

/**
 * The landing page may write out a review. It may not write out a policy.
 *
 * Both files this checks say in their own comments that every policy they name is one the
 * bundled corpus really contains — because the page's whole claim is that a verdict rests on
 * guidance somebody wrote, and a page naming guidance that does not ship is making that claim
 * falsely. The claim was already there; nothing enforced it. Three of the ids in the
 * retrieval manifests turned out to be invented, and one policy's title was a paraphrase of
 * the real one.
 *
 * So this reads the corpus itself rather than a copy of it. That is what makes it a check
 * rather than a second place to get it wrong: renaming a policy file, or retitling one, fails
 * here, which is the moment somebody can still fix the page.
 */

const CORPUS = join(import.meta.dirname, "../../../../src/archcompass/policies/general");

/** Every bundled policy, by id, with the title its own front matter gives it. */
function corpus(): Map<string, string> {
  const entries = readdirSync(CORPUS).filter((name) => name.endsWith(".md"));
  return new Map(
    entries.map((name) => {
      const body = readFileSync(join(CORPUS, name), "utf8");
      const id = /^id:\s*(.+)$/m.exec(body)?.[1].trim() ?? "";
      const title = /^title:\s*(.+)$/m.exec(body)?.[1].trim() ?? "";
      return [id, title];
    }),
  );
}

describe("the policies the landing page names", () => {
  it("reads a corpus that is actually there", () => {
    // A guard on the guard: a wrong path would make every assertion below vacuous by
    // finding nothing to contradict.
    expect(corpus().size).toBeGreaterThan(40);
  });

  it("are all policies the bundled corpus ships", () => {
    const bundled = corpus();
    const named = [
      ...BEARINGS.map((bearing) => bearing.policy.id),
      ...BEARINGS.flatMap((bearing) => (bearing.also ? [bearing.also] : [])),
      ...CASE_FILE.findings.flatMap((finding) =>
        finding.policies.map((bearing) => bearing.policy_id),
      ),
      ...CASE_FILE.retrieval_manifest.flatMap((entry) => entry.selected_policy_ids),
    ];

    expect(named.filter((id) => !bundled.has(id))).toEqual([]);
  });

  it("are titled the way the corpus titles them", () => {
    const bundled = corpus();
    const titled = [
      ...BEARINGS.map((bearing) => [bearing.policy.id, bearing.policy.title] as const),
      ...CASE_FILE.findings.flatMap((finding) =>
        finding.policies.map((bearing) => [bearing.policy_id, bearing.policy_title] as const),
      ),
    ];

    expect(titled.filter(([id, title]) => bundled.get(id) !== title)).toEqual([]);
  });

  /**
   * `RetrievalProvenance.selected_policy_ids` is what retrieval pulled and `Finding.policies`
   * is what bore on the verdict. The second is a subset of the first on every real review,
   * and the surface prints the difference between the two counts — so a fixture where a
   * policy bore without having been retrieved would print a number that cannot happen.
   */
  it("only let a policy bear on a judgement if retrieval pulled it", () => {
    for (const finding of CASE_FILE.findings) {
      const retrieved = CASE_FILE.retrieval_manifest.find(
        (entry) => entry.candidate_id === finding.candidate.id,
      );
      expect(retrieved).toBeDefined();
      for (const bearing of finding.policies) {
        expect(retrieved?.selected_policy_ids).toContain(bearing.policy_id);
      }
    }
  });
});
