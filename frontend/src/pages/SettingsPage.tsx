import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { coreApi } from "../api";
import { Card, ErrorNotice, Loading, PageTitle, StatusBadge, cn } from "../components/ui";

export function SettingsPage() {
  const client = useQueryClient();
  const catalog = useQuery({ queryKey: ["models"], queryFn: coreApi.models });
  const embeddings = useQuery({ queryKey: ["embeddings"], queryFn: coreApi.embeddings });
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: coreApi.workspace });
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ["models"] }), client.invalidateQueries({ queryKey: ["embeddings"] }), client.invalidateQueries({ queryKey: ["workspace"] })]); };
  const selectReasoning = useMutation({ mutationFn: ({ provider, model, thinking }: { provider: string; model: string; thinking: boolean | null }) => coreApi.selectModel(provider, model, thinking), onSuccess: refresh });
  const selectEmbedding = useMutation({ mutationFn: ({ provider, model }: { provider: string; model: string }) => coreApi.selectEmbedding(provider, model), onSuccess: refresh });

  if (catalog.isLoading || embeddings.isLoading || workspace.isLoading) return <Loading label="Discovering available models…" />;
  if (catalog.error) return <ErrorNotice error={catalog.error} />;
  if (embeddings.error) return <ErrorNotice error={embeddings.error} />;
  if (workspace.error) return <ErrorNotice error={workspace.error} />;

  return <div>
    <PageTitle eyebrow="Runtime configuration" title="Models" description="Reasoning and embedding are independent capabilities. Select the best provider for each without changing the review workflow." />
    <div className="grid gap-8">
      <ModelSection number="01" title="Reasoning model" description="Judges candidates, explains findings, and generates clarification questions." providers={catalog.data?.providers ?? []}>
        {catalog.data?.candidates.map((model) => <ModelChoice key={`${model.provider}:${model.model}:${model.thinking}`} selected={Boolean(model.is_selected)} disabled={!catalog.data.providers.find((provider) => provider.provider === model.provider)?.available || selectReasoning.isPending} onClick={() => selectReasoning.mutate({ provider: model.provider, model: model.model, thinking: model.thinking ?? null })} title={model.model} meta={`${model.provider} · ${model.label || "chat model"}${model.thinking === null || model.thinking === undefined ? "" : model.thinking ? " · thinking" : " · direct"}`} />)}
      </ModelSection>

      <ModelSection number="02" title="Embedding model" description="Builds and queries the local policy index. This choice is independent from the reasoning model." providers={embeddings.data?.providers ?? []} notice={workspace.data?.models.embedding_pinned ? "Embedding selection is pinned by environment configuration. Remove the ARCHCOMPASS_EMBEDDING_* overrides to select it here." : undefined}>
        {embeddings.data?.candidates.map((model) => <ModelChoice key={`${model.provider}:${model.model}:${model.dimensions}`} selected={Boolean(model.is_selected)} disabled={Boolean(workspace.data?.models.embedding_pinned) || !embeddings.data.providers.find((provider) => provider.provider === model.provider)?.available || selectEmbedding.isPending} onClick={() => selectEmbedding.mutate({ provider: model.provider, model: model.model })} title={model.model} meta={`${model.provider} · ${model.label || "embedding model"}`} detail={`${model.dimensions.toLocaleString()} dimensions`} />)}
      </ModelSection>
    </div>
    {selectReasoning.error ? <div className="mt-5"><ErrorNotice error={selectReasoning.error} /></div> : null}
    {selectEmbedding.error ? <div className="mt-5"><ErrorNotice error={selectEmbedding.error} /></div> : null}
  </div>;
}

function ModelChoice({ selected, disabled, onClick, title, meta, detail }: { selected: boolean; disabled: boolean; onClick: () => void; title: string; meta: string; detail?: string }) {
  return <button disabled={disabled} onClick={onClick} className={cn("rounded-2xl border p-4 text-left shadow-sm transition disabled:cursor-not-allowed disabled:opacity-45", selected ? "border-primary bg-primary-soft ring-1 ring-primary/15" : "border-rule bg-surface hover:border-primary/35 hover:-translate-y-0.5")}><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="truncate font-display text-lg font-semibold">{title}</div><div className="mt-1 text-xs text-ink-3">{meta}</div></div>{selected ? <StatusBadge status="selected" /> : null}</div>{detail ? <div className="mt-4 border-t border-rule pt-3 text-xs font-semibold text-ink-2">{detail}</div> : null}</button>;
}

function ModelSection({ number, title, description, providers, notice, children }: { number: string; title: string; description: string; providers: Array<{ provider: string; available: boolean; detail?: string }>; notice?: string; children: ReactNode }) {
  return <section className="grid gap-5 xl:grid-cols-[260px_minmax(0,1fr)]">
    <div><div className="font-mono text-xs font-bold text-primary">{number}</div><h2 className="mt-2 font-display text-2xl font-semibold tracking-tight">{title}</h2><p className="mt-2 text-sm leading-6 text-ink-3">{description}</p></div>
    <div className="grid gap-4">
      <Card className="p-4 sm:p-4"><div className="flex flex-wrap gap-x-6 gap-y-3">{providers.map((provider) => <div key={provider.provider} className="flex min-w-48 flex-1 items-center justify-between gap-3"><div><div className="text-sm font-semibold capitalize">{provider.provider}</div><div className="mt-0.5 text-xs text-ink-3">{provider.detail || "No provider detail"}</div></div><StatusBadge status={provider.available ? "available" : "unavailable"} /></div>)}</div></Card>
      {notice ? <div className="rounded-xl border border-warning/25 bg-warning-soft p-4 text-sm leading-6 text-warning">{notice}</div> : null}
      <div className="grid content-start gap-3 md:grid-cols-2">{children}</div>
    </div>
  </section>;
}
