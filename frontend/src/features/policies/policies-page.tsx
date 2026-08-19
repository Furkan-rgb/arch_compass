import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { coreApi, type PolicyDocument } from "../../api";
import { cn } from "../../lib/cn";
import { humanise, strengthOf } from "../../lib/format";
import { StrengthBadge, Tag } from "../../ui/badge";
import { Button, ToggleButton } from "../../ui/button";
import { SearchInput } from "../../ui/field";
import { ChevronDown } from "../../ui/icons";
import { Markdown } from "../../ui/markdown";
import { MetaLine, Mono } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel } from "../../ui/states";
import { PolicyEditor } from "./policy-editor";

const STRENGTHS = ["all", "required", "preferred", "guidance"] as const;
const SCOPES = ["all", "general", "user", "organisation", "repository", "accepted_adr"] as const;

function PolicyCard({
  policy,
  expanded,
  onToggle,
  onEdit,
  onDelete,
  deleting,
}: {
  policy: PolicyDocument;
  expanded: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  const strength = strengthOf(policy.strength);
  const workspaceOwned = policy.origin === "workspace";

  return (
    <article
      className={cn(
        "overflow-hidden rounded-lg border bg-surface shadow-panel transition",
        expanded ? "border-rule-strong" : "border-rule hover:border-rule-strong",
      )}
    >
      <h3>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          className="flex w-full items-start justify-between gap-3 px-4 py-3.5 text-left sm:px-5"
        >
          <span className="min-w-0">
            <span className="flex flex-wrap items-center gap-2">
              <span className="font-display text-base font-semibold tracking-tight text-ink">
                {policy.title}
              </span>
              <StrengthBadge strength={policy.strength} />
              {workspaceOwned ? <Tag>workspace</Tag> : null}
            </span>
            <span className="mt-1.5 block text-sm leading-6 text-ink-2">{policy.description}</span>
            <MetaLine
              className="mt-2"
              items={[
                humanise(policy.scope),
                policy.applies_to ? `applies to ${policy.applies_to}` : null,
                policy.source.author,
                ...policy.tags.map((tag) => <Tag key={tag}>{tag}</Tag>),
              ]}
            />
          </span>
          <ChevronDown
            className={cn("mt-1 size-4 shrink-0 text-ink-3 transition", expanded && "rotate-180")}
          />
        </button>
      </h3>

      {expanded ? (
        <div className="animate-expand border-t border-rule px-4 py-4 sm:px-5">
          <Markdown>{policy.body}</Markdown>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-4">
            <div className="min-w-0">
              <Label>Provenance</Label>
              <MetaLine
                className="mt-1"
                items={[
                  <Mono key="id" className="text-[11px]">
                    {policy.id}
                  </Mono>,
                  <Mono key="path" className="text-[11px]">
                    {policy.source_path}
                  </Mono>,
                  <Mono key="hash" className="text-[11px]">
                    {policy.content_hash.slice(0, 12)}
                  </Mono>,
                  strength.label,
                ]}
              />
            </div>
            {workspaceOwned ? (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <Button size="sm" variant="secondary" onClick={onEdit}>
                  Edit
                </Button>
                {confirming ? (
                  <>
                    <span className="text-xs text-ink-3">Delete permanently?</span>
                    <Button size="sm" variant="danger" disabled={deleting} onClick={onDelete}>
                      Confirm
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
                      Keep
                    </Button>
                  </>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>
                    Delete
                  </Button>
                )}
              </div>
            ) : (
              <p className="text-xs text-ink-3">
                Read from a registered source — edit it where it is authored.
              </p>
            )}
          </div>
        </div>
      ) : null}
    </article>
  );
}

export function PoliciesPage() {
  const client = useQueryClient();
  const policies = useQuery({ queryKey: ["policies"], queryFn: coreApi.policies });
  const sources = useQuery({ queryKey: ["policy-sources"], queryFn: coreApi.policySources });
  const [query, setQuery] = useState("");
  const [strength, setStrength] = useState<(typeof STRENGTHS)[number]>("all");
  const [scope, setScope] = useState<(typeof SCOPES)[number]>("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [editing, setEditing] = useState<PolicyDocument | null>(null);
  const [authoring, setAuthoring] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => coreApi.deletePolicy(id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["policies"] });
    },
  });

  const all = useMemo(() => policies.data ?? [], [policies.data]);
  const visible = all.filter((policy) => {
    const haystack =
      `${policy.title} ${policy.description ?? ""} ${policy.body} ${policy.tags.join(" ")}`.toLowerCase();
    return (
      haystack.includes(query.toLowerCase()) &&
      (strength === "all" || policy.strength === strength) &&
      (scope === "all" || policy.scope === scope)
    );
  });

  if (policies.isLoading) return <LoadingPanel label="Loading the policy corpus…" rows={5} />;
  if (policies.error) return <ErrorNotice error={policies.error} />;

  const counts = {
    required: all.filter((policy) => policy.strength === "required").length,
    workspace: all.filter((policy) => policy.origin === "workspace").length,
  };

  return (
    <div>
      <PageHeader
        eyebrow="Auditable guidance"
        title="Policies"
        description="Policies are authored architectural guidance. Retrieval selects a subset for each candidate, and records exactly which ones it chose."
        actions={
          <Button
            variant={authoring ? "secondary" : "primary"}
            onClick={() => {
              setEditing(null);
              setAuthoring(!authoring);
            }}
          >
            {authoring ? "Close" : "Author policy"}
          </Button>
        }
      />

      {authoring || editing ? (
        <div className="mb-5">
          <PolicyEditor
            key={editing?.id ?? "new"}
            policy={editing}
            onClose={() => {
              setAuthoring(false);
              setEditing(null);
            }}
          />
        </div>
      ) : null}

      <div className="mb-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px] xl:items-start">
        <div>
          <div className="mb-3 grid gap-2 rounded-lg border border-rule bg-surface p-2 shadow-panel lg:grid-cols-[minmax(0,1fr)_auto]">
            <SearchInput
              label="Search policies"
              value={query}
              onValueChange={setQuery}
              placeholder="Search title, body or tag"
            />
            <div className="flex flex-wrap items-center gap-3">
              <div role="group" aria-label="Filter by strength" className="flex gap-1">
                {STRENGTHS.map((item) => (
                  <ToggleButton
                    key={item}
                    pressed={strength === item}
                    onClick={() => setStrength(item)}
                    className="capitalize"
                  >
                    {item}
                  </ToggleButton>
                ))}
              </div>
              <label className="flex items-center gap-1.5 text-xs text-ink-3">
                Scope
                <select
                  aria-label="Filter by scope"
                  value={scope}
                  onChange={(event) => setScope(event.target.value as (typeof SCOPES)[number])}
                  className="rounded-sm border border-rule bg-surface px-2 py-1 text-xs text-ink"
                >
                  {SCOPES.map((item) => (
                    <option key={item} value={item}>
                      {humanise(item)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          {!visible.length ? (
            <EmptyState title={all.length ? "No policy matches that" : "No policies loaded"}>
              {all.length
                ? "Clear the search, or widen the strength and scope filters."
                : "Author a workspace policy, or register a folder of Markdown policies as a source."}
            </EmptyState>
          ) : (
            <div className="grid gap-2.5">
              {visible.map((policy) => (
                <PolicyCard
                  key={policy.id}
                  policy={policy}
                  expanded={expanded === policy.id}
                  onToggle={() => setExpanded(expanded === policy.id ? null : policy.id)}
                  onEdit={() => {
                    setAuthoring(false);
                    setEditing(policy);
                  }}
                  onDelete={() => remove.mutate(policy.id)}
                  deleting={remove.isPending}
                />
              ))}
            </div>
          )}

          {remove.error ? (
            <div className="mt-4">
              <ErrorNotice error={remove.error} />
            </div>
          ) : null}
        </div>

        <div className="grid gap-4">
          <Panel tone="sunken">
            <PanelBody>
              <Label>Corpus</Label>
              <ul className="mt-2.5 grid gap-1.5 text-sm text-ink-2">
                <li className="flex justify-between gap-3">
                  <span>Policies</span>
                  <span className="tabular-nums text-ink">{all.length}</span>
                </li>
                <li className="flex justify-between gap-3">
                  <span>Required</span>
                  <span className="tabular-nums text-ink">{counts.required}</span>
                </li>
                <li className="flex justify-between gap-3">
                  <span>Authored here</span>
                  <span className="tabular-nums text-ink">{counts.workspace}</span>
                </li>
                <li className="flex justify-between gap-3">
                  <span>Showing</span>
                  <span className="tabular-nums text-ink">{visible.length}</span>
                </li>
              </ul>
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader
              title="Sources"
              description="Folders of Markdown policies this workspace reads on every review."
            />
            <PanelBody>
              {sources.isLoading ? (
                <p className="text-sm text-ink-3">Loading sources…</p>
              ) : !sources.data?.length ? (
                <p className="text-sm text-ink-3">
                  Only the bundled corpus and anything authored here.
                </p>
              ) : (
                <ul className="grid gap-1.5">
                  {sources.data.map((source) => (
                    <li key={source.canonical_path}>
                      <Mono className="block truncate text-[11px]">{source.canonical_path}</Mono>
                    </li>
                  ))}
                </ul>
              )}
            </PanelBody>
          </Panel>
        </div>
      </div>
    </div>
  );
}
