import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";
import { ModelChip, ModelPickerProvider } from "./model-picker";
import type { ModelCatalog, WorkspaceSummary } from "./types";

const CATALOG: ModelCatalog = {
  providers: [
    {
      provider: "ollama",
      available: true,
      detail: "",
      probed_at: "2026-08-01T10:00:00Z",
    },
    {
      provider: "google",
      available: false,
      detail: "The google provider needs an API key: set GOOGLE_API_KEY in .env",
      probed_at: "2026-08-01T10:00:00Z",
    },
  ],
  candidates: [
    {
      provider: "ollama",
      model: "gemma4:26b",
      thinking: null,
      label: "26B",
      input_token_limit: null,
      output_token_limit: null,
      is_selected: false,
    },
    // One model, two rows: a model that can reason either way is offered as both, and
    // the variant is part of what a click sends.
    {
      provider: "ollama",
      model: "qwen3.6:35b",
      thinking: true,
      label: "35B",
      input_token_limit: null,
      output_token_limit: null,
      is_selected: false,
    },
    {
      provider: "ollama",
      model: "qwen3.6:35b",
      thinking: false,
      label: "35B",
      input_token_limit: null,
      output_token_limit: null,
      is_selected: false,
    },
  ],
};

function summary(models: Partial<WorkspaceSummary["models"]>): WorkspaceSummary {
  return {
    workspace: "/home/dev/workspace",
    models: {
      reasoning: null,
      failure: "",
      pinned: false,
      ...models,
    },
  };
}

function open(workspace: WorkspaceSummary) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ModelPickerProvider>
        <ModelChip workspace={workspace} />
      </ModelPickerProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("the model chip", () => {
  it("asks for a model when none is chosen, and is the control that chooses one", () => {
    open(summary({}));

    expect(screen.getByText("Choose a model")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Choose a reasoning model" }),
    ).toBeInTheDocument();
  });

  it("names the model once one is chosen", () => {
    open(summary({ reasoning: { provider: "ollama", model: "gemma4:26b" } }));

    expect(screen.getByText("ollama · gemma4:26b")).toBeInTheDocument();
  });

  it("carries the last failure, which is not the same as being unavailable", () => {
    // A spent quota lists perfectly well, so no probe can discover this. It is only ever
    // known from a call that already failed.
    open(
      summary({
        reasoning: { provider: "google", model: "gemini-3.6-flash" },
        failure: "Google AI Studio reasoning request failed with HTTP 429",
      }),
    );

    expect(screen.getByRole("button", { name: /Change the reasoning model/ })).toHaveAttribute(
      "title",
      expect.stringContaining("HTTP 429"),
    );
  });

  it("offers no choice when the run was pinned to a model", () => {
    // `--provider`/`--model` decided which provider this process costs against. Offering
    // a choice that would then be ignored is worse than offering none.
    open(summary({ reasoning: { provider: "google", model: "gemini-3.6-flash" }, pinned: true }));

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("google · gemini-3.6-flash")).toBeInTheDocument();
  });
});

describe("choosing a model", () => {
  it("asks no provider anything until the sheet is opened", async () => {
    const models = vi.spyOn(api, "models").mockResolvedValue(CATALOG);
    open(summary({}));

    expect(models).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Choose a reasoning model" }));

    await waitFor(() => expect(models).toHaveBeenCalledTimes(1));
  });

  it("shows a provider that did not answer, with the reason", async () => {
    // The most useful row on the screen: it is the only one naming what to do about it.
    vi.spyOn(api, "models").mockResolvedValue(CATALOG);
    open(summary({}));

    fireEvent.click(screen.getByRole("button", { name: "Choose a reasoning model" }));

    expect(await screen.findByText(/set GOOGLE_API_KEY in .env/)).toBeInTheDocument();
    expect(screen.getByText("gemma4:26b")).toBeInTheDocument();
  });

  it("sends the variant as well as the model", async () => {
    // The same name thinking and not are two different choices, with different costs and
    // output budgets behind them, so the click has to say which row it was.
    vi.spyOn(api, "models").mockResolvedValue(CATALOG);
    const select = vi
      .spyOn(api, "selectModel")
      .mockResolvedValue(
        summary({ reasoning: { provider: "ollama", model: "qwen3.6:35b", thinking: true } }),
      );
    open(summary({}));

    fireEvent.click(screen.getByRole("button", { name: "Choose a reasoning model" }));
    fireEvent.click(await screen.findByRole("option", { name: /qwen3\.6:35b thinking/ }));

    // The first argument only: react-query hands the mutation its own context as a second.
    await waitFor(() => expect(select).toHaveBeenCalled());
    expect(select.mock.calls[0][0]).toEqual({
      provider: "ollama",
      model: "qwen3.6:35b",
      thinking: true,
    });
  });

  it("offers a model that reasons either way as two rows, and only marks the thinking one", async () => {
    vi.spyOn(api, "models").mockResolvedValue(CATALOG);
    open(summary({}));

    fireEvent.click(screen.getByRole("button", { name: "Choose a reasoning model" }));

    const rows = await screen.findAllByRole("option", { name: /qwen3\.6:35b/ });
    expect(rows).toHaveLength(2);
    expect(screen.getAllByText("thinking")).toHaveLength(1);
  });
});

describe("while the providers are being asked", () => {
  it("says so, rather than looking like it already answered nothing", async () => {
    // The probe reaches every configured provider over the network, and an Ollama server
    // that is not running spends its whole two-second budget before saying so. An empty
    // sheet in the meantime reads as "there are no models".
    let answer: (catalog: ModelCatalog) => void = () => {};
    vi.spyOn(api, "models").mockReturnValue(
      new Promise<ModelCatalog>((resolve) => {
        answer = resolve;
      }),
    );
    open(summary({}));

    fireEvent.click(screen.getByRole("button", { name: "Choose a reasoning model" }));

    expect(await screen.findByText(/Asking each provider what it has/)).toBeInTheDocument();

    answer(CATALOG);

    expect(await screen.findByRole("option", { name: /gemma4:26b/ })).toBeInTheDocument();
    expect(screen.queryByText(/Asking each provider what it has/)).not.toBeInTheDocument();
  });
});
