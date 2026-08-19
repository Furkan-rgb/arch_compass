import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { coreApi } from "../../api";
import { cn } from "../../lib/cn";
import { useTheme } from "../../lib/theme";
import { Badge, StatusDot, Tag } from "../../ui/badge";
import { CheckIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { ErrorNotice, LoadingPanel } from "../../ui/states";

type Provider = { provider: string; available: boolean; detail?: string };

/**
 * Two independent choices, presented as two.
 *
 * Reasoning decides what the evidence means; embedding decides which policies are put in
 * front of it. They come from different providers as often as not, and the page never
 * implies that choosing one chooses the other.
 */
export function SettingsPage() {
  const client = useQueryClient();
  const catalog = useQuery({ queryKey: ["models"], queryFn: coreApi.models });
  const embeddings = useQuery({ queryKey: ["embeddings"], queryFn: coreApi.embeddings });
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: coreApi.workspace });

  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["models"] }),
      client.invalidateQueries({ queryKey: ["embeddings"] }),
      client.invalidateQueries({ queryKey: ["workspace"] }),
    ]);
  };

  const selectReasoning = useMutation({
    mutationFn: (choice: { provider: string; model: string; thinking: boolean | null }) =>
      coreApi.selectModel(choice.provider, choice.model, choice.thinking),
    onSuccess: refresh,
  });
  const selectEmbedding = useMutation({
    mutationFn: (choice: { provider: string; model: string }) =>
      coreApi.selectEmbedding(choice.provider, choice.model),
    onSuccess: refresh,
  });

  if (catalog.isLoading || embeddings.isLoading || workspace.isLoading) {
    return <LoadingPanel label="Asking each provider what it can offer…" rows={5} />;
  }
  if (catalog.error) return <ErrorNotice error={catalog.error} />;
  if (embeddings.error) return <ErrorNotice error={embeddings.error} />;
  if (workspace.error) return <ErrorNotice error={workspace.error} />;

  const reasoningPinned = Boolean(workspace.data?.models.pinned);
  const embeddingPinned = Boolean(workspace.data?.models.embedding_pinned);
  const failure = workspace.data?.models.failure;

  return (
    <div>
      <PageHeader
        eyebrow="Runtime"
        title="Models"
        description="ArchCompass separates the model that judges architecture from the model that retrieves policy. Either can be local or hosted, and neither constrains the other."
        actions={<ThemeChoice />}
      />

      {failure ? (
        <div className="mb-5">
          <ErrorNotice error={new Error(failure)} title="The workspace reported a problem" />
        </div>
      ) : null}

      <div className="grid gap-6">
        <ModelSection
          index="01"
          title="Reasoning model"
          role="Architecture judgement"
          description="Reads the candidate, its evidence, the case and the retrieved policies, and decides what the evidence means. It never invents repository or policy identity."
          providers={catalog.data?.providers ?? []}
          pinned={reasoningPinned}
          pinnedNotice="Pinned by environment configuration. Remove the provider override to choose here."
        >
          <div className="grid gap-2 md:grid-cols-2">
            {catalog.data?.candidates.map((model) => {
              const provider = catalog.data.providers.find(
                (item) => item.provider === model.provider,
              );
              return (
                <ModelChoice
                  key={`${model.provider}:${model.model}:${model.thinking}`}
                  title={model.model}
                  provider={model.provider}
                  detail={model.label || "chat model"}
                  selected={Boolean(model.is_selected)}
                  unavailable={!provider?.available}
                  disabled={reasoningPinned || !provider?.available || selectReasoning.isPending}
                  extra={
                    model.thinking === null || model.thinking === undefined ? null : (
                      <Tag>{model.thinking ? "thinking" : "direct"}</Tag>
                    )
                  }
                  onSelect={() =>
                    selectReasoning.mutate({
                      provider: model.provider,
                      model: model.model,
                      thinking: model.thinking ?? null,
                    })
                  }
                />
              );
            })}
          </div>
          {selectReasoning.error ? (
            <div className="mt-3">
              <ErrorNotice error={selectReasoning.error} />
            </div>
          ) : null}
        </ModelSection>

        <ModelSection
          index="02"
          title="Embedding model"
          role="Policy retrieval"
          description="Builds and queries the local policy index. Retrieval provenance records the identity of whichever model is selected here, so a review can be audited later."
          providers={embeddings.data?.providers ?? []}
          pinned={embeddingPinned}
          pinnedNotice="Pinned by environment configuration. Remove the ARCHCOMPASS_EMBEDDING_* overrides to choose here."
        >
          <div className="grid gap-2 md:grid-cols-2">
            {embeddings.data?.candidates.map((model) => {
              const provider = embeddings.data.providers.find(
                (item) => item.provider === model.provider,
              );
              return (
                <ModelChoice
                  key={`${model.provider}:${model.model}:${model.dimensions}`}
                  title={model.model}
                  provider={model.provider}
                  detail={model.label || "embedding model"}
                  selected={Boolean(model.is_selected)}
                  unavailable={!provider?.available}
                  disabled={embeddingPinned || !provider?.available || selectEmbedding.isPending}
                  extra={<Tag>{model.dimensions.toLocaleString()} dimensions</Tag>}
                  onSelect={() =>
                    selectEmbedding.mutate({ provider: model.provider, model: model.model })
                  }
                />
              );
            })}
          </div>
          {selectEmbedding.error ? (
            <div className="mt-3">
              <ErrorNotice error={selectEmbedding.error} />
            </div>
          ) : null}
        </ModelSection>
      </div>
    </div>
  );
}

function ThemeChoice() {
  const { preference, setPreference } = useTheme();
  return (
    <div
      role="group"
      aria-label="Colour theme"
      className="flex gap-1 rounded-md border border-rule bg-surface p-1"
    >
      {(["light", "dark", "system"] as const).map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={preference === option}
          onClick={() => setPreference(option)}
          className={cn(
            "min-h-8 rounded-sm px-2.5 text-xs font-semibold capitalize transition",
            preference === option ? "bg-ink text-canvas" : "text-ink-3 hover:bg-sunken hover:text-ink",
          )}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

function ModelSection({
  index,
  title,
  role,
  description,
  providers,
  pinned,
  pinnedNotice,
  children,
}: {
  index: string;
  title: string;
  role: string;
  description: string;
  providers: Provider[];
  pinned: boolean;
  pinnedNotice: string;
  children: ReactNode;
}) {
  return (
    <section className="grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)] xl:gap-6">
      <div className="xl:sticky xl:top-20 xl:self-start">
        <Mono className="text-[11px] font-bold text-accent">{index}</Mono>
        <h2 className="mt-1.5 font-display text-xl font-semibold tracking-tight text-ink">
          {title}
        </h2>
        <Label className="mt-1">{role}</Label>
        <p className="mt-2 text-sm leading-6 text-ink-3">{description}</p>
      </div>

      <div className="grid gap-3">
        <Panel tone="flat">
          <PanelHeader title="Providers" description="Availability is checked when this page loads." />
          <PanelBody className="grid gap-2 sm:grid-cols-2">
            {providers.length ? (
              providers.map((provider) => (
                <div
                  key={provider.provider}
                  className="flex items-center justify-between gap-3 rounded-md border border-rule bg-surface-2 px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <StatusDot tone={provider.available ? "cleared" : "material"} />
                      <span className="text-sm font-semibold capitalize text-ink">
                        {provider.provider}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-ink-3">
                      {provider.detail || "No detail reported"}
                    </p>
                  </div>
                  <Badge tone={provider.available ? "cleared" : "material"} glyph={provider.available ? "●" : "▲"}>
                    {provider.available ? "Available" : "Unavailable"}
                  </Badge>
                </div>
              ))
            ) : (
              <p className="text-sm text-ink-3">No provider is configured.</p>
            )}
          </PanelBody>
        </Panel>

        {pinned ? (
          <p className="rounded-md border border-held/30 bg-held-soft/60 px-3 py-2.5 text-sm leading-6 text-held">
            {pinnedNotice}
          </p>
        ) : null}

        {children}
      </div>
    </section>
  );
}

function ModelChoice({
  title,
  provider,
  detail,
  selected,
  unavailable,
  disabled,
  extra,
  onSelect,
}: {
  title: string;
  provider: string;
  detail: string;
  selected: boolean;
  unavailable: boolean;
  disabled: boolean;
  extra?: ReactNode;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "rounded-md border p-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50",
        selected
          ? "border-accent bg-accent-soft ring-1 ring-accent/25"
          : "border-rule bg-surface hover:border-rule-strong",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Mono className="block truncate text-[13px] font-semibold text-ink">{title}</Mono>
          <div className="mt-1 text-xs text-ink-3">
            <span className="capitalize">{provider}</span> · {detail}
          </div>
        </div>
        {selected ? (
          <span className="inline-flex items-center gap-1 rounded-sm bg-accent px-1.5 py-1 text-[10px] font-bold uppercase tracking-[0.08em] text-on-accent">
            <CheckIcon className="size-3" />
            Selected
          </span>
        ) : null}
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        {extra}
        {unavailable ? <Tag>provider unavailable</Tag> : null}
      </div>
    </button>
  );
}
