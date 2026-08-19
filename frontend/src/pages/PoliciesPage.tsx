import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { coreApi } from "../api";
import {
  Button,
  Card,
  Empty,
  ErrorNotice,
  Field,
  Input,
  Loading,
  PageTitle,
  Select,
  StatusBadge,
  Textarea,
  cn,
} from "../components/ui";
import { Markdown } from "../components/markdown";

export function PoliciesPage() {
  const client = useQueryClient();
  const policies = useQuery({ queryKey: ["policies"], queryFn: coreApi.policies });
  const [query, setQuery] = useState("");
  const [strength, setStrength] = useState("all");
  const [authoring, setAuthoring] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [draft, setDraft] = useState({
    title: "",
    description: "",
    body: "",
    tags: "",
    strength: "guidance" as "guidance" | "preferred" | "required",
  });
  const create = useMutation({
    mutationFn: () =>
      coreApi.createPolicy({
        title: draft.title.trim(),
        description: draft.description.trim(),
        body: draft.body.trim(),
        tags: draft.tags
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        strength: draft.strength,
      }),
    onSuccess: async () => {
      setAuthoring(false);
      setDraft({ title: "", description: "", body: "", tags: "", strength: "guidance" });
      await client.invalidateQueries({ queryKey: ["policies"] });
    },
  });
  const remove = useMutation({
    mutationFn: coreApi.deletePolicy,
    onSuccess: async () => {
      setPendingDelete(null);
      await client.invalidateQueries({ queryKey: ["policies"] });
    },
  });
  if (policies.isLoading) return <Loading label="Loading policy corpus…" />;
  if (policies.error) return <ErrorNotice error={policies.error} />;
  const visible = (policies.data || []).filter(
    (policy) =>
      `${policy.title} ${policy.description} ${policy.body} ${policy.tags.join(" ")}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (strength === "all" || policy.strength === strength),
  );

  return (
    <div>
      <PageTitle
        eyebrow="Architectural guidance"
        title="Policy corpus"
        description="Policies are authored guidance. Retrieval selects a relevant, auditable subset for each architecture candidate."
      >
        <Button onClick={() => setAuthoring(!authoring)} variant={authoring ? "secondary" : "primary"}>
          {authoring ? "Close form" : "Author policy"}
        </Button>
      </PageTitle>
      {authoring ? (
        <Card className="mb-6" tone="accent">
          <h2 className="font-display text-xl font-semibold">New workspace policy</h2>
          <p className="mt-1 text-sm text-ink-3">
            Write the durable architectural principle; retrieval mechanics remain outside the policy itself.
          </p>
          <div className="mt-6 grid gap-5">
            <div className="grid gap-5 md:grid-cols-2">
              <Field label="Title" htmlFor="policy-title">
                <Input
                  id="policy-title"
                  value={draft.title}
                  onChange={(event) => setDraft({ ...draft, title: event.target.value })}
                  placeholder="Keep domain code framework-free"
                />
              </Field>
              <Field label="Strength" htmlFor="policy-strength">
                <Select
                  id="policy-strength"
                  value={draft.strength}
                  onChange={(event) => setDraft({ ...draft, strength: event.target.value as typeof draft.strength })}
                >
                  <option value="guidance">Guidance</option>
                  <option value="preferred">Preferred</option>
                  <option value="required">Required</option>
                </Select>
              </Field>
            </div>
            <Field
              label="Description"
              htmlFor="policy-description"
              hint="A short statement of what this policy protects."
            >
              <Input
                id="policy-description"
                value={draft.description}
                onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                placeholder="Preserve a portable domain model"
              />
            </Field>
            <Field label="Policy body" htmlFor="policy-body" hint="Markdown is supported.">
              <Textarea
                id="policy-body"
                value={draft.body}
                onChange={(event) => setDraft({ ...draft, body: event.target.value })}
                className="min-h-44"
                placeholder="Explain the principle, applicability, and trade-offs…"
              />
            </Field>
            <Field label="Tags" htmlFor="policy-tags" hint="Comma-separated">
              <Input
                id="policy-tags"
                value={draft.tags}
                onChange={(event) => setDraft({ ...draft, tags: event.target.value })}
                placeholder="domain, boundaries, dependencies"
              />
            </Field>
            <div>
              <Button
                disabled={!draft.title.trim() || !draft.description.trim() || !draft.body.trim() || create.isPending}
                onClick={() => create.mutate()}
              >
                {create.isPending ? "Saving policy…" : "Save policy"}
              </Button>
            </div>
          </div>
          {create.error ? (
            <div className="mt-4">
              <ErrorNotice error={create.error} />
            </div>
          ) : null}
        </Card>
      ) : null}
      {(policies.data || []).length ? (
        <div className="mb-5 flex flex-col gap-3 rounded-2xl border border-rule bg-surface p-3 shadow-sm sm:flex-row">
          <Input
            aria-label="Search policies"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="sm:max-w-md"
            placeholder="Search title, body, or tag…"
          />
          <div className="flex gap-1" aria-label="Filter policy strength">
            {["all", "required", "preferred", "guidance"].map((item) => (
              <button
                key={item}
                onClick={() => setStrength(item)}
                className={cn(
                  "rounded-lg px-3 py-2 text-xs font-semibold capitalize",
                  strength === item ? "bg-primary-soft text-primary" : "text-ink-3 hover:bg-canvas-strong",
                )}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      {!visible.length ? (
        <Empty title={policies.data?.length ? "No matching policies" : "No policies yet"}>
          {policies.data?.length
            ? "Adjust the search or strength filter."
            : "Author a workspace policy to add architectural guidance."}
        </Empty>
      ) : (
        <div className="grid gap-3">
          {visible.map((policy) => (
            <details
              key={policy.id}
              className="group rounded-2xl border border-rule bg-surface shadow-card open:border-primary/25"
            >
              <summary className="flex list-none items-start justify-between gap-4 p-5 sm:p-6">
                <div className="min-w-0">
                  <div className="font-display text-xl font-semibold tracking-tight">{policy.title}</div>
                  <div className="mt-2 text-sm leading-6 text-ink-2">{policy.description}</div>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-ink-3">
                    <span>
                      {policy.scope}
                      {policy.applies_to ? ` · ${policy.applies_to}` : ""}
                    </span>
                    <span>·</span>
                    <span>{policy.source.author}</span>
                    {policy.tags.map((tag) => (
                      <span key={tag} className="rounded-full bg-canvas-strong px-2 py-0.5">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
                <StatusBadge status={policy.strength} />
              </summary>
              <div className="border-t border-rule px-5 py-5 sm:px-6">
                <div className="text-sm leading-7 text-ink-2">
                  <Markdown>{policy.body}</Markdown>
                </div>
                {policy.origin === "workspace" ? (
                  <div className="mt-5 border-t border-rule pt-4">
                    {pendingDelete === policy.id ? (
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-ink-3">Delete this workspace policy?</span>
                        <Button
                          size="sm"
                          variant="danger"
                          disabled={remove.isPending}
                          onClick={() => remove.mutate(policy.id)}
                        >
                          Confirm delete
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setPendingDelete(null)}>
                          Keep
                        </Button>
                      </div>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setPendingDelete(policy.id)}
                        className="text-danger"
                      >
                        Delete policy
                      </Button>
                    )}
                  </div>
                ) : null}
              </div>
            </details>
          ))}
        </div>
      )}
      {remove.error ? (
        <div className="mt-4">
          <ErrorNotice error={remove.error} />
        </div>
      ) : null}
    </div>
  );
}
