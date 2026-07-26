import { dump, load } from "js-yaml";
import { X } from "lucide-react";
import { useState, type ReactNode } from "react";

import { ErrorPanel, Loading } from "./components";
import type { ArchitectureCase } from "./types";

/**
 * Authoring a case, as YAML.
 *
 * YAML first because the fields that decide verdicts — `expected_future_changes`,
 * `non_goals`, `confirmed_facts` — are prose with structure, and a form flattens exactly
 * those. The editor is a client of `POST /api/cases/import-yaml`, which the CLI already
 * uses, so the browser and the terminal author the same thing.
 *
 * Only syntax is checked here. What a case must contain is the domain's rule, and a second
 * copy of it in the browser would drift from the first (master plan §12.0: the application
 * decides, and here the server is the application).
 */
export const CASE_SKELETON = `# An ArchitectureCase says what this software has to do, so that a boundary can be
# judged against something rather than against taste.
#
# Required: title, problem_statement, desired_outcome. Everything else is optional,
# but three fields decide most verdicts:
#
#   expected_future_changes  A boundary earns its place by absorbing a change that is
#                            actually coming. "We might need X one day" is not one.
#   non_goals                Variation you have decided against. A boundary that
#                            absorbs a non-goal is indirection that hides nothing.
#   confirmed_facts          What is settled, and why. Anything fixed by an external
#                            contract cannot vary, so no boundary can absorb it.

title:
problem_statement: >-

desired_outcome: >-


# Delete any of the following you have nothing to say about. An empty list is fine;
# a guessed entry is not — an invented future change produces a justified boundary
# that nothing justifies.

actors_and_workflows: []
functional_requirements: []
quality_attributes: []
technical_constraints: []
organisational_constraints: []

expected_future_changes: []
non_goals: []

confirmed_facts:
  - text: >-
      Something that is settled, in your words.
    kind: fact          # every entry in this list must be kind: fact

# Optional. The repository rail can point at a path instead; naming it here fills
# that rail when the path is already indexed.
# repository:
#   root_path: /absolute/path/to/python-project
`;

/** Identity and bookkeeping ArchCompass owns, which nobody authors. */
const GENERATED_KEYS = new Set([
  "schema_version",
  "case_id",
  "revision",
  "created_at",
  "updated_at",
]);

function authoredFields(value: object): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(value).filter(
      ([key, item]) => key !== "id" && item !== null && item !== undefined,
    ),
  );
}

/**
 * A stored case as its author would write it: generated identity removed, empty fields
 * dropped, statement IDs left out. What comes back is YAML that can be pasted straight
 * into the editor, so reading a case and writing one are the same format.
 */
export function caseToYaml(snapshot: ArchitectureCase): string {
  const authored: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(snapshot)) {
    if (GENERATED_KEYS.has(key) || value === null || value === undefined) continue;
    if (Array.isArray(value)) {
      if (!value.length) continue;
      authored[key] = value.map((item) =>
        item && typeof item === "object" ? authoredFields(item) : item,
      );
      continue;
    }
    if (typeof value === "object") {
      const nested = authoredFields(value);
      if (Object.keys(nested).length) authored[key] = nested;
      continue;
    }
    authored[key] = value;
  }
  return dump(authored, { lineWidth: 88, noRefs: true });
}

/** The one thing the browser can judge alone: whether this is YAML at all. */
export function checkYamlSyntax(source: string): string | null {
  try {
    load(source);
    return null;
  } catch (error) {
    return error instanceof Error ? error.message : "This is not valid YAML.";
  }
}

/**
 * The editing surface itself, shared by writing a case and revising one.
 *
 * `initial` is read once, when the form mounts, so a caller that loads its document
 * asynchronously mounts this after the document arrives rather than fighting a controlled
 * value that changes underneath the person typing into it.
 */
function YamlForm({
  initial,
  submitLabel,
  pendingLabel,
  pending,
  onSubmit,
  children,
}: {
  initial: string;
  submitLabel: string;
  pendingLabel: string;
  pending: boolean;
  onSubmit: (source: string) => void;
  children: ReactNode;
}) {
  const [source, setSource] = useState(initial);
  const [syntax, setSyntax] = useState<string | null>(null);

  return (
    <form
      className="case-editor__form"
      onSubmit={(event) => {
        event.preventDefault();
        const problem = checkYamlSyntax(source);
        setSyntax(problem);
        if (!problem) onSubmit(source);
      }}
    >
      <textarea
        className="case-editor__source"
        value={source}
        spellCheck={false}
        aria-label="Case YAML"
        onChange={(event) => setSource(event.target.value)}
      />
      {syntax ? (
        <p className="case-editor__problem" role="alert">
          <strong>That is not valid YAML.</strong> {syntax}
        </p>
      ) : null}
      <div className="case-editor__actions">
        <button type="submit" className="button button--primary" disabled={pending}>
          {pending ? pendingLabel : submitLabel}
        </button>
        {children}
      </div>
    </form>
  );
}

export function CaseEditor({
  onCreate,
  onClose,
  pending,
  error,
}: {
  onCreate: (source: string) => void;
  onClose: () => void;
  pending: boolean;
  error: unknown;
}) {
  return (
    <section className="case-editor" aria-label="Write a case">
      <div className="case-editor__head">
        <h3>Write a case</h3>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close the editor">
          <X size={16} aria-hidden />
        </button>
      </div>
      {/* The server's own message, verbatim: it names the field and what it needed, and
          paraphrasing it here would tell the user less than the validator knows. */}
      {error ? <ErrorPanel error={error} /> : null}
      <YamlForm
        initial={CASE_SKELETON}
        submitLabel="Create the case"
        pendingLabel="Creating…"
        pending={pending}
        onSubmit={onCreate}
      >
        <p>
          Created as revision 1, then selected in the case rail. Revisions are immutable: a
          later change adds one rather than editing this one.
        </p>
      </YamlForm>
    </section>
  );
}

export function CaseView({
  snapshot,
  loading,
  error,
  onClose,
}: {
  snapshot: ArchitectureCase | undefined;
  loading: boolean;
  error: unknown;
  onClose: () => void;
}) {
  return (
    <div className="case-editor">
      <div className="case-editor__head">
        <h3>{snapshot?.title || "Case"}</h3>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close the case">
          <X size={16} aria-hidden />
        </button>
      </div>
      {loading ? <Loading label="Reading the case…" /> : null}
      {error ? <ErrorPanel error={error} /> : null}
      {snapshot ? (
        <pre className="case-editor__source case-editor__source--read">
          {caseToYaml(snapshot)}
        </pre>
      ) : null}
      <p className="case-editor__note">
        Revision {snapshot?.revision ?? "?"}, exactly as a review would pin it.
      </p>
    </div>
  );
}
