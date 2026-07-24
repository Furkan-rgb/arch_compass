import { load as loadYaml } from "js-yaml";
import { describe, expect, it } from "vitest";

import {
  caseFormSchema,
  consultationExamples,
  fromImportedCase,
  toArchitectureCase,
} from "./NewConsultationPage";

describe("consultation case preparation", () => {
  it("imports list and statement values from case YAML", () => {
    const imported = fromImportedCase(
      loadYaml(`
title: Provider ownership
problem_statement: Provider knowledge leaks across several application layers.
desired_outcome: Give capability discovery one clear architectural owner.
functional_requirements:
  - Discover available voices
confirmed_facts:
  - text: A provider interface already exists.
    kind: fact
`),
    );

    expect(imported.title).toBe("Provider ownership");
    expect(imported.functional_requirements).toBe("Discover available voices");
    expect(imported.confirmed_facts).toBe("A provider interface already exists.");
  });

  it("normalizes one-item-per-line fields into the case contract", () => {
    const form = {
      ...fromImportedCase(consultationExamples[0].value),
      functional_requirements: "Ingest books\n\nResume narration",
      confirmed_facts: "Qwen is first.\nOne local GPU.",
    };

    const architectureCase = toArchitectureCase(form);

    expect(architectureCase.functional_requirements).toEqual([
      "Ingest books",
      "Resume narration",
    ]);
    expect(architectureCase.confirmed_facts).toEqual([
      { text: "Qwen is first.", kind: "fact" },
      { text: "One local GPU.", kind: "fact" },
    ]);
  });

  it("rejects vague required fields before review", () => {
    const result = caseFormSchema.safeParse({
      ...fromImportedCase({}),
      title: "No",
      problem_statement: "Too short",
      desired_outcome: "Vague",
    });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.title).toBeDefined();
      expect(result.error.flatten().fieldErrors.problem_statement).toBeDefined();
      expect(result.error.flatten().fieldErrors.desired_outcome).toBeDefined();
    }
  });
});
