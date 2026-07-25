import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";
import { ConversationPanel } from "./conversation-panel";

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ConversationPanel runId="run-1" />
    </QueryClientProvider>,
  );
}

describe("report conversation panel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("offers to start a conversation when the run has none", async () => {
    vi.spyOn(api, "conversations").mockResolvedValue([]);
    const create = vi
      .spyOn(api, "createConversation")
      .mockResolvedValue({ conversation_id: "conv-1" } as never);
    vi.spyOn(api, "conversationHistory").mockResolvedValue([]);

    renderPanel();

    const button = await screen.findByRole("button", {
      name: /start a conversation/i,
    });
    fireEvent.click(button);

    await waitFor(() => expect(create).toHaveBeenCalledWith("run-1"));
  });

  it("asks a question against the existing conversation and shows the answer", async () => {
    vi.spyOn(api, "conversations").mockResolvedValue([
      { conversation_id: "conv-1", title: "First" },
    ] as never);
    vi.spyOn(api, "conversationHistory").mockResolvedValue([
      {
        message_id: "m1",
        role: "user",
        text: "Which evidence supports FIND-001?",
      },
      {
        message_id: "m2",
        role: "assistant",
        text: "FIND-001 cites node_provider_adapter.",
      },
    ] as never);
    const ask = vi
      .spyOn(api, "askConversation")
      .mockResolvedValue({ message_id: "m3" } as never);

    renderPanel();

    expect(
      await screen.findByText("FIND-001 cites node_provider_adapter."),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/question/i), {
      target: { value: "Why?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^ask$/i }));

    await waitFor(() => expect(ask).toHaveBeenCalledWith("conv-1", "Why?"));
  });

  it("surfaces a failed turn instead of dropping it", async () => {
    vi.spyOn(api, "conversations").mockResolvedValue([
      { conversation_id: "conv-1" },
    ] as never);
    vi.spyOn(api, "conversationHistory").mockResolvedValue([]);
    vi.spyOn(api, "askConversation").mockRejectedValue(
      new Error("The pinned run has no report"),
    );

    renderPanel();

    fireEvent.change(await screen.findByLabelText(/question/i), {
      target: { value: "Why?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^ask$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The pinned run has no report",
    );
  });
});
