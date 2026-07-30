import { Trash2, X } from "lucide-react";
import { useEffect } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { ErrorPanel, Loading } from "./components";
import type { ArchitectureCase, CaseUpdate, Clarification } from "./types";

/* The surface a case is written on, shared by the form and the YAML editor: one padded grid
   inside the layer that floats it, with a head that puts the way out beside the title. */
export const caseSurface = "grid gap-3.5 p-[var(--card-pad)]";
export const caseHead = "flex items-center justify-between gap-3";
/* One group of the form: a well with its own rule, and a small-caps label saying what this
   group is for. */
const group = "grid gap-4 rounded-panel [border:var(--sheet-border)] bg-sunken p-[var(--card-pad)]";
const groupTitle = "m-0 text-micro font-[650] tracking-[.08em] uppercase text-ink-3";
const example =
  "grid grid-cols-[auto_1fr] items-baseline gap-2 text-ui leading-[1.5] text-ink-2 max-[720px]:grid-cols-[1fr] max-[720px]:gap-0.5";
/* What commits, and the sentence saying what committing does. */
export const caseActions = "flex items-center gap-3";
export const caseNote = "m-0 text-ui leading-[1.5] text-ink-2";

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
  /**
   * The questions a review asked and the answers given to them, as pairs.
   *
   * The one field here that is not a textarea of lines, because a pair cannot be a line: half
   * of it is the advisor's words and half of it is the reader's, and a format that ran them
   * together would lose which was which. Kept as objects so the question travels untouched —
   * the form offers no way to edit it, and a case that claimed a review asked something it
   * never did would be a fabricated record of an exchange.
   */
  clarifications: Clarification[];
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
  clarifications: [],
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
    clarifications: (snapshot.clarifications || []).map((item) => ({ ...item })),
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
    // Answers trimmed, and a pair whose answer has been emptied is dropped rather than sent.
    // Blank is how someone deletes one by clearing the box instead of pressing the button, and
    // the server would refuse it anyway: a question sitting in the case with nothing answering
    // it reads to every later pass as a statement about this project.
    clarifications: values.clarifications
      .map((item) => ({ ...item, answer: item.answer.trim() }))
      .filter((item) => item.answer),
  };
}

/* An answer here is prose, not a value: these are set at the body size and given the wider
   gutter a sentence needs, and the focus mark is tightened by a pixel because the box is
   already inside a bordered group. One string, because eleven fields have to look alike.

   The field keeps the vendored 34px: the line is taller than that and an input centres it,
   which is what these have always looked like. Only a textarea's height comes from its own
   content, so only a textarea takes the vertical padding — and `rows` decides how tall it
   opens, which is why the vendored floor comes off. */
export const caseField =
  "px-3 text-body leading-[1.6] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary";
const caseArea = cn(caseField, "min-h-0");

/* Both examples wear the verdict families, which is the whole trick: the answer that decides
   something is field green and the one that decides nothing is revision magenta, so a reader
   recognises them from the report before they have written a word.

   Deliberately not a `Badge`: a chip in this design is sentence case, because a chip states a
   fact about the thing beside it and shouting it would give a piece of metadata more voice
   than what it is attached to. These two are the opposite — a legend over a pair of examples,
   read before either example is — so they keep the shout. */
const tag =
  "rounded-pill border px-2 py-px text-micro font-bold tracking-[.05em] uppercase whitespace-nowrap max-[720px]:justify-self-start";
const tagGood = cn(tag, "border-cleared-rule bg-cleared-soft text-cleared");
const tagBad = cn(tag, "border-material-rule bg-material-soft text-material");

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
    <label className="grid gap-1">
      <span className="text-body font-[650]">{label}</span>
      {hint ? (
        <span className="max-w-[86ch] text-ui leading-[1.5] text-ink-2">{hint}</span>
      ) : null}
      {good && bad ? (
        <span className="mt-0.5 mb-[3px] grid max-w-[92ch] gap-1">
          <span data-slot="case-example" data-tone="good" className={example}>
            <span className={tagGood}>Decides something</span>
            {good}
          </span>
          <span data-slot="case-example" data-tone="bad" className={example}>
            <span className={tagBad}>Decides nothing</span>
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
  onDirtyChange,
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
  /**
   * Told whenever this form starts or stops holding writing that is not in a revision yet.
   *
   * The form is the only thing that can answer that question — what counts as written is what
   * differs from the case it opened on, which is `useForm`'s own comparison against the
   * defaults it took at mount, and nothing outside can see it. What the answer is *for* is the
   * layer this form floats in: it decides whether a dismissal is a decision to throw prose
   * away, and it cannot decide that from the outside either.
   */
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const form = useForm<CaseFormValues>({ defaultValues: caseFormValues(initial) });
  /* Removal is what a field array is needed for here. The answers themselves are ordinary
     registered inputs; taking a pair out of the case is not, and a list rebuilt on every
     keystroke would take the cursor with it. */
  const clarifications = useFieldArray({ control: form.control, name: "clarifications" });

  /* Read here rather than inside a handler, because reading it in the body is what subscribes
     this component to it: `formState` is a proxy, and a field it is never asked for during a
     render is a field it never re-renders for. */
  const dirty = form.formState.isDirty;
  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);

  return (
    <section className={caseSurface} aria-label={heading}>
      <div className={caseHead}>
        <h3 className="m-0 text-sub">{heading}</h3>
        <Button
          type="button"
          size="icon"
          onClick={onClose}
          aria-label={`Close ${heading.toLowerCase()}`}
        >
          <X size={16} aria-hidden />
        </Button>
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
        <form
          data-slot="case-form"
          className="grid gap-4"
          onSubmit={form.handleSubmit(onSubmit)}
        >
          <div className={group}>
            <h4 className={groupTitle}>The decision</h4>
            {/* These three are the only fields the domain requires, so the form asks for them
                before submitting. Everything else the server judges — including these, which
                it still validates. */}
            <Field label="Name for this case" hint="Short, so you can find it again.">
              <Input className={caseField} {...form.register("title", { required: true })} />
            </Field>
            <Field label="What decision are you facing?">
              <Textarea className={caseArea} rows={3} {...form.register("problem_statement")} />
            </Field>
            <Field label="What would a good answer give you?">
              <Textarea className={caseArea} rows={2} {...form.register("desired_outcome")} />
            </Field>
          </div>

          {/* The three fields that decide verdicts are marked as such: a form of equal
              boxes says every answer matters equally, and here they do not. */}
          <div
            data-slot="case-decisive"
            className={cn(group, "border-accent-rule bg-accent-soft")}
          >
            <h4 className={groupTitle}>What decides the verdict</h4>
            <p className="m-0 -mt-1 max-w-[86ch] text-ui leading-[1.6] text-ink-2">
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
              <Textarea className={caseArea} rows={3} {...form.register("expected_future_changes")} />
            </Field>
            <Field
              label="What have you decided against?"
              hint="One per line. A boundary that absorbs a non-goal hides nothing."
              good="We will not run on anything but Postgres; the ops team supports one database and that is settled."
              bad="Keep it simple and avoid over-engineering."
            >
              <Textarea className={caseArea} rows={3} {...form.register("non_goals")} />
            </Field>
            <Field
              label="What is settled, and why?"
              hint="One per line. Anything fixed by an external contract cannot vary, so no boundary can absorb it."
              good="The payroll export format is fixed by the tax authority and changes only by legislation."
              bad="The current code is a bit messy in places."
            >
              <Textarea className={caseArea} rows={4} {...form.register("confirmed_facts")} />
            </Field>
          </div>

          {/* Only where a review has actually asked something. An empty section here would
              invite someone to write their own questions, and these are not theirs to write:
              a pair exists because a verdict turned on something the case did not say. */}
          {clarifications.fields.length > 0 ? (
            <div data-slot="case-clarifications" className={group}>
              <h4 className={groupTitle}>What a review asked, and what you answered</h4>
              <p className="m-0 -mt-1 max-w-[86ch] text-ui leading-[1.6] text-ink-2">
                These came from answering a review's questions. The question is the review's
                wording and is kept as it was asked; the answer is yours, so change it if it no
                longer says what you meant, or remove the pair if it should not be weighed at
                all.
              </p>
              {clarifications.fields.map((entry, index) => (
                <div
                  key={entry.id}
                  data-slot="clarification"
                  className="grid grid-cols-[1fr_auto] items-start gap-x-3 gap-y-1"
                >
                  {/* Muted and attributed, because the whole point of keeping the pair is that
                      a reader can tell which half they wrote. There is no box around it: it is
                      not theirs to edit. */}
                  <span className="text-ui leading-[1.5] text-ink-3">
                    Asked: {entry.question}
                  </span>
                  <Button
                    type="button"
                    size="icon"
                    className="row-span-2"
                    onClick={() => clarifications.remove(index)}
                    aria-label={`Remove the answer to "${entry.question}"`}
                  >
                    <Trash2 size={15} aria-hidden />
                  </Button>
                  <Textarea
                    className={cn(caseArea, "col-start-1")}
                    rows={2}
                    aria-label={`Your answer to "${entry.question}"`}
                    {...form.register(`clarifications.${index}.answer` as const)}
                  />
                  {/* The force this answer carries, shown rather than offered. It was read
                      from the review's own report when the answer was recorded, and letting it
                      be changed here would let a case decide how its own evidence is weighed. */}
                  <span className="col-start-1 text-meta text-ink-3">
                    Weighed as <code className="text-meta">{entry.bears_on}</code>
                  </span>
                </div>
              ))}
            </div>
          ) : null}

          {/* Collapsed by default: real context, but a form that opens as eleven empty boxes
              reads as work rather than as questions. */}
          <details className="rounded-panel border border-rule bg-surface px-4 py-3 open:[&>summary]:mb-4 [&>label+label]:mt-3">
            <summary className="cursor-pointer text-body font-[650] text-ink-2">
              More context
            </summary>
            <Field
              label="Technical constraints"
              hint="One per line. Something a design could actually violate."
              good="Python 3.12 with no async runtime, deployed as one container with no outbound network."
              bad="Must be scalable and maintainable."
            >
              <Textarea className={caseArea} rows={3} {...form.register("technical_constraints")} />
            </Field>
            <Field
              label="Organisational constraints"
              hint="One per line. Who maintains this, and with how much time."
              good="One maintainer, roughly four hours a week, and nobody else has read this code."
              bad="The team is quite small."
            >
              <Textarea className={caseArea} rows={2} {...form.register("organisational_constraints")} />
            </Field>
            <Field
              label="Qualities that matter"
              hint="One per line. Ranked against each other, because everything cannot come first."
              good="A failed import must never lose a row; correctness matters more than throughput here."
              bad="High performance, security and reliability."
            >
              <Textarea className={caseArea} rows={2} {...form.register("quality_attributes")} />
            </Field>
            <Field
              label="What it has to do"
              hint="One per line."
              good="Reconcile last night's bank export against yesterday's ledger and report every mismatch."
              bad="Handle the data properly."
            >
              <Textarea className={caseArea} rows={2} {...form.register("functional_requirements")} />
            </Field>
            <Field
              label="Who uses it, and how"
              hint="One per line."
              good="Two finance analysts run the reconciliation each morning and work through the failures by hand."
              bad="Users use the system."
            >
              <Textarea className={caseArea} rows={2} {...form.register("actors_and_workflows")} />
            </Field>
          </details>

          <div className={caseActions}>
            <Button type="submit" variant="primary" disabled={pending}>
              {pending ? pendingLabel : submitLabel}
            </Button>
            <p className={caseNote}>
              Case revisions are immutable: this writes a new one rather than changing what an
              earlier review was judged against.
            </p>
          </div>
        </form>
      )}
    </section>
  );
}
