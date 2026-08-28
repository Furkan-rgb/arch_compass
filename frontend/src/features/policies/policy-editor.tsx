import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, type PolicyDocument, type PolicyDraft } from "../../api";
import { cn } from "../../lib/cn";
import { Button } from "../../ui/button";
import { Field, Input, Select, Textarea } from "../../ui/field";
import { Markdown } from "../../ui/markdown";
import { Label, Panel, PanelBody, PanelFooter, PanelHeader } from "../../ui/panel";
import { ErrorNotice, Spinner } from "../../ui/states";
import { Tabs, TabPanel } from "../../ui/tabs";
import { useToast } from "../../ui/toast";
import { missingSections, policyTemplate, sectionStates } from "./sections";
import { Mark } from "../../ui/mark";

const EMPTY: PolicyDraft = {
  title: "",
  description: "",
  body: policyTemplate(),
  tags: [],
  strength: "guidance",
};

/**
 * What each strength actually does, because it is the largest consequence anything on this
 * form has and the field used to say four words about it.
 *
 * `required` is not emphasis. `policies/retrieval.py` puts a general policy in the mandatory
 * lane when — and only when — its strength is `required`, which means every candidate of
 * every review reads it, unconditionally. The other two reach a judgement only if dense
 * retrieval ranks them against the candidate in front of it. An author choosing between the
 * three was being asked to decide that with "How binding this is" as the whole explanation.
 *
 * The register is the scale's, not the sign's: this says what happens, not that anything is
 * wrong. A required policy is the policy to read first, never an alarm — `lib/format.ts`
 * argues that at length beside the marks, and the sentence has to agree with the glyph.
 *
 * These belong beside the three `STRENGTHS` descriptors in `lib/format.ts`, where
 * `DescriptorBadge` would forward them into every `StrengthBadge`'s `title` for free — that
 * table is the one place that decides what a strength means. They are here because this
 * change does not own that file.
 */
const STRENGTH_REACH: Record<PolicyDraft["strength"], string> = {
  required: "Retrieved for every candidate of every review, whether or not it ranks.",
  preferred: "Retrieved when it ranks against the candidate.",
  guidance: "Retrieved when it ranks against the candidate, and weighed last of the three.",
};

function draftFrom(policy: PolicyDocument | null): PolicyDraft {
  if (!policy) return EMPTY;
  return {
    title: policy.title,
    description: policy.description ?? "",
    body: policy.body,
    tags: policy.tags,
    strength: policy.strength,
  };
}

/**
 * Authoring a workspace policy, with the Markdown shown as it will actually render.
 *
 * The same form edits an existing workspace policy, because writing one and correcting one
 * are the same act — only the request differs.
 *
 * `onDirtyChange` is how the page around this knows not to throw the draft away. Four
 * ordinary gestures used to destroy it without a word — Cancel, the header button, pressing
 * Edit on another policy, and leaving the page — and the experience doc names the rule all
 * four broke: *never navigate away from unsaved input*. The three that are controls are
 * guarded by the page, which owns them; the fourth is guarded here, because `beforeunload`
 * belongs to whoever holds the text.
 */
export function PolicyEditor({
  policy,
  onCancel,
  onSaved,
  onDirtyChange,
}: {
  policy: PolicyDocument | null;
  onCancel: () => void;
  onSaved: () => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const client = useQueryClient();
  const say = useToast().say;
  const [draft, setDraft] = useState<PolicyDraft>(() => draftFrom(policy));
  const [tags, setTags] = useState((policy?.tags ?? []).join(", "));
  const [tab, setTab] = useState("write");

  const payload = (): PolicyDraft => ({
    ...draft,
    title: draft.title.trim(),
    description: draft.description.trim(),
    body: draft.body.trim(),
    tags: tags
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean),
  });

  const started = draftFrom(policy);
  const dirty =
    draft.title !== started.title ||
    draft.description !== started.description ||
    draft.body !== started.body ||
    draft.strength !== started.strength ||
    tags !== (policy?.tags ?? []).join(", ");

  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);

  /**
   * The one way out of this form that no control on the page can intercept.
   *
   * A reload, a typed address, the back gesture — none of them go through Cancel, and a
   * browser only offers to stop them if something asks. `preventDefault` is the whole ask;
   * the wording is the browser's and cannot be set.
   */
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const save = useMutation({
    // The failure is rendered in the footer of this panel, a few centimetres from the button
    // that caused it, so the global toast would be saying it twice in one eyeline.
    meta: { handled: true },
    mutationFn: () =>
      policy ? api.updatePolicy(policy.id, payload()) : api.createPolicy(payload()),
    onSuccess: async (saved) => {
      await client.invalidateQueries({ queryKey: ["policies"] });
      say(`“${saved.title}” is in the corpus the next review reads.`, "Policy saved");
      onSaved();
    },
  });

  const sections = sectionStates(draft.body);
  const outstanding = missingSections(draft.body);

  /**
   * Everything standing between this draft and the corpus, in the order the form asks for it.
   *
   * `incomplete` has four causes and the sentence beside the button reported one of them. Fill
   * in all nine sections and leave the description blank — an easy state, because the
   * description is one line above a box that takes most of the panel — and the footer read
   * *"Written to the workspace as a Markdown file the next review reads."* beside a button
   * that would not press. Nothing anywhere on the form said which field was missing. The
   * sentence and the button now read the same list, so they cannot disagree.
   *
   * The body gets one entry rather than nine when it is empty. An author who has cleared the
   * scaffold does not need to be told which nine headings they no longer have.
   */
  const missing: string[] = [
    draft.title.trim() ? null : "a title",
    draft.description.trim() ? null : "a description",
    ...(draft.body.trim() ? outstanding : ["the body"]),
  ].filter((item): item is string => Boolean(item));
  const incomplete = missing.length > 0;

  /**
   * Which fields the author has left, so a fault is reported where it happened as well as at
   * the button — and not while they are still on their way to filling it in.
   *
   * On blur rather than on the first keystroke anywhere: marking Description invalid the
   * moment somebody types the first letter of the Title is the form arguing with work that is
   * plainly in progress.
   */
  const [left, setLeft] = useState<Record<string, boolean>>({});
  const leaving = (field: string) => () => setLeft((current) => ({ ...current, [field]: true }));

  return (
    <Panel className="animate-expand" tone="marked">
      <PanelHeader
        title={policy ? `Edit “${policy.title}”` : "New workspace policy"}
        description="Durable architectural guidance. Retrieval mechanics stay out of the policy itself."
        actions={
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        }
      />
      <PanelBody className="grid gap-4">
        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_180px]">
          <Field
            label="Title"
            error={left.title && !draft.title.trim() ? "Required" : undefined}
          >
            {(props) => (
              <Input
                {...props}
                // Opening the form used to move no focus at all, so reaching the first field
                // from the keyboard meant tabbing back down the whole page to a panel that
                // had just appeared above it.
                autoFocus
                value={draft.title}
                onBlur={leaving("title")}
                onChange={(event) => setDraft({ ...draft, title: event.target.value })}
                placeholder="Keep domain code framework-free"
              />
            )}
          </Field>
          <Field label="Strength" hint={STRENGTH_REACH[draft.strength]}>
            {(props) => (
              <Select
                {...props}
                value={draft.strength}
                onChange={(event) =>
                  setDraft({ ...draft, strength: event.target.value as PolicyDraft["strength"] })
                }
              >
                <option value="guidance">Guidance</option>
                <option value="preferred">Preferred</option>
                <option value="required">Required</option>
              </Select>
            )}
          </Field>
        </div>

        <Field
          label="Description"
          hint="One sentence on what this policy protects."
          error={left.description && !draft.description.trim() ? "Required" : undefined}
        >
          {(props) => (
            <Input
              {...props}
              value={draft.description}
              onBlur={leaving("description")}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
              placeholder="Preserve a portable domain model"
            />
          )}
        </Field>

        <div>
          <Tabs
            label="Body view"
            variant="solid"
            active={tab}
            onChange={setTab}
            items={[
              { id: "write", label: "Write" },
              { id: "preview", label: "Preview" },
            ]}
            className="mb-2 w-fit"
          />
          <TabPanel id="write" active={tab}>
            <Field label="Policy body" hint="Markdown, including lists, tables and code fences.">
              {(props) => (
                <Textarea
                  {...props}
                  value={draft.body}
                  onChange={(event) => setDraft({ ...draft, body: event.target.value })}
                  className="min-h-56 font-mono text-[13px]"
                  placeholder={"## When this applies\n\nExplain the principle, its applicability, and the trade-off it accepts."}
                />
              )}
            </Field>
          </TabPanel>
          <TabPanel id="preview" active={tab}>
            <div className="min-h-56 rounded-md border border-rule bg-surface p-4">
              {draft.body.trim() ? (
                <Markdown>{draft.body}</Markdown>
              ) : (
                <p className="text-sm text-ink-2">Nothing to preview yet.</p>
              )}
            </div>
          </TabPanel>
        </div>

        <div className="rounded-md border border-rule bg-surface-2 p-3">
          <Label>Required sections</Label>
          <p className="mt-1 text-xs leading-5 text-ink-2">
            The workspace re-reads this policy with the same parser it uses for the bundled
            corpus, which needs all nine sections present and written.
          </p>
          <ul className="mt-2.5 grid gap-2 sm:grid-cols-3">
            {sections.map((section) => (
              <li
                key={section.name}
                // A checklist should point at what is left, not congratulate what is done —
                // and "written" is not a verdict, which is what the green said it was.
                className={cn("text-xs", section.present ? "text-ink-3" : "text-ink")}
              >
                <span className="flex items-center gap-1.5">
                  {/* A step on a scale, not a grade: written and not-yet-written, solid to
                      dashed. Deliberately not a tick — see the class note above. */}
                  <Mark shape={section.present ? "solid" : "dashed"} className="size-[13px]" />
                  <span className={section.present ? undefined : "font-medium"}>
                    {section.name}
                  </span>
                  <span className="sr-only">{section.present ? " written" : " still missing"}</span>
                </span>
                {/* The prompt used to be the body of the scaffold, which is how nine of them
                    reached the corpus as a policy. It says the same thing here and cannot be
                    saved by accident, because it is not in the box. */}
                {section.present ? null : (
                  <span className="mt-0.5 block pl-[19px] leading-5 text-ink-2">
                    {section.prompt}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>

        <Field label="Tags" hint="Comma-separated. Used for filtering, not for retrieval.">
          {(props) => (
            <Input
              {...props}
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              placeholder="domain, boundaries, dependencies"
            />
          )}
        </Field>

        {save.error ? <ErrorNotice error={save.error} /> : null}
      </PanelBody>
      <PanelFooter>
        <div className="flex flex-wrap items-center gap-2">
          <Button disabled={incomplete || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? <Spinner /> : policy ? "Save changes" : "Create policy"}
          </Button>
          <span className="text-xs text-ink-2">
            {missing.length
              ? `Still to write: ${missing.join(", ")}.`
              : "Written to the workspace as a Markdown file the next review reads."}
          </span>
        </div>
      </PanelFooter>
    </Panel>
  );
}
