import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

import { ErrorPanel } from "./components";
import type { Policy, PolicyDraft, PolicyStrength } from "./types";

/**
 * The nine headings every policy in this corpus has, as an empty frame to write into.
 *
 * The form asks for a body rather than for nine boxes. These sections are what a policy is
 * — the rule, the signals that it is being broken, the cases where it does not apply — and
 * a field per heading would turn writing one into filling in a survey, with the prose that
 * runs across two sections cut in half to fit. The parser requires all nine and requires
 * each to have something under it, so the skeleton is the contract stated as a starting
 * point instead of as a rejection.
 */
export const POLICY_BODY_SKELETON = [
  "Intent",
  "Guidance",
  "Signals",
  "Diagnostic questions",
  "Likely consequences",
  "Exceptions",
  "Positive example",
  "Counterexample",
  "Related policies",
]
  .map((heading) => `## ${heading}\n\n`)
  .join("");

const STRENGTHS: PolicyStrength[] = ["guidance", "preferred", "required"];

export interface PolicyFormValues {
  title: string;
  description: string;
  /* Comma-separated, because a tag is a word. The case form gives its lists a line each,
     which is right for entries that are sentences and wrong for a row of five nouns. */
  tags: string;
  strength: PolicyStrength;
  body: string;
}

/** A stored policy as form values, or an empty policy framed by the section skeleton. */
export function policyFormValues(policy?: Policy | null): PolicyFormValues {
  if (!policy) {
    return {
      title: "",
      description: "",
      tags: "",
      strength: "guidance",
      body: POLICY_BODY_SKELETON,
    };
  }
  return {
    title: policy.title,
    description: policy.description || "",
    tags: policy.tags.join(", "),
    strength: policy.strength as PolicyStrength,
    body: policy.body,
  };
}

/**
 * Form values as the payload both authoring routes accept.
 *
 * No id: the server derives it from the title, so there is nothing here that could file a
 * policy under a name its title does not say. No scope either — anything written here is
 * general, and the scoped kinds are declared by where their file lives.
 */
export function policyDraft(values: PolicyFormValues): PolicyDraft {
  return {
    title: values.title.trim(),
    description: values.description.trim(),
    body: values.body.trim(),
    tags: values.tags
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean),
    strength: values.strength,
  };
}

/* The same measurements the case form is written on: one padded grid, groups sunk into
   wells, and the question a field answers as its label. Two forms that ask a person to write
   the material this product reasons over should not look like two products. */
const field =
  "px-3 text-body leading-[1.6] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary";
const area = cn(field, "min-h-0");
const group =
  "grid gap-4 rounded-panel [border:var(--sheet-border)] bg-sunken p-[var(--card-pad)]";
const groupTitle = "m-0 text-micro font-[650] tracking-[.08em] uppercase text-ink-3";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="grid gap-1">
      <span className="text-body font-[650]">{label}</span>
      {hint ? (
        <span className="max-w-[86ch] text-ui leading-[1.5] text-ink-2">{hint}</span>
      ) : null}
      {children}
    </label>
  );
}

/**
 * A policy as a form: what it says, how hard it binds, and the body it is judged from.
 *
 * The one field with real weight is the body, and it opens holding the corpus's own section
 * headings. Everything above it is the front matter a reader meets before opening the
 * policy — the title a review cites it by, the précis the catalog row prints, the tags it is
 * found under.
 */
export function PolicyForm({
  heading,
  initial,
  submitLabel,
  pendingLabel,
  pending,
  error,
  note,
  onSubmit,
}: {
  heading: string;
  /** The policy being rewritten, or nothing when this is a new one. */
  initial?: Policy | null;
  submitLabel: string;
  pendingLabel: string;
  pending: boolean;
  error: unknown;
  note?: React.ReactNode;
  onSubmit: (draft: PolicyDraft) => void;
}) {
  const form = useForm<PolicyFormValues>({ defaultValues: policyFormValues(initial) });
  const strength = form.watch("strength");

  return (
    <form
      data-slot="policy-form"
      className="grid gap-4"
      aria-label={heading}
      onSubmit={form.handleSubmit((values) => onSubmit(policyDraft(values)))}
    >
      {error ? <ErrorPanel error={error} /> : null}

      <div className={group}>
        <h4 className={groupTitle}>What this policy is</h4>
        <Field
          label="What is the rule?"
          hint="Stated as the thing to do, the way the corpus states its own. The id a review will cite is made from this, and it does not change when the wording does."
        >
          <Input
            className={field}
            autoFocus
            {...form.register("title", { required: true })}
          />
        </Field>
        <Field
          label="The précis"
          hint="Two or three sentences, shown in the catalog before anyone opens the policy. Short by design — the thoroughness belongs in the body."
        >
          <Textarea
            className={area}
            rows={3}
            {...form.register("description", { required: true })}
          />
        </Field>
        <Field label="Tags" hint="Separated by commas. A word or two each.">
          <Input className={field} placeholder="layering, dependencies" {...form.register("tags")} />
        </Field>
        {/* Not a `Field`: a label wrapping a row of buttons announces itself once and names
            none of them, so the group is labelled by the text beside it instead. */}
        <div className="grid gap-1">
          <span id="policy-strength-label" className="text-body font-[650]">
            How hard does it bind?
          </span>
          <span className="max-w-[86ch] text-ui leading-[1.5] text-ink-2">
            Guidance is weighed, preferred is expected, required is a rule a verdict may not
            trade away.
          </span>
          <ToggleGroup
            type="single"
            className="mt-0.5 w-fit"
            value={strength}
            aria-labelledby="policy-strength-label"
            // A group in single mode clears itself when the current item is pressed again,
            // and a policy always binds somehow — so the empty value is the one refusal.
            onValueChange={(value) => {
              if (value) form.setValue("strength", value as PolicyStrength);
            }}
          >
            {STRENGTHS.map((value) => (
              <ToggleGroupItem key={value} value={value}>
                {value}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      </div>

      <div className={group}>
        <h4 className={groupTitle}>The policy itself</h4>
        <Field
          label="The nine sections"
          hint="Every heading needs something under it. The corpus is presented whole to each boundary judged, so a heading with nothing beneath it is a section the model reads as saying nothing."
        >
          <Textarea
            className={cn(area, "font-mono text-meta")}
            rows={22}
            spellCheck
            {...form.register("body", { required: true })}
          />
        </Field>
      </div>

      <div className="flex items-center gap-3">
        <Button type="submit" variant="primary" disabled={pending}>
          {pending ? pendingLabel : submitLabel}
        </Button>
        {note ? <p className="m-0 text-ui leading-[1.5] text-ink-2">{note}</p> : null}
      </div>
    </form>
  );
}
