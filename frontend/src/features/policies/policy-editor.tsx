import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type PolicyDocument, type PolicyDraft } from "../../api";
import { cn } from "../../lib/cn";
import { Button } from "../../ui/button";
import { Field, Input, Select, Textarea } from "../../ui/field";
import { Markdown } from "../../ui/markdown";
import { Label, Panel, PanelBody, PanelFooter, PanelHeader } from "../../ui/panel";
import { ErrorNotice, Spinner } from "../../ui/states";
import { Tabs, TabPanel } from "../../ui/tabs";
import { missingSections, policyTemplate, sectionStates } from "./sections";

const EMPTY: PolicyDraft = {
  title: "",
  description: "",
  body: policyTemplate(),
  tags: [],
  strength: "guidance",
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
 */
export function PolicyEditor({
  policy,
  onClose,
}: {
  policy: PolicyDocument | null;
  onClose: () => void;
}) {
  const client = useQueryClient();
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

  const save = useMutation({
    mutationFn: () =>
      policy ? api.updatePolicy(policy.id, payload()) : api.createPolicy(payload()),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["policies"] });
      onClose();
    },
  });

  const outstanding = missingSections(draft.body);
  const incomplete =
    !draft.title.trim() || !draft.description.trim() || !draft.body.trim() || outstanding.length > 0;

  return (
    <Panel className="animate-expand" tone="accent">
      <PanelHeader
        title={policy ? `Edit “${policy.title}”` : "New workspace policy"}
        description="Durable architectural guidance. Retrieval mechanics stay out of the policy itself."
        actions={
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
        }
      />
      <PanelBody className="grid gap-4">
        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_180px]">
          <Field label="Title">
            {(props) => (
              <Input
                {...props}
                value={draft.title}
                onChange={(event) => setDraft({ ...draft, title: event.target.value })}
                placeholder="Keep domain code framework-free"
              />
            )}
          </Field>
          <Field label="Strength" hint="How binding this is">
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

        <Field label="Description" hint="One sentence on what this policy protects.">
          {(props) => (
            <Input
              {...props}
              value={draft.description}
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
                <p className="text-sm text-ink-3">Nothing to preview yet.</p>
              )}
            </div>
          </TabPanel>
        </div>

        <div className="rounded-md border border-rule bg-surface-2 p-3">
          <Label>Required sections</Label>
          <p className="mt-1 text-xs leading-5 text-ink-3">
            The workspace re-reads this policy with the same parser it uses for the bundled
            corpus, which needs all nine sections present and written.
          </p>
          <ul className="mt-2.5 grid gap-1 sm:grid-cols-3">
            {sectionStates(draft.body).map((section) => (
              <li
                key={section.name}
                className={cn(
                  "flex items-center gap-1.5 text-xs",
                  section.present ? "text-cleared" : "text-ink-3",
                )}
              >
                <span aria-hidden="true">{section.present ? "●" : "○"}</span>
                {section.name}
                <span className="sr-only">{section.present ? " written" : " still missing"}</span>
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
          <span className="text-xs text-ink-3">
            {outstanding.length
              ? `Still to write: ${outstanding.join(", ")}.`
              : "Written to the workspace as a Markdown file the next review reads."}
          </span>
        </div>
      </PanelFooter>
    </Panel>
  );
}
