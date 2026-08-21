import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { api, type ProviderAvailability } from "../../api";
import { cn } from "../../lib/cn";
import { plural } from "../../lib/format";
import { useTheme } from "../../lib/theme";
import { Badge, StatusDot, Tag } from "../../ui/badge";
import { CheckIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { ErrorNotice, LoadingPanel, Notice } from "../../ui/states";

/** One model on offer, in the terms this page renders rather than the terms it arrived in. */
type Choice = {
  key: string;
  provider: string;
  title: string;
  detail: string;
  selected: boolean;
  extra?: ReactNode;
  select: () => void;
};

/** A provider and everything it currently offers, which is what a section is. */
type Group = { provider: ProviderAvailability; choices: Choice[] };

/**
 * A section per provider, because a provider is what a reader is actually deciding between.
 *
 * The models used to be one flat grid with the provider printed inside each tile, which read
 * as one list of fifteen unrelated things — and put the reason a provider had nothing to
 * offer ("GROQ_API_KEY is unset") in a separate availability panel, several rows away from
 * the empty space it explained. Grouping puts the cure beside the absence.
 *
 * Providers with nothing to offer are kept and shown last. They are the rows that say what
 * to fix, and dropping them would answer "why is Groq not here" with silence.
 */
export function SettingsPage() {
  const client = useQueryClient();
  const catalog = useQuery({ queryKey: ["models"], queryFn: api.models });
  const embeddings = useQuery({ queryKey: ["embeddings"], queryFn: api.embeddings });
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: api.workspace });

  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["models"] }),
      client.invalidateQueries({ queryKey: ["embeddings"] }),
      client.invalidateQueries({ queryKey: ["workspace"] }),
    ]);
  };

  const selectReasoning = useMutation({
    mutationFn: (choice: { provider: string; model: string; thinking: boolean | null }) =>
      api.selectModel(choice.provider, choice.model, choice.thinking),
    onSuccess: refresh,
  });
  const selectEmbedding = useMutation({
    mutationFn: (choice: { provider: string; model: string }) =>
      api.selectEmbedding(choice.provider, choice.model),
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

  const reasoningGroups = grouped(
    catalog.data?.providers ?? [],
    (catalog.data?.candidates ?? []).map((model) => ({
      key: `${model.provider}:${model.model}:${model.thinking}`,
      provider: model.provider,
      title: model.model,
      detail: model.label || "chat model",
      selected: Boolean(model.is_selected),
      extra:
        model.thinking === null || model.thinking === undefined ? null : (
          <Tag>{model.thinking ? "thinking" : "direct"}</Tag>
        ),
      select: () =>
        selectReasoning.mutate({
          provider: model.provider,
          model: model.model,
          thinking: model.thinking ?? null,
        }),
    })),
  );

  const embeddingGroups = grouped(
    embeddings.data?.providers ?? [],
    (embeddings.data?.candidates ?? []).map((model) => ({
      key: `${model.provider}:${model.model}:${model.dimensions}`,
      provider: model.provider,
      title: model.model,
      detail: model.label || "embedding model",
      selected: Boolean(model.is_selected),
      extra: <Tag>{model.dimensions.toLocaleString()} dimensions</Tag>,
      select: () => selectEmbedding.mutate({ provider: model.provider, model: model.model }),
    })),
  );

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
          title="Reasoning model"
          role="Judges the evidence"
          description="Reads the candidate, its evidence, the case and the retrieved policies, and decides what the evidence means. It never invents repository or policy identity."
          groups={reasoningGroups}
          pinned={reasoningPinned}
          pinnedNotice="Pinned by environment configuration. Remove the provider override to choose here."
          busy={selectReasoning.isPending}
          error={selectReasoning.error}
          emptyNotice="This provider has no reasoning models to offer."
        />

        <ModelSection
          title="Embedding model"
          role="Retrieves the policy"
          description="Builds and queries the local policy index. Retrieval provenance records the identity of whichever model is selected here, so a review can be audited later."
          groups={embeddingGroups}
          pinned={embeddingPinned}
          pinnedNotice="Pinned by environment configuration. Remove the ARCHCOMPASS_EMBEDDING_* overrides to choose here."
          busy={selectEmbedding.isPending}
          error={selectEmbedding.error}
          emptyNotice="This provider serves no embeddings."
        />
      </div>
    </div>
  );
}

/**
 * Choices filed under the provider that offers them, available providers first.
 *
 * The order within each half is the order the backend named them, which is the order the
 * deployment enabled them in — so a workspace that put Ollama first still reads that way.
 */
function grouped(providers: ProviderAvailability[], choices: Choice[]): Group[] {
  const groups = providers.map((provider) => ({
    provider,
    choices: choices.filter((choice) => choice.provider === provider.provider),
  }));
  return [
    ...groups.filter((group) => group.provider.available),
    ...groups.filter((group) => !group.provider.available),
  ];
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
  title,
  role,
  description,
  groups,
  pinned,
  pinnedNotice,
  busy,
  error,
  emptyNotice,
}: {
  title: string;
  role: string;
  description: string;
  groups: Group[];
  pinned: boolean;
  pinnedNotice: string;
  busy: boolean;
  error: unknown;
  emptyNotice: string;
}) {
  return (
    <section className="grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)] xl:gap-6">
      {/* The eyebrow is the model's job, not its position in a list. These two choices are
          independent — a numbered marker above them would claim an order that does not
          exist, and the thing that actually distinguishes them is what each one does. */}
      <div className="xl:sticky xl:top-20 xl:self-start">
        <Label>{role}</Label>
        <h2 className="mt-1.5 font-display text-xl font-semibold tracking-tight text-ink">
          {title}
        </h2>
        <p className="mt-2 text-sm leading-6 text-ink-3">{description}</p>
      </div>

      <div className="grid gap-3">
        {pinned ? <Notice>{pinnedNotice}</Notice> : null}

        {groups.length ? (
          groups.map((group) => (
            <ProviderSection
              key={group.provider.provider}
              group={group}
              disabled={pinned || busy}
              emptyNotice={emptyNotice}
            />
          ))
        ) : (
          <p className="text-sm text-ink-3">No provider is configured.</p>
        )}

        {error ? <ErrorNotice error={error} /> : null}
      </div>
    </section>
  );
}

function ProviderSection({
  group,
  disabled,
  emptyNotice,
}: {
  group: Group;
  disabled: boolean;
  emptyNotice: string;
}) {
  const { provider, choices } = group;
  const available = provider.available;
  return (
    <Panel tone={available ? "raised" : "flat"}>
      <PanelHeader
        title={
          <span className="flex items-center gap-2">
            <StatusDot tone={available ? "cleared" : "material"} />
            {provider.label || provider.provider}
          </span>
        }
        // The reason a provider offers nothing, in the section where nothing is offered.
        // Held one panel away it read as an unrelated status list.
        description={provider.detail || undefined}
        actions={
          available ? (
            <span className="text-xs tabular-nums text-ink-3">
              {plural(choices.length, "model")}
            </span>
          ) : (
            <Badge tone="material" glyph="triangle">
              Unavailable
            </Badge>
          )
        }
      />
      <PanelBody>
        {choices.length ? (
          <div className="grid gap-2 md:grid-cols-2">
            {choices.map((choice) => (
              <ModelChoice
                key={choice.key}
                choice={choice}
                disabled={disabled || !available}
              />
            ))}
          </div>
        ) : (
          <p className="text-sm text-ink-3">
            {available ? emptyNotice : "Nothing to choose from until this provider answers."}
          </p>
        )}
      </PanelBody>
    </Panel>
  );
}

function ModelChoice({ choice, disabled }: { choice: Choice; disabled: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={choice.select}
      aria-pressed={choice.selected}
      className={cn(
        "rounded-md border p-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50",
        choice.selected
          ? "border-ink bg-sunken ring-1 ring-rule-strong"
          : "border-rule bg-surface hover:border-rule-strong",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Mono className="block truncate text-[13px] font-semibold text-ink" title={choice.title}>
            {choice.title}
          </Mono>
          {/* The provider is the heading above this tile now, so the tile says what the
              model is instead of repeating where it came from. */}
          <div className="mt-1 text-xs text-ink-3">{choice.detail}</div>
        </div>
        {choice.selected ? (
          <span className="inline-flex items-center gap-1 rounded-sm bg-ink px-1.5 py-1 text-[10px] font-bold uppercase tracking-[0.08em] text-canvas">
            <CheckIcon className="size-3" />
            Selected
          </span>
        ) : null}
      </div>
      {/* The provider's own heading says whether it answered; repeating it on every tile
          under that heading is the same fact said twice. */}
      {choice.extra ? <div className="mt-2.5 flex flex-wrap gap-1.5">{choice.extra}</div> : null}
    </button>
  );
}
