import { afterEach, describe, expect, it, vi } from "vitest";

import { coreApi } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("clean-break API client", () => {
  it("starts reviews with case and repository identity only", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "review-1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetch);

    await coreApi.startReview("case-1", "/work/repository");

    expect(fetch).toHaveBeenCalledWith(
      "/api/reviews",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          case_id: "case-1",
          repository_root: "/work/repository",
        }),
      }),
    );
  });

  it("resumes by review identity without client-owned continuation fields", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "review-2" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetch);

    await coreApi.answer(
      "review-1",
      [{ question_id: "question-1", status: "skipped", value: null }],
      true,
    );

    const init = fetch.mock.calls[0]?.[1] as RequestInit;
    expect(fetch.mock.calls[0]?.[0]).toBe("/api/reviews/review-1/answers");
    expect(JSON.parse(String(init.body))).toEqual({
      answers: [{ question_id: "question-1", status: "skipped", value: null }],
      stop: true,
    });
  });

  it("surfaces boundary problem details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ message: "Policy index unavailable" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(coreApi.reviews()).rejects.toThrow("Policy index unavailable");
  });

  it("exposes graph stages from the NDJSON review stream", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          '{"event":"analyze_repository"}\n' +
            '{"event":"awaiting_answers","review":{"id":"review-1"}}\n',
          { status: 200, headers: { "Content-Type": "application/x-ndjson" } },
        ),
      ),
    );

    const events = [];
    for await (const event of coreApi.streamReview("case-1", "/work/repository")) {
      events.push(event);
    }

    expect(events.map((event) => event.event)).toEqual([
      "analyze_repository",
      "awaiting_answers",
    ]);
    expect(events[1]?.review?.id).toBe("review-1");
  });

  it("selects embedding models independently from reasoning", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ models: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetch);

    await coreApi.selectEmbedding("ollama", "nomic-embed-text:latest");

    expect(fetch).toHaveBeenCalledWith(
      "/api/embeddings/selection",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          provider: "ollama",
          model: "nomic-embed-text:latest",
        }),
      }),
    );
  });

  it("updates a workspace policy in place rather than creating a second one", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "team-convention" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetch);

    await coreApi.updatePolicy("team convention/1", {
      title: "Team convention",
      description: "Authored here",
      body: "Local guidance",
      tags: [],
      strength: "guidance",
    });

    expect(fetch.mock.calls[0]?.[0]).toBe("/api/policies/team%20convention%2F1");
    expect((fetch.mock.calls[0]?.[1] as RequestInit).method).toBe("PUT");
  });

  it("browses the machine's folders one directory at a time", async () => {
    // A fresh Response per call: a body can only be read once.
    const fetch = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify({ path: "/work", parent: "/", directories: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetch);

    await coreApi.directories("/work/payments platform");
    expect(fetch.mock.calls[0]?.[0]).toBe(
      "/api/filesystem/directories?path=%2Fwork%2Fpayments%20platform",
    );

    await coreApi.directories();
    expect(fetch.mock.calls[1]?.[0]).toBe("/api/filesystem/directories");
  });

  it("re-indexes a repository without asking the caller for a scope", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ root_path: "/work/repository" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetch);

    await coreApi.indexRepository("/work/repository");

    expect(fetch).toHaveBeenCalledWith(
      "/api/repositories/index",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ root_path: "/work/repository" }),
      }),
    );
  });
});
