import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type ReactNode } from "react";

import {
  api,
  type EmbeddingCatalog,
  type ModelCatalog,
  type ProviderAvailability,
  type ThinkingMode,
  type Workspace,
} from "../../api";
import { cn } from "../../lib/cn";
import {
  EDITOR_LABELS,
  readEditorScheme,
  writeEditorScheme,
  type EditorScheme,
} from "../../lib/editor";
import { plural, relativeTime } from "../../lib/format";
import { useTheme } from "../../lib/theme";
import { Badge, StatusDot, Tag } from "../../ui/badge";
import { Button, ToggleButton } from "../../ui/button";
import { Field, Input, Select } from "../../ui/field";
import { CheckIcon, RefreshIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { ErrorNotice, LoadingPanel, Notice, Spinner } from "../../ui/states";
import { useToast } from "../../ui/toast";

/** One model on offer, in the terms this page renders rather than the terms it arrived in. */
type Choice = {
  key: string;
  provider: string;
  /** The identifier the provider knows it by, and what several tiles can share. */
  model: string;
  /** What tells this tile apart from the others of the same model, where anything does. */
  variant: string | null;
  detail: string;
  limits: string | null;
  selected: boolean;
  extra?: ReactNode;
  select: () => void;
};

/** One model id and every variant of it a provider offers. */
type ModelRow = { model: string; choices: Choice[] };

/** A provider and everything it currently offers, which is what a section is. */
type Group = { provider: ProviderAvailability; models: ModelRow[]; count: number };

/**
 * Above this many models in one half of the page, the list stops being something you read.
 *
 * The page was designed against a catalogue of nine hand-approved models, where every tile
 * fitted on a screen and a filter would have been a control with nothing to do. OpenRouter
 * made the reasoning half 225 rows and twelve screens tall — 23,000 pixels on a phone — with
 * no way to look for a name, so choosing a model meant scrolling past two hundred you were
 * not choosing. Twelve is roughly the point where scanning turns into searching.
 */
const FILTERABLE_FROM = 12;

/** The rows whose model id or description contains what was typed, and their groups. */
function matching(groups: Group[], query: string): Group[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return groups;
  return groups.map((group) => {
    const models = group.models.filter((row) =>
      [row.model, ...row.choices.map((choice) => choice.detail)]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
    return { ...group, models };
  });
}

/**
 * How hard this row asks the model to think, said in the provider's own vocabulary.
 *
 * Nothing where the model has no depth to choose, because a tag reading "default" beside a
 * model that has one setting is a word that distinguishes it from nothing. `on` and `off`
 * are the switch Ollama has; the four levels are the dial Gemini 3 has, which replaced the
 * switch — there is no request to a Gemini 3 model that means "do not think".
 */
function thinkingLabel(thinking: ThinkingMode): string | null {
  if (thinking === null || thinking === undefined) return null;
  if (thinking === true) return "thinking";
  if (thinking === false) return "direct";
  return `${thinking} thinking`;
}

function thinkingTag(thinking: ThinkingMode): ReactNode {
  const label = thinkingLabel(thinking);
  return label ? <Tag>{label}</Tag> : null;
}

/** What a model will take and give back — on the wire since the catalog existed, never shown. */
function limitsOf(input: number | null | undefined, output: number | null | undefined) {
  const parts = [
    input ? `context ${input.toLocaleString()}` : null,
    output ? `output ${output.toLocaleString()}` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

export function SettingsPage() {
  const client = useQueryClient();
  const say = useToast().say;
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
    meta: { handled: true },
    mutationFn: (choice: { provider: string; model: string; thinking: ThinkingMode }) =>
      api.selectModel(choice.provider, choice.model, choice.thinking),
    onSuccess: refresh,
  });
  const selectEmbedding = useMutation({
    meta: { handled: true },
    mutationFn: (choice: { provider: string; model: string }) =>
      api.selectEmbedding(choice.provider, choice.model),
    onSuccess: refresh,
  });
  const clearReasoning = useMutation({
    mutationFn: () => api.clearModelSelection(),
    onSuccess: async () => {
      await refresh();
      say("Nothing is set. Choose a reasoning model before the next review.", "Selection cleared");
    },
  });
  const clearEmbedding = useMutation({
    mutationFn: () => api.clearEmbeddingSelection(),
    onSuccess: async () => {
      await refresh();
      say("Nothing is set. Choose an embedding model before the next review.", "Selection cleared");
    },
  });

  const models = workspace.data?.models;
  const reasoningPinned = Boolean(models?.pinned);
  const embeddingPinned = Boolean(models?.embedding_pinned);
  const failure = models?.failure;

  const reasoningGroups = grouped(
    catalog.data?.providers ?? [],
    (catalog.data?.candidates ?? []).map((model) => ({
      key: `${model.provider}:${model.model}:${model.thinking}`,
      provider: model.provider,
      model: model.model,
      variant: thinkingLabel(model.thinking ?? null),
      detail: model.label || "chat model",
      limits: limitsOf(model.input_token_limit, model.output_token_limit),
      selected: Boolean(model.is_selected),
      extra: thinkingTag(model.thinking ?? null),
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
      model: model.model,
      variant: null,
      detail: model.label || "embedding model",
      limits: null,
      selected: Boolean(model.is_selected),
      extra: <Tag>{model.dimensions.toLocaleString()} dimensions</Tag>,
      select: () => selectEmbedding.mutate({ provider: model.provider, model: model.model }),
    })),
  );

  const rechecking = catalog.isFetching || embeddings.isFetching;

  return (
    <div>
      <PageHeader
        eyebrow="Runtime"
        title="Models"
        description="The model that judges architecture and the model that retrieves policy are set separately."
        // One action, and it is the only thing on this header that acts on the workspace. The
        // theme switch used to sit here beside it: an unlabelled three-way control about
        // colour, first in the tab order of a page called Models, carrying nothing but an
        // `aria-label`. It is a per-browser preference exactly like the editor scheme, so it
        // is now in the section that already explains what per-browser means.
        actions={
          /* A provider is probed when this page asks for the catalog, and never again.
             Starting Ollama after the page had painted needed a browser reload. */
          <Button
            size="sm"
            variant="secondary"
            disabled={rechecking}
            onClick={() => void refresh()}
          >
            {/* The label is printed right beside it. */}
            {rechecking ? (
              <Spinner label="" />
            ) : (
              <RefreshIcon aria-hidden="true" className="size-3.5" />
            )}
            Re-check providers
          </Button>
        }
      />

      {failure ? (
        <div className="mb-5">
          <ErrorNotice error={new Error(failure)} title="The workspace reported a problem" />
        </div>
      ) : null}

      {workspace.error ? (
        <div className="mb-5">
          <ErrorNotice
            error={workspace.error}
            title="The workspace could not say what is selected"
            action={
              <Button size="sm" variant="secondary" onClick={() => void workspace.refetch()}>
                Try again
              </Button>
            }
          />
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
          loading={catalog.isLoading}
          loadingLabel="Asking each provider what it can offer…"
          failure={catalog.error}
          onRetry={() => void catalog.refetch()}
          selection={
            workspace.isLoading ? null : (
              <Selection
                identity={selectedIdentity(workspace.data, "reasoning")}
                extra={thinkingTag(models?.reasoning?.thinking ?? null)}
                missing={whyMissing(
                  catalog.data,
                  models?.reasoning,
                  providerLabel(catalog.data?.providers, models?.reasoning?.provider),
                )}
                pinned={reasoningPinned}
                empty="No reasoning model is selected."
                onClear={() => clearReasoning.mutate()}
                clearing={clearReasoning.isPending}
              />
            )
          }
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
          loading={embeddings.isLoading}
          loadingLabel="Asking each provider what it can embed…"
          failure={embeddings.error}
          onRetry={() => void embeddings.refetch()}
          selection={
            workspace.isLoading ? null : (
              <Selection
                identity={selectedIdentity(workspace.data, "embedding")}
                extra={
                  models?.embedding ? (
                    <Tag>{models.embedding.dimensions.toLocaleString()} dimensions</Tag>
                  ) : null
                }
                missing={whyMissing(
                  embeddings.data,
                  models?.embedding,
                  providerLabel(embeddings.data?.providers, models?.embedding?.provider),
                )}
                pinned={embeddingPinned}
                empty="No embedding model is selected."
                onClear={() => clearEmbedding.mutate()}
                clearing={clearEmbedding.isPending}
              />
            )
          }
        />

        <EditorChoice />
      </div>
    </div>
  );
}

/** `provider:model`, which is how the workspace names what it is set to. */
function selectedIdentity(workspace: Workspace | undefined, kind: "reasoning" | "embedding") {
  const identity = kind === "reasoning" ? workspace?.models.reasoning : workspace?.models.embedding;
  return identity ? `${identity.provider}:${identity.model}` : null;
}

/** A provider's own name for itself, falling back to the identifier the workspace stores. */
function providerLabel(
  providers: ProviderAvailability[] | undefined,
  provider: string | undefined,
): string {
  return (providers ?? []).find((item) => item.provider === provider)?.label || provider || "";
}

/**
 * Why the selected model has no tile, in the reader's terms — or null when it has one.
 *
 * These are two different faults with two different repairs, and they were one sentence. The
 * page said "Ollama is not answering" whenever the selected model was missing from the
 * catalogue, including when Ollama had answered a moment earlier and listed everything it
 * had: the workspace was pinned to `nomic-embed-text`, the machine had `embeddinggemma`, and
 * the page reported the daemon as down beside a provider row reading "1 model · checked just
 * now". Restarting a provider that is already running is the wrong repair, and it is the one
 * that sentence asks for. Pulling the model, or choosing another, is the right one.
 *
 * `available` is the probe's own answer about the provider, so the distinction costs nothing
 * to make — it was on the wire already and this page was not reading it.
 */
function whyMissing(
  catalog: ModelCatalog | EmbeddingCatalog | undefined,
  identity: { provider: string; model: string } | null | undefined,
  label: string,
): string | null {
  if (!identity) return null;
  const listed = (catalog?.candidates ?? []).some(
    (candidate) =>
      candidate.provider === identity.provider && candidate.model === identity.model,
  );
  if (listed) return null;

  const availability = (catalog?.providers ?? []).find(
    (item) => item.provider === identity.provider,
  );
  // Unreachable is the claim that needs the probe to have made it. Absent one — a provider
  // the catalogue does not mention at all — the honest statement is the narrow one, which is
  // also the one that is true either way.
  if (availability && !availability.available) {
    return availability.detail
      ? `${label} is not answering: ${availability.detail}`
      : `${label} is not answering.`;
  }
  return `${label} is answering, but it is not offering this model.`;
}

/**
 * What this workspace is actually set to, read from the workspace rather than from the probe.
 *
 * `is_selected` is computed per candidate from the live probe, so the moment a provider stops
 * answering the selected model has no tile at all and nothing on the page wears the Selected
 * chip. The reader saw fifteen tiles, none of them marked, and no statement anywhere of what
 * the workspace was set to — while the answer sat unrendered in `workspace.models`.
 *
 * `Clear selection` sits beside it for the same reason. The server's own docstring calls it
 * "the way back out of a choice that turned out to be wrong. There is no file to edit
 * instead", and it matters most in exactly this state, where there is no tile to click away
 * from. It is not offered where the choice was made by environment configuration, because
 * then there is nothing here to clear.
 */
function Selection({
  identity,
  extra,
  missing,
  pinned,
  empty,
  onClear,
  clearing,
}: {
  identity: string | null;
  extra: ReactNode;
  missing: string | null;
  pinned: boolean;
  empty: string;
  onClear: () => void;
  clearing: boolean;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-rule bg-surface-2 px-3.5 py-3">
      <div className="min-w-0">
        <Label>Currently selected</Label>
        {identity ? (
          <p className="mt-1 text-sm leading-6 text-ink-2">
            <Mono className="text-[13px] font-semibold text-ink">{identity}</Mono> is this
            workspace&rsquo;s model.{missing ? ` ${missing}` : ""}
            {extra ? <span className="ml-1.5 align-middle">{extra}</span> : null}
          </p>
        ) : (
          // An explicit unknown outranks an implied one: a blank line here reads as a page
          // that failed to load rather than as a workspace nobody has chosen for.
          <p className="mt-1 text-sm text-ink-2">{empty}</p>
        )}
      </div>
      {identity && !pinned ? (
        <Button size="sm" variant="secondary" disabled={clearing} onClick={onClear}>
          {clearing ? <Spinner /> : "Clear selection"}
        </Button>
      ) : null}
    </div>
  );
}

/**
 * Choices filed under the provider that offers them, available providers first, and one row
 * per model id inside each.
 *
 * A section per provider, because a provider is what a reader is actually deciding between.
 * The models used to be one flat grid with the provider printed inside each tile, which read
 * as one list of fifteen unrelated things — and put the reason a provider had nothing to
 * offer ("OPENROUTER_API_KEY is unset") in a separate availability panel, several rows away from
 * the empty space it explained. Grouping puts the cure beside the absence. Providers with
 * nothing to offer are kept and shown last: they are the rows that say what to fix, and
 * dropping them would answer "why is Groq not here" with silence.
 *
 * The second grouping is the model id. A thinking variant is a separate candidate, so the
 * page printed `gemma4:26b-mlx` twice and `gemini-3.5-flash-lite` four times — the id set
 * loud in every one of them, and the only thing that differed between the four carried by a
 * small quiet tag. The id is said once per model now, and the tile leads with the variant.
 *
 * The order within each half is the order the backend named them, which is the order the
 * deployment enabled them in — so a workspace that put Ollama first still reads that way.
 */
function grouped(providers: ProviderAvailability[], choices: Choice[]): Group[] {
  const groups = providers.map((provider) => {
    const offered = choices.filter((choice) => choice.provider === provider.provider);
    const models: ModelRow[] = [];
    for (const choice of offered) {
      const row = models.find((item) => item.model === choice.model);
      if (row) row.choices.push(choice);
      else models.push({ model: choice.model, choices: [choice] });
    }
    return { provider, models, count: offered.length };
  });
  return [
    ...groups.filter((group) => group.provider.available),
    ...groups.filter((group) => !group.provider.available),
  ];
}

/**
 * The theme, under a label somebody can read.
 *
 * It is not a `Field`, and that is the one thing here worth explaining: `Field` labels a
 * control with `<label htmlFor>`, which associates with a form element and does nothing at
 * all pointing at a group of buttons. So the label is a `<span>` the group names with
 * `aria-labelledby` — the same association `Field` makes, spelled the way a group can make
 * it — set in `Field`'s own type so the two rows in this panel read as one form.
 */
function ThemeChoice() {
  const { preference, setPreference } = useTheme();
  const id = useId();
  return (
    <div className="min-w-0">
      <span id={id} className="block text-xs font-semibold text-ink">
        Theme
      </span>
      <div
        role="group"
        aria-labelledby={id}
        // The track is `--sunken`, which is what a set of alternatives sits in everywhere else
        // in the system — `ToggleGroup variant="segment"` and the solid tab strip. It used to
        // be `bg-surface`, which was legible in the page header and is the panel's own colour
        // now that the control lives inside one.
        className="mt-1.5 flex w-fit gap-0.5 rounded-sm border border-rule bg-sunken p-0.5"
      >
        {/* `ToggleButton` rather than the `bg-ink text-canvas` this hand-rolled: the one toggle
            recipe the design system retired by name — *a toggle that is on is raised, not
            inverted* — and the only control on the page that missed the coarse-pointer floor. */}
        {(["light", "dark", "system"] as const).map((option) => (
          <ToggleButton
            key={option}
            pressed={preference === option}
            onClick={() => setPreference(option)}
            className="capitalize"
          >
            {option}
          </ToggleButton>
        ))}
      </div>
    </div>
  );
}

/**
 * The two settings that belong to the browser rather than to the workspace.
 *
 * Which editor a path opens in is what turns every path in a review into somewhere to go:
 * `ui/meta.tsx` has offered an *open* control beside every source path for as long as there
 * has been a scheme to build one from, and nothing anywhere wrote the scheme — so the
 * affordance existed and never once appeared. It is a per-machine fact rather than a workspace
 * one, and off until somebody says otherwise; `lib/editor.ts` argues both at length.
 *
 * The theme is the same kind of fact and the page used to give the two opposite treatments.
 * The editor got this section, with a left column that says *kept in this browser rather than
 * in the workspace* — which is the sentence that explains the theme as well. The theme got the
 * header's actions slot beside *Re-check providers*, a workspace action, with an `aria-label`
 * and nothing visible to say what it was. One sentence covers both, so both are under it.
 */
function EditorChoice() {
  const [scheme, setScheme] = useState<EditorScheme>(readEditorScheme);
  return (
    <section className="grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)] xl:gap-6">
      <div className="xl:sticky xl:top-20 xl:self-start">
        <Label>Kept in this browser</Label>
        <h2 className="mt-1.5 font-display text-xl font-semibold tracking-tight text-ink">
          This machine
        </h2>
        <p className="mt-2 text-sm leading-6 text-ink-2">
          Neither of these is part of the workspace. Two people reading the same review may run
          different editors and want different themes, and one of them may be reading it over
          SSH where no local path resolves at all.
        </p>
      </div>
      <Panel>
        <PanelHeader
          title="Theme and editor"
          description="How this browser draws a review, and where a source path in one opens."
        />
        <PanelBody className="grid gap-4">
          <ThemeChoice />
          <Field
            label="Editor"
            hint="Nothing is offered by default. A link that silently fails costs a click to discover and looks like the product being broken."
          >
            {(props) => (
              <Select
                {...props}
                value={scheme}
                onChange={(event) => {
                  const next = event.target.value as EditorScheme;
                  writeEditorScheme(next);
                  setScheme(next);
                }}
                className="max-w-80"
              >
                {(Object.keys(EDITOR_LABELS) as EditorScheme[]).map((option) => (
                  <option key={option} value={option}>
                    {EDITOR_LABELS[option]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </PanelBody>
      </Panel>
    </section>
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
  loading,
  loadingLabel,
  failure,
  onRetry,
  selection,
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
  loading: boolean;
  loadingLabel: string;
  failure: unknown;
  onRetry: () => void;
  selection: ReactNode;
}) {
  const [query, setQuery] = useState("");
  const total = groups.reduce((count, group) => count + group.count, 0);
  const filterable = total >= FILTERABLE_FROM;
  const shown = filterable ? matching(groups, query) : groups;
  const left = shown.reduce((count, group) => count + group.models.length, 0);

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
        <p className="mt-2 text-sm leading-6 text-ink-2">{description}</p>
      </div>

      <div className="grid gap-3">
        {selection}

        {pinned ? <Notice>{pinnedNotice}</Notice> : null}

        {/* One slow or failed probe used to replace the whole page — including the half that
            would have let you pick a different provider. It replaces its own section now. */}
        {failure ? (
          <ErrorNotice
            error={failure}
            action={
              <Button size="sm" variant="secondary" onClick={onRetry}>
                Try again
              </Button>
            }
          />
        ) : loading ? (
          <LoadingPanel label={loadingLabel} rows={3} />
        ) : groups.length ? (
          <>
            {filterable ? (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <Input
                  type="search"
                  value={query}
                  aria-label={`Filter ${title.toLowerCase()}s`}
                  placeholder="Filter by name — flash, qwen, embed"
                  onChange={(event) => setQuery(event.target.value)}
                  className="h-9 min-w-0 max-w-[22rem] flex-1 text-[13px]"
                />
                <span className="shrink-0 text-[12px] text-ink-3">
                  <span className="font-mono tabular-nums text-ink-2">{left}</span> of{" "}
                  <span className="font-mono tabular-nums">{total}</span>
                </span>
              </div>
            ) : null}
            {/* A provider whose every model was filtered out keeps its panel: the panel is
                also where "OPENROUTER_API_KEY is unset" is said, and a filter that hid the
                reason a provider is empty would answer a search with silence. */}
            {shown.map((group) => (
              <ProviderSection
                key={group.provider.provider}
                group={group}
                disabled={pinned || busy}
                emptyNotice={emptyNotice}
                filtered={filterable && Boolean(query.trim())}
              />
            ))}
          </>
        ) : (
          <p className="text-sm text-ink-2">No provider is configured.</p>
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
  filtered = false,
}: {
  group: Group;
  disabled: boolean;
  emptyNotice: string;
  /** Whether a filter is narrowing this, which is a different empty from having nothing. */
  filtered?: boolean;
}) {
  const { provider, models, count } = group;
  const available = provider.available;
  return (
    // `sunken`, not `flat`. The panel was trying to say "this provider has nothing for you" by
    // stepping down the elevation ramp, and it could not: the only thing separating `flat`
    // from `raised` is `shadow-rim`, and `--rim` is `transparent` in light on purpose. So in
    // the light theme a live provider and a dead one were the same white panel with the same
    // hairline, and the entire signal fell on the dot and the badge — the two things quietened
    // below. A recess reads in both themes, and it says the right thing: a provider offering
    // nothing is not a panel, it is a hole where one would be.
    <Panel tone={available ? "raised" : "sunken"}>
      <PanelHeader
        title={
          <span className="flex items-center gap-2">
            {/* Weight, not hue. A provider that is not answering is not a verdict, and
                `--material` *is* the accent — so a workspace with two API keys unset opened
                this page with two red dots and two red badges on it, while the page's actual
                choices, the model tiles, carried no accent at all. That is a fifth job for the
                one hue the system has, and `ui/states.tsx` names this exact case: a fact about
                your configuration is a standing note, never a grade. `marked` is `--ink` and
                `neutral` is `--ink-3`, which is the ramp the doc asks for at no chroma. */}
            <StatusDot tone={available ? "marked" : "neutral"} />
            {provider.label || provider.provider}
          </span>
        }
        // The reason a provider offers nothing, in the section where nothing is offered.
        // Held one panel away it read as an unrelated status list.
        description={provider.detail || undefined}
        actions={
          <span className="flex flex-wrap items-center justify-end gap-2 text-xs text-ink-3">
            {available ? (
              <span className="tabular-nums">
                {filtered && models.length !== count
                  ? `${models.length} of ${plural(count, "model")}`
                  : plural(count, "model")}
              </span>
            ) : (
              // No glyph and no hue. The caution triangle belongs to the sign register, which
              // is for what is *graded* — the model's three verdicts and a review's own state
              // — and an unset API key is graded by nobody. `dashed` would be no better: that
              // is the scale register, and an availability is not a position on a scale. So
              // the word carries it, and `provider.detail` beside it carries the cure.
              <Badge tone="neutral">Unavailable</Badge>
            )}
            {/* When the probe ran, which is the difference between "Ollama is not running"
                and "Ollama was not running when this page was built". */}
            <span>checked {relativeTime(provider.probed_at)}</span>
          </span>
        }
      />
      <PanelBody>
        {models.length ? (
          <div className="grid gap-2 md:grid-cols-2">
            {models.map((row) =>
              row.choices.length === 1 ? (
                <ModelChoice
                  key={row.choices[0].key}
                  choice={row.choices[0]}
                  lead={
                    <Mono
                      className="block truncate text-[13px] font-semibold text-ink"
                      title={row.model}
                    >
                      {row.model}
                    </Mono>
                  }
                  disabled={disabled || !available}
                />
              ) : (
                <div
                  key={row.model}
                  className="rounded-md border border-rule bg-surface-2 p-2 md:col-span-2"
                >
                  {/* Said once, above the variants of it, rather than in the loudest line of
                      four tiles that are otherwise identical. */}
                  <Mono className="block px-1 pb-2 text-[13px] font-semibold text-ink">
                    {row.model}
                  </Mono>
                  <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                    {row.choices.map((choice) => (
                      <ModelChoice
                        key={choice.key}
                        choice={choice}
                        lead={
                          <span className="block truncate text-[13px] font-semibold capitalize text-ink">
                            {choice.variant ?? row.model}
                          </span>
                        }
                        name={`${row.model} ${choice.variant ?? ""}`.trim()}
                        disabled={disabled || !available}
                      />
                    ))}
                  </div>
                </div>
              ),
            )}
          </div>
        ) : (
          <p className="text-sm text-ink-2">
            {!available
              ? "Nothing to choose from until this provider answers."
              : /* Two different empties. A provider that offers nothing says so; a provider
                   whose models were all filtered out must not be read as offering nothing,
                   or clearing the box would look like the catalogue changing under you. */
                filtered && count
                ? "Nothing here matches what you typed."
                : emptyNotice}
          </p>
        )}
      </PanelBody>
    </Panel>
  );
}

function ModelChoice({
  choice,
  lead,
  name,
  disabled,
}: {
  choice: Choice;
  lead: ReactNode;
  /** The whole identity, where what is on screen is only the half that distinguishes it. */
  name?: string;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={choice.select}
      aria-pressed={choice.selected}
      aria-label={name}
      className={cn(
        "rounded-md border p-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50",
        choice.selected
          ? "border-ink bg-sunken ring-1 ring-rule-strong"
          : "border-rule bg-surface hover:border-rule-strong",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {lead}
          {/* The provider is the heading above this tile now, so the tile says what the
              model is instead of repeating where it came from. */}
          <div className="mt-1 text-xs text-ink-3">{choice.detail}</div>
          {choice.limits ? (
            <div className="mt-1 text-[11px] tabular-nums text-ink-3">{choice.limits}</div>
          ) : null}
        </div>
        {/* `Badge` rather than the block-label recipe this had hand-rolled: the recipe
            belongs to one component and this is a badge. The tick comes from `ui/icons.tsx`
            rather than from `Mark`'s vocabulary, whose sign register is for what is *graded*
            — and a chosen model is not a verdict. */}
        {choice.selected ? (
          <Badge tone="marked" className="shrink-0">
            <CheckIcon aria-hidden="true" className="size-3" />
            Selected
          </Badge>
        ) : null}
      </div>
      {/* The provider's own heading says whether it answered; repeating it on every tile
          under that heading is the same fact said twice. */}
      {choice.extra ? <div className="mt-2.5 flex flex-wrap gap-1.5">{choice.extra}</div> : null}
    </button>
  );
}
