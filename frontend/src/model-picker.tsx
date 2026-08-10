import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, ChevronDown, Cpu, Loader } from "lucide-react";
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandFooter,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { cn } from "@/lib/utils";

import { api } from "./api";
import type { ModelCandidate, WorkspaceSummary } from "./types";

/**
 * Which model this workspace reasons with, chosen from the ones that actually exist.
 *
 * The list is not what a file configures — it is what a running provider answered with when
 * this sheet opened. Nothing is asked until then: a probe costs a round trip to every
 * provider, and the moment someone is waiting to choose is the only moment worth paying for
 * it and the only moment the answer has to be fresh.
 *
 * A provider that did not answer is shown, greyed, carrying the reason. That row is the most
 * useful thing on the screen — "GOOGLE_API_KEY is unset" names what to do, and a provider
 * quietly missing from a list names nothing.
 */

/* Opening the sheet is a page-level act: the chip lives in the top bar and the start step
   asks for a model from the middle of a form. Sharing one piece of state beats a second
   copy of this sheet mounted somewhere else, which would probe twice and disagree. */
const PickerContext = createContext<(() => void) | null>(null);

export function useModelPicker() {
  return useContext(PickerContext);
}

/* What a row is matched on. */
function haystack(...parts: Array<string | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

/* The right-hand column: what the provider says this model can hold. Set against the name
   rather than under it, tabular so a column of them lines up without a column being drawn. */
const rowMeta =
  "ml-auto flex-none pl-4 text-right text-meta tabular-nums text-ink-3 group-data-[selected=true]/command-item:text-ink-2";

function tokens(count: number | null | undefined) {
  if (!count) return "";
  return count >= 1000 ? `${Math.round(count / 1000)}k` : `${count}`;
}

/** `131k in · 32k out`, or nothing where the provider reports no limits — as Ollama does. */
function limits(candidate: ModelCandidate) {
  const input = tokens(candidate.input_token_limit);
  const output = tokens(candidate.output_token_limit);
  if (!input && !output) return "";
  return [input && `${input} in`, output && `${output} out`].filter(Boolean).join(" · ");
}

export function ModelPickerProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const client = useQueryClient();

  const catalog = useQuery({ queryKey: ["models"], queryFn: api.models, enabled: open });
  const choose = useMutation({
    mutationFn: api.selectModel,
    onSuccess: (summary: WorkspaceSummary) => {
      // The server hands back the whole summary, so the chip is right before this closes
      // rather than a refetch later.
      client.setQueryData(["workspace"], summary);
      setOpen(false);
    },
  });

  const byProvider = useMemo(() => {
    const grouped = new Map<string, ModelCandidate[]>();
    for (const candidate of catalog.data?.candidates ?? []) {
      grouped.set(candidate.provider, [
        ...(grouped.get(candidate.provider) ?? []),
        candidate,
      ]);
    }
    return grouped;
  }, [catalog.data]);

  const providers = catalog.data?.providers ?? [];

  return (
    <PickerContext.Provider value={() => setOpen(true)}>
      {children}
      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Choose a reasoning model"
        description="Only models a reachable provider currently has are offered."
      >
        <Command
          loop
          filter={(value, search) =>
            value.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()) ? 1 : 0
          }
        >
          <CommandInput placeholder="Find a model…" />
          <CommandList>
            {/* The wait is real and worth drawing: this asks every configured provider over
                the network, and a local server that is not running spends the probe's whole
                two-second budget before saying so. A sentence alone left the sheet looking
                like it had already answered "nothing". */}
            <CommandEmpty>
              {catalog.isLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <Loader size={13} className="spin" aria-hidden />
                  Asking each provider what it has…
                </span>
              ) : catalog.isError ? (
                "The workspace could not be asked which models are available."
              ) : (
                "No provider answered, and nothing here is configured to ask."
              )}
            </CommandEmpty>

            {providers.map((provider) => {
              const candidates = byProvider.get(provider.provider) ?? [];
              return (
                <CommandGroup key={provider.provider} heading={provider.provider}>
                  {/* Not a row that can be chosen, and deliberately still a row: the whole
                      point of showing an unreachable provider is the sentence it carries. */}
                  {!provider.available ? (
                    <CommandItem disabled value={haystack(provider.provider, provider.detail)}>
                      <AlertTriangle size={15} aria-hidden />
                      <span className="min-w-0 text-meta text-ink-2">
                        {provider.detail || "This provider did not answer."}
                      </span>
                    </CommandItem>
                  ) : null}
                  {candidates.map((candidate) => {
                    // A model that can reason either way appears twice, and the variant is
                    // part of the row's identity: the same name with thinking on and off
                    // differs in what it costs, how long it takes and how much output
                    // headroom the request gets, which is exactly what is being chosen.
                    const thinking = candidate.thinking ?? null;
                    // Choosing is a round trip of its own — the server asks the provider for
                    // this model's limits on the way past — so the row that was clicked says
                    // it is working, and no second row can be clicked underneath it.
                    const saving =
                      choose.isPending &&
                      choose.variables?.provider === candidate.provider &&
                      choose.variables?.model === candidate.model &&
                      (choose.variables?.thinking ?? null) === thinking;
                    return (
                    <CommandItem
                      key={`${candidate.provider}:${candidate.model}:${String(thinking)}`}
                      value={haystack(
                        candidate.model,
                        candidate.label,
                        candidate.provider,
                        thinking === true ? "thinking" : null,
                      )}
                      disabled={choose.isPending}
                      onSelect={() =>
                        choose.mutate({
                          provider: candidate.provider,
                          model: candidate.model,
                          thinking,
                        })
                      }
                    >
                      {saving ? (
                        <Loader size={15} className="spin" aria-hidden />
                      ) : candidate.is_selected ? (
                        <Check size={15} aria-hidden />
                      ) : (
                        <Cpu size={15} aria-hidden />
                      )}
                      <span className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-meta">
                        {candidate.model}
                      </span>
                      {/* Only the thinking variant is marked. Its sibling needs no badge
                          saying "not thinking" — an unmarked row already reads as the plain
                          one, and a model offering a single way of working has nothing to
                          distinguish it from. */}
                      {thinking === true ? (
                        <Badge variant="neutral" className="flex-none">
                          thinking
                        </Badge>
                      ) : null}
                      <span className={rowMeta}>{limits(candidate)}</span>
                    </CommandItem>
                    );
                  })}
                </CommandGroup>
              );
            })}
          </CommandList>
          <CommandFooter>
            {choose.isError
              ? (choose.error as Error).message
              : "↑↓ navigate · ↵ choose · esc close"}
          </CommandFooter>
        </Command>
      </CommandDialog>
    </PickerContext.Provider>
  );
}

/**
 * The model, in the top bar, as the control that changes it.
 *
 * Four states, because there are four things worth saying and they need different answers
 * from the reader. Nothing chosen is a required field and reads as one. A recorded failure
 * is not the same as unavailability: the model is selected and listed and the last run
 * against it still failed, which is the half of a model's health no probe can see.
 */
export function ModelChip({ workspace }: { workspace: WorkspaceSummary | undefined }) {
  const openPicker = useModelPicker();
  const models = workspace?.models;
  const reasoning = models?.reasoning;
  const failing = Boolean(models?.failure);
  const chosen = Boolean(reasoning);
  // Pinned runs and the brief moment before the workspace has answered are both read-only:
  // `--provider`/`--model` said which provider this process costs against, so a choice
  // offered here would be one that gets ignored.
  const interactive = Boolean(openPicker) && !models?.pinned;

  const label = !workspace
    ? "reading workspace…"
    : reasoning
      ? `${reasoning.provider} · ${reasoning.model}${reasoning.thinking === true ? " · thinking" : ""}`
      : "Choose a model";

  const chip = (
    <Badge
      variant="neutral"
      className={cn(
        "min-w-0 gap-2 bg-transparent py-0.5 font-mono font-normal tracking-normal",
        // The one state that is not a machine's name is not set in a machine's voice.
        !chosen && workspace && "font-sans",
        // The bar's own hover, the same one its navigation links draw. Without it a chip
        // that opens a chooser looked exactly like a chip that does nothing — which is
        // what a pinned one is, three lines below.
        interactive && "group-hover/chip:bg-sunken group-hover/chip:text-ink",
      )}
    >
      {/* The accent, because in this design the accent means "you can act on this" and an
          unfilled required field is exactly that. Not the danger hue: nothing is wrong yet,
          and spending the verdict colour on an unanswered question would leave nothing left
          to say with when a run against the chosen model actually fails. */}
      <span className="relative flex size-1.5 flex-none">
        {/* The ping is the affordance turned up one notch: an unfilled required field is
            the one chip state that wants to be noticed before it is looked for. Tailwind's
            own notification-dot idiom — a ghost of the dot scaling outward behind it —
            and only here: a pulse on the chosen or failing dot would nag about a state
            the label already tells. Reduced motion drops the echo and keeps the dot. */}
        {!chosen && workspace ? (
          <span
            aria-hidden
            className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75 motion-reduce:hidden"
          />
        ) : null}
        <span
          className={cn(
            "relative inline-flex size-1.5 rounded-full",
            !chosen ? "bg-primary" : failing ? "bg-danger" : "bg-cleared",
          )}
        />
      </span>
      <span className="overflow-hidden text-ellipsis whitespace-nowrap">{label}</span>
      {/* The static half of the affordance, and the load-bearing half. Hover only tells
          someone already reaching for it; this says it opens something before they do. */}
      {interactive ? <ChevronDown size={12} className="flex-none text-ink-3" aria-hidden /> : null}
    </Badge>
  );

  if (!interactive) {
    return (
      <span title={`Pinned by --provider/--model${models?.failure ? ` — ${models.failure}` : ""}`}>
        {chip}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={() => openPicker?.()}
      aria-haspopup="dialog"
      aria-label={chosen ? `Change the reasoning model (${label})` : "Choose a reasoning model"}
      title={
        models?.failure
          ? `The last run against this model failed — ${models.failure}`
          : workspace?.workspace
      }
      // `outline`, not `ring`: the focus ring in this design is 2px of accent offset by 2,
      // drawn the same way on every focusable thing on the page.
      className={cn(
        "group/chip min-w-0 cursor-pointer rounded-control",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
      )}
    >
      {chip}
    </button>
  );
}
