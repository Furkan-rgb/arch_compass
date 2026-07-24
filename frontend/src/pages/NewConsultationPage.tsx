import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { load as loadYaml } from "js-yaml";
import {
  ArrowLeft,
  ArrowRight,
  BookOpenText,
  Boxes,
  Check,
  FileUp,
  Leaf,
  Play,
} from "lucide-react";
import { useState } from "react";
import { useForm, type UseFormRegisterReturn } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { api } from "../api";
import { Badge, ErrorPanel, PageHeader } from "../components";
import type { ArchitectureCaseInput } from "../types";

export const caseFormSchema = z.object({
  title: z.string().min(3, "Give this decision a short title."),
  problem_statement: z.string().min(12, "Describe the architecture problem in a little more detail."),
  desired_outcome: z.string().min(8, "Describe what a sound decision should achieve."),
  actors_and_workflows: z.string(),
  functional_requirements: z.string(),
  quality_attributes: z.string(),
  technical_constraints: z.string(),
  organisational_constraints: z.string(),
  expected_future_changes: z.string(),
  non_goals: z.string(),
  confirmed_facts: z.string(),
});

export type CaseFormValue = z.infer<typeof caseFormSchema>;
type Mode = "greenfield" | "repository";

const defaults: CaseFormValue = {
  title: "",
  problem_statement: "",
  desired_outcome: "",
  actors_and_workflows: "",
  functional_requirements: "",
  quality_attributes: "",
  technical_constraints: "",
  organisational_constraints: "",
  expected_future_changes: "",
  non_goals: "",
  confirmed_facts: "",
};

export const consultationExamples: Array<{
  name: string;
  badge: string;
  value: Partial<CaseFormValue>;
}> = [
  {
    name: "Greenfield audiobook system",
    badge: "Provider boundaries",
    value: {
      title: "Greenfield audiobook system",
      problem_statement:
        "Build an audiobook application using Qwen TTS with voice design, cloning, and built-in voices.",
      desired_outcome:
        "Stable pipeline boundaries that allow credible future providers without a universal plugin platform.",
      actors_and_workflows: "A user ingests a book and resumes long-running narration.",
      functional_requirements:
        "Book ingestion\nText preparation and chunking\nVoice design and cloning\nNarration",
      quality_attributes: "Long-running jobs are resumable",
      technical_constraints: "One local GPU\nQwen is the initial provider",
      expected_future_changes: "Hosted providers may be added later",
      non_goals: "Universal dynamic plugin marketplace",
      confirmed_facts: "Qwen is the initial provider.",
    },
  },
  {
    name: "Brownfield provider leakage",
    badge: "Ownership",
    value: {
      title: "Brownfield provider leakage",
      problem_statement:
        "Qwen built-in voice knowledge appears in frontend, preflight, workflow, and root composition.",
      desired_outcome:
        "Put voice discovery under one clear owner and reduce coordinated provider changes.",
      expected_future_changes: "A second provider may be added.",
      confirmed_facts: "A provider interface exists but does not own voice discovery.",
    },
  },
  {
    name: "Premature abstraction",
    badge: "Keep local",
    value: {
      title: "Premature abstraction",
      problem_statement:
        "A formatter interface, factory, provider registry, and runtime configuration key are proposed to replace one directly called local formatter.",
      desired_outcome:
        "Keep the single behavior local unless credible independent variation makes an abstraction reduce present complexity.",
      confirmed_facts:
        "The repository contains exactly one formatting implementation.\nNo second implementation or runtime selection requirement exists.\nThere is no credible planned variation.",
    },
  },
];

function lines(value: string) {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function toArchitectureCase(
  value: CaseFormValue,
): ArchitectureCaseInput {
  return {
    title: value.title,
    problem_statement: value.problem_statement,
    desired_outcome: value.desired_outcome,
    actors_and_workflows: lines(value.actors_and_workflows),
    functional_requirements: lines(value.functional_requirements),
    quality_attributes: lines(value.quality_attributes),
    technical_constraints: lines(value.technical_constraints),
    organisational_constraints: lines(value.organisational_constraints),
    expected_future_changes: lines(value.expected_future_changes),
    non_goals: lines(value.non_goals),
    confirmed_facts: lines(value.confirmed_facts).map((text) => ({ text, kind: "fact" })),
  };
}

export function fromImportedCase(raw: unknown): CaseFormValue {
  const source = (raw || {}) as Record<string, unknown>;
  const text = (key: string) => (typeof source[key] === "string" ? String(source[key]) : "");
  const list = (key: string) =>
    Array.isArray(source[key])
      ? (source[key] as unknown[])
          .map((item) =>
            typeof item === "object" && item && "text" in item
              ? String((item as { text: unknown }).text)
              : String(item),
          )
          .join("\n")
      : "";
  return {
    title: text("title"),
    problem_statement: text("problem_statement"),
    desired_outcome: text("desired_outcome"),
    actors_and_workflows: list("actors_and_workflows"),
    functional_requirements: list("functional_requirements"),
    quality_attributes: list("quality_attributes"),
    technical_constraints: list("technical_constraints"),
    organisational_constraints: list("organisational_constraints"),
    expected_future_changes: list("expected_future_changes"),
    non_goals: list("non_goals"),
    confirmed_facts: list("confirmed_facts"),
  };
}

export function NewConsultationPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  const [step, setStep] = useState(1);
  const [mode, setMode] = useState<Mode>("repository");
  const [repositoryRoot, setRepositoryRoot] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const form = useForm<CaseFormValue>({
    resolver: zodResolver(caseFormSchema),
    defaultValues: defaults,
  });
  const index = useMutation({
    mutationFn: api.indexRepository,
    onSuccess: (version) => {
      setRepositoryRoot(version.root_path);
      void queryClient.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
  const launch = useMutation({
    mutationFn: async (value: CaseFormValue) => {
      const revision = await api.createCase(toArchitectureCase(value));
      return api.startConsultation(
        revision.case_id,
        mode === "repository" ? repositoryRoot : undefined,
      );
    },
    onSuccess: (job) => navigate(`/runs/${job.run_id}`),
  });

  const selectedIndexed = repositories.data?.some(
    (item) => item.root_path === repositoryRoot,
  );
  const values = form.watch();

  const nextFromContext = async () => {
    if (mode === "repository" && !repositoryRoot.trim()) return;
    if (mode === "repository" && !selectedIndexed) {
      await index.mutateAsync(repositoryRoot.trim());
    }
    setStep(2);
  };

  const importFile = async (file?: File) => {
    if (!file) return;
    try {
      form.reset(fromImportedCase(loadYaml(await file.text())));
      setImportError(null);
      setStep(2);
    } catch (error) {
      setImportError(error instanceof Error ? error.message : "Could not read YAML.");
    }
  };

  return (
    <div className="page page--narrow">
      <PageHeader
        eyebrow="New architecture consultation"
        title="Frame the decision"
        description="A precise case produces a more useful recommendation than a broad request to review everything."
      />
      <ol className="wizard-steps" aria-label="Consultation setup">
        {["Context", "Case", "Review"].map((label, indexValue) => (
          <li key={label} className={step >= indexValue + 1 ? "active" : ""}>
            <span>{step > indexValue + 1 ? <Check size={15} /> : indexValue + 1}</span>
            {label}
          </li>
        ))}
      </ol>

      {(index.error || launch.error) && <ErrorPanel error={index.error || launch.error} />}
      {importError && <div className="notice notice--error">{importError}</div>}

      {step === 1 && (
        <section className="wizard-card">
          <span className="eyebrow">Step 1 · Evidence context</span>
          <h2>What kind of decision is this?</h2>
          <div className="mode-grid">
            <button
              type="button"
              onClick={() => setMode("repository")}
              className={mode === "repository" ? "selected" : ""}
              aria-pressed={mode === "repository"}
            >
              <Boxes size={25} />
              <strong>Existing repository</strong>
              <span>Use a freshness-checked Python atlas as bounded structural evidence.</span>
              {mode === "repository" && <Check size={17} className="mode-check" />}
            </button>
            <button
              type="button"
              onClick={() => setMode("greenfield")}
              className={mode === "greenfield" ? "selected" : ""}
              aria-pressed={mode === "greenfield"}
            >
              <Leaf size={25} />
              <strong>Greenfield</strong>
              <span>Reason from requirements, constraints, facts, and future scenarios.</span>
              {mode === "greenfield" && <Check size={17} className="mode-check" />}
            </button>
          </div>

          {mode === "repository" && (
            <div className="form-section">
              <label className="field">
                <span>Absolute repository path</span>
                <input
                  value={repositoryRoot}
                  onChange={(event) => setRepositoryRoot(event.target.value)}
                  placeholder="/absolute/path/to/python-project"
                  list="indexed-repositories"
                />
                <datalist id="indexed-repositories">
                  {repositories.data?.map((item) => (
                    <option key={item.version_id} value={item.root_path} />
                  ))}
                </datalist>
                <small>
                  {selectedIndexed
                    ? "An indexed atlas is available. Freshness will be checked before use."
                    : "This project will be indexed before the case is created."}
                </small>
              </label>
            </div>
          )}

          <div className="wizard-actions">
            <span />
            <button
              type="button"
              className="button button--primary"
              disabled={
                index.isPending || (mode === "repository" && !repositoryRoot.trim())
              }
              onClick={() => void nextFromContext()}
            >
              {index.isPending ? "Indexing repository…" : "Continue"}
              {!index.isPending && <ArrowRight size={16} />}
            </button>
          </div>
        </section>
      )}

      {step === 2 && (
        <form className="wizard-card" onSubmit={form.handleSubmit(() => setStep(3))}>
          <div className="case-import-row">
            <div>
              <span className="eyebrow">Step 2 · Architecture case</span>
              <h2>Describe the decision in context</h2>
            </div>
            <label className="button button--quiet file-button">
              <FileUp size={16} /> Import YAML
              <input
                type="file"
                accept=".yaml,.yml,text/yaml"
                onChange={(event) => void importFile(event.target.files?.[0])}
              />
            </label>
          </div>

          <div className="example-strip">
            <span>Start from an evaluation case</span>
            {consultationExamples.map((example) => (
              <button
                type="button"
                key={example.name}
                onClick={() => form.reset({ ...defaults, ...example.value })}
              >
                <BookOpenText size={15} />
                <span>{example.name}</span>
                <Badge tone="neutral">{example.badge}</Badge>
              </button>
            ))}
          </div>

          <div className="form-grid">
            <label className="field field--wide">
              <span>Case title *</span>
              <input {...form.register("title")} placeholder="e.g. Provider capability ownership" />
              {form.formState.errors.title && <small className="field-error">{form.formState.errors.title.message}</small>}
            </label>
            <label className="field field--wide">
              <span>Problem statement *</span>
              <textarea rows={4} {...form.register("problem_statement")} />
              {form.formState.errors.problem_statement && <small className="field-error">{form.formState.errors.problem_statement.message}</small>}
            </label>
            <label className="field field--wide">
              <span>Desired outcome *</span>
              <textarea rows={3} {...form.register("desired_outcome")} />
              {form.formState.errors.desired_outcome && <small className="field-error">{form.formState.errors.desired_outcome.message}</small>}
            </label>
          </div>

          <details className="form-details" open>
            <summary>Requirements and constraints</summary>
            <p>Enter one item per line. Empty sections remain explicit and valid.</p>
            <div className="form-grid">
              <TextList label="Actors and workflows" registration={form.register("actors_and_workflows")} />
              <TextList label="Functional requirements" registration={form.register("functional_requirements")} />
              <TextList label="Quality attributes" registration={form.register("quality_attributes")} />
              <TextList label="Technical constraints" registration={form.register("technical_constraints")} />
              <TextList label="Organisational constraints" registration={form.register("organisational_constraints")} />
              <TextList label="Confirmed facts" registration={form.register("confirmed_facts")} />
            </div>
          </details>

          <details className="form-details">
            <summary>Future change and boundaries</summary>
            <div className="form-grid">
              <TextList label="Expected future changes" registration={form.register("expected_future_changes")} />
              <TextList label="Non-goals" registration={form.register("non_goals")} />
            </div>
          </details>

          <div className="wizard-actions">
            <button type="button" className="button button--quiet" onClick={() => setStep(1)}>
              <ArrowLeft size={16} /> Back
            </button>
            <button type="submit" className="button button--primary">
              Review case <ArrowRight size={16} />
            </button>
          </div>
        </form>
      )}

      {step === 3 && (
        <section className="wizard-card">
          <span className="eyebrow">Step 3 · Review and run</span>
          <h2>{values.title}</h2>
          <p className="review-problem">{values.problem_statement}</p>
          <div className="review-context">
            <div>
              <span>Evidence mode</span>
              <strong>{mode === "repository" ? "Repository atlas + case context" : "Greenfield case context"}</strong>
              {mode === "repository" && <code>{repositoryRoot}</code>}
            </div>
            <div>
              <span>Desired outcome</span>
              <strong>{values.desired_outcome}</strong>
            </div>
            <div>
              <span>Context supplied</span>
              <strong>
                {Object.entries(values)
                  .filter(([key, value]) => !["title", "problem_statement", "desired_outcome"].includes(key) && value.trim())
                  .length} populated sections
              </strong>
            </div>
          </div>
          <div className="notice">
            <strong>Structured transparency</strong>
            <p>
              The run will expose design forces, evidence queries, policy matches, alternatives,
              scenarios, and validation repairs—not hidden chain-of-thought.
            </p>
          </div>
          <div className="wizard-actions">
            <button type="button" className="button button--quiet" onClick={() => setStep(2)}>
              <ArrowLeft size={16} /> Edit case
            </button>
            <button
              type="button"
              className="button button--primary"
              disabled={launch.isPending}
              onClick={() => void form.handleSubmit((value) => launch.mutate(value))()}
            >
              <Play size={16} />
              {launch.isPending ? "Starting…" : "Start consultation"}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

function TextList({
  label,
  registration,
}: {
  label: string;
  registration: UseFormRegisterReturn;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <textarea rows={4} {...registration} placeholder="One item per line" />
    </label>
  );
}
