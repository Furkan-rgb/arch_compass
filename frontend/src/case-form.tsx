import { X } from "lucide-react";
import { useForm } from "react-hook-form";

import { ErrorPanel, Loading } from "./components";
import type { ArchitectureCase, CaseUpdate } from "./types";

/**
 * A case as a form, field by field.
 *
 * Every list field is a textarea, one item per line, rather than a row of inputs with add
 * and remove buttons. The entries are sentences a person writes, edits and pastes in
 * batches, and a widget that makes each one a separate control makes all three harder for
 * the sake of chrome nobody asked for.
 *
 * The form covers the fields that decide verdicts and leaves the rest to the YAML editor.
 * Each label is the question the field answers, and the hint says why the answer matters,
 * because the reason is the part a person cannot guess.
 */
export interface CaseFormValues {
  title: string;
  problem_statement: string;
  desired_outcome: string;
  expected_future_changes: string;
  non_goals: string;
  confirmed_facts: string;
  technical_constraints: string;
  organisational_constraints: string;
  quality_attributes: string;
  functional_requirements: string;
  actors_and_workflows: string;
}

const EMPTY: CaseFormValues = {
  title: "",
  problem_statement: "",
  desired_outcome: "",
  expected_future_changes: "",
  non_goals: "",
  confirmed_facts: "",
  technical_constraints: "",
  organisational_constraints: "",
  quality_attributes: "",
  functional_requirements: "",
  actors_and_workflows: "",
};

function lines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

/** A stored case as form values: lists become one item per line, in their stored order. */
export function caseFormValues(snapshot: ArchitectureCase | undefined): CaseFormValues {
  if (!snapshot) return EMPTY;
  return {
    title: snapshot.title || "",
    problem_statement: snapshot.problem_statement || "",
    desired_outcome: snapshot.desired_outcome || "",
    expected_future_changes: (snapshot.expected_future_changes || []).join("\n"),
    non_goals: (snapshot.non_goals || []).join("\n"),
    confirmed_facts: (snapshot.confirmed_facts || [])
      .map((statement) => statement.text)
      .join("\n"),
    technical_constraints: (snapshot.technical_constraints || []).join("\n"),
    organisational_constraints: (snapshot.organisational_constraints || []).join("\n"),
    quality_attributes: (snapshot.quality_attributes || []).join("\n"),
    functional_requirements: (snapshot.functional_requirements || []).join("\n"),
    actors_and_workflows: (snapshot.actors_and_workflows || []).join("\n"),
  };
}

/**
 * Form values as the payload both case routes accept.
 *
 * One shape for creating and for revising: every key is present, so a field cleared in the
 * form is cleared in the next revision rather than silently keeping its old value. Statement
 * kinds are set here because they are fixed by which list the statement is in — asking a
 * person to type `kind: fact` next to a fact they just wrote is asking them to restate the
 * form's own structure.
 */
export function casePayload(values: CaseFormValues): ArchitectureCase & CaseUpdate {
  return {
    title: values.title.trim(),
    problem_statement: values.problem_statement.trim(),
    desired_outcome: values.desired_outcome.trim(),
    expected_future_changes: lines(values.expected_future_changes),
    non_goals: lines(values.non_goals),
    confirmed_facts: lines(values.confirmed_facts).map((text) => ({
      text,
      kind: "fact" as const,
    })),
    technical_constraints: lines(values.technical_constraints),
    organisational_constraints: lines(values.organisational_constraints),
    quality_attributes: lines(values.quality_attributes),
    functional_requirements: lines(values.functional_requirements),
    actors_and_workflows: lines(values.actors_and_workflows),
  };
}

/**
 * One field, with the question it answers and — where an answer can miss — a pair of
 * examples.
 *
 * Both examples, never only the good one. Every field here has a plausible-looking answer
 * that decides nothing: "we might need X one day", "must be scalable", "the team is small".
 * A reader shown only a good example reads it as a formatting convention and writes the
 * empty answer anyway; shown the pair, they can see which of the two theirs resembles.
 */
function Field({
  label,
  hint,
  good,
  bad,
  children,
}: {
  label: string;
  hint?: string;
  good?: string;
  bad?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="case-field">
      <span className="case-field__label">{label}</span>
      {hint ? <span className="case-field__hint">{hint}</span> : null}
      {good && bad ? (
        <span className="case-field__examples">
          <span className="case-field__example case-field__example--good">
            <span className="case-field__tag">Decides something</span>
            {good}
          </span>
          <span className="case-field__example case-field__example--bad">
            <span className="case-field__tag">Decides nothing</span>
            {bad}
          </span>
        </span>
      ) : null}
      {children}
    </label>
  );
}

export function CaseForm({
  heading,
  initial,
  submitLabel,
  pendingLabel,
  pending,
  loading,
  error,
  note,
  onSubmit,
  onClose,
}: {
  heading: string;
  initial: ArchitectureCase | undefined;
  submitLabel: string;
  pendingLabel: string;
  pending: boolean;
  loading?: boolean;
  error: unknown;
  note?: React.ReactNode;
  onSubmit: (values: CaseFormValues) => void;
  onClose: () => void;
}) {
  const form = useForm<CaseFormValues>({ defaultValues: caseFormValues(initial) });

  return (
    <section className="case-editor" aria-label={heading}>
      <div className="case-editor__head">
        <h3>{heading}</h3>
        <button
          type="button"
          className="icon-button"
          onClick={onClose}
          aria-label={`Close ${heading.toLowerCase()}`}
        >
          <X size={16} aria-hidden />
        </button>
      </div>
      {note}
      {error ? <ErrorPanel error={error} /> : null}

      {/* Nothing to fill in until there is something to fill it with. `useForm` takes
          its defaults once, at mount, so a form rendered before the case arrives holds
          empty fields for good — and submitting it would write a revision with every
          field cleared, because the payload always carries every key. A caller that keys
          this on the loaded revision re-mounts it correctly; one that does not would
          erase a case in silence, so the form is not offered until it can be right. */}
      {loading ? (
        <Loading label="Reading the case…" />
      ) : (
        <form className="case-form" onSubmit={form.handleSubmit(onSubmit)}>
          <div className="case-form__group">
            <h4>The decision</h4>
            {/* These three are the only fields the domain requires, so the form asks for them
                before submitting. Everything else the server judges — including these, which
                it still validates. */}
            <Field label="Name for this case" hint="Short, so you can find it again.">
              <input {...form.register("title", { required: true })} />
            </Field>
            <Field label="What decision are you facing?">
              <textarea rows={3} {...form.register("problem_statement", { required: true })} />
            </Field>
            <Field label="What would a good answer give you?">
              <textarea rows={2} {...form.register("desired_outcome", { required: true })} />
            </Field>
          </div>

          <div className="case-form__group case-form__group--decisive">
            <h4>What decides the verdict</h4>
            <p className="case-form__why">
              A boundary earns its place by absorbing a change that is actually coming. These
              three fields are where that is settled, and a review with them empty can only
              judge structure.
            </p>
            <Field
              label="What changes are actually coming?"
              hint="One per line. A boundary earns its place by absorbing one of these."
              good="Billing moves to a second provider in Q4 — the contract is signed and the migration is scheduled."
              bad="We might need to support other providers one day."
            >
              <textarea rows={3} {...form.register("expected_future_changes")} />
            </Field>
            <Field
              label="What have you decided against?"
              hint="One per line. A boundary that absorbs a non-goal hides nothing."
              good="We will not run on anything but Postgres; the ops team supports one database and that is settled."
              bad="Keep it simple and avoid over-engineering."
            >
              <textarea rows={3} {...form.register("non_goals")} />
            </Field>
            <Field
              label="What is settled, and why?"
              hint="One per line. Anything fixed by an external contract cannot vary, so no boundary can absorb it."
              good="The payroll export format is fixed by the tax authority and changes only by legislation."
              bad="The current code is a bit messy in places."
            >
              <textarea rows={4} {...form.register("confirmed_facts")} />
            </Field>
          </div>

          {/* Collapsed by default: real context, but a form that opens as eleven empty boxes
              reads as work rather than as questions. */}
          <details className="case-form__more">
            <summary>More context</summary>
            <Field
              label="Technical constraints"
              hint="One per line. Something a design could actually violate."
              good="Python 3.12 with no async runtime, deployed as one container with no outbound network."
              bad="Must be scalable and maintainable."
            >
              <textarea rows={3} {...form.register("technical_constraints")} />
            </Field>
            <Field
              label="Organisational constraints"
              hint="One per line. Who maintains this, and with how much time."
              good="One maintainer, roughly four hours a week, and nobody else has read this code."
              bad="The team is quite small."
            >
              <textarea rows={2} {...form.register("organisational_constraints")} />
            </Field>
            <Field
              label="Qualities that matter"
              hint="One per line. Ranked against each other, because everything cannot come first."
              good="A failed import must never lose a row; correctness matters more than throughput here."
              bad="High performance, security and reliability."
            >
              <textarea rows={2} {...form.register("quality_attributes")} />
            </Field>
            <Field
              label="What it has to do"
              hint="One per line."
              good="Reconcile last night's bank export against yesterday's ledger and report every mismatch."
              bad="Handle the data properly."
            >
              <textarea rows={2} {...form.register("functional_requirements")} />
            </Field>
            <Field
              label="Who uses it, and how"
              hint="One per line."
              good="Two finance analysts run the reconciliation each morning and work through the failures by hand."
              bad="Users use the system."
            >
              <textarea rows={2} {...form.register("actors_and_workflows")} />
            </Field>
          </details>

          <div className="case-editor__actions">
            <button type="submit" className="button button--primary" disabled={pending}>
              {pending ? pendingLabel : submitLabel}
            </button>
            <p>
              Case revisions are immutable: this writes a new one rather than changing what an
              earlier review was judged against.
            </p>
          </div>
        </form>
      )}
    </section>
  );
}
