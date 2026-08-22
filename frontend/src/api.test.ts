import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("clean-break API client", () => {
  it("starts reviews on a run, so no tab is holding the review open", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse({ run_id: "thread-1" }, 202));
    vi.stubGlobal("fetch", fetch);

    await api.startReviewRun("case-1", "/work/repository");

    expect(fetch).toHaveBeenCalledWith(
      "/api/reviews/runs",
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

    await api.answer(
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

    await expect(api.reviews()).rejects.toThrow("Policy index unavailable");
  });

  it("answers a clarification round onto a run there is somewhere to come back to", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse({ run_id: "thread-3" }, 202));
    vi.stubGlobal("fetch", fetch);

    const run = await api.answerRun(
      "review-1",
      [{ question_id: "question-1", status: "answered", value: "The domain owns it" }],
    );

    expect(fetch.mock.calls[0]?.[0]).toBe("/api/reviews/review-1/answers/runs");
    expect(run.run_id).toBe("thread-3");
  });

  it("asks for the review list as a listing rather than as the reviews", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetch);

    await api.reviewSummaries();

    expect(fetch.mock.calls[0]?.[0]).toBe("/api/reviews?view=summary");
  });

  it("adds the repository's own policies to the corpus the page shows", async () => {
    // A fresh Response per call: a body can only be read once.
    const fetch = vi.fn().mockImplementation(async () => jsonResponse([]));
    vi.stubGlobal("fetch", fetch);

    await api.policies({ repositoryRoot: "/work/payments platform" });
    expect(fetch.mock.calls[0]?.[0]).toBe(
      "/api/policies?repository_root=%2Fwork%2Fpayments%20platform",
    );

    // Called the way React Query calls a `queryFn`: with its context, not with a path.
    await api.policies({ signal: new AbortController().signal });
    expect(fetch.mock.calls[1]?.[0]).toBe("/api/policies");
  });

  it("gives up on a read that never answers, and never on work the server is doing", async () => {
    const signals: Array<AbortSignal | null | undefined> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (_path: string, init: RequestInit) => {
        signals.push(init.signal);
        return jsonResponse({});
      }),
    );

    await api.reviews();
    await api.ask("conversation-1", "What supports this?");

    expect(signals[0]).toBeInstanceOf(AbortSignal);
    // Nothing to abort on a judgement: the work carries on after a timeout fires, so
    // aborting says nothing true about it and takes away the answer that would have.
    expect(signals[1]).toBeUndefined();
  });

  it("passes the caller's own cancellation through to the request", async () => {
    const controller = new AbortController();
    let seen: AbortSignal | null | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (_path: string, init: RequestInit) => {
        seen = init.signal;
        return jsonResponse({});
      }),
    );

    await api.review("review-1", controller.signal);

    expect(seen).toBeInstanceOf(AbortSignal);
    controller.abort();
    expect(seen?.aborted).toBe(true);
  });

  it("records one disposition against several candidates in one round trip", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse({ recorded: 2, decisions: [] }, 201));
    vi.stubGlobal("fetch", fetch);

    await api.decideMany("review-1", ["candidate-1", "candidate-2"], "accept");

    expect(fetch.mock.calls[0]?.[0]).toBe("/api/decisions/bulk");
    expect(JSON.parse(String((fetch.mock.calls[0]?.[1] as RequestInit).body))).toEqual({
      review_id: "review-1",
      disposition: "accept",
      author: "user",
      reasoning: null,
      candidates: [{ candidate_id: "candidate-1" }, { candidate_id: "candidate-2" }],
    });
  });

  it("forgets a model selection the provider can no longer offer a tile for", async () => {
    const fetch = vi.fn().mockImplementation(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);

    await api.clearModelSelection();
    await api.clearEmbeddingSelection();

    expect(fetch.mock.calls[0]?.[0]).toBe("/api/models/selection");
    expect((fetch.mock.calls[0]?.[1] as RequestInit).method).toBe("DELETE");
    expect(fetch.mock.calls[1]?.[0]).toBe("/api/embeddings/selection");
  });

  it("re-scopes a case, which is the only thing about one that is set rather than answered", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse({ case_id: "case-1" }));
    vi.stubGlobal("fetch", fetch);

    await api.rescopeCase("case-1", { organisation: "acme", repository: null, user: null });

    expect(fetch.mock.calls[0]?.[0]).toBe("/api/cases/case-1");
    expect((fetch.mock.calls[0]?.[1] as RequestInit).method).toBe("PATCH");
  });

  it("registers and forgets a folder of Markdown policies", async () => {
    const fetch = vi.fn().mockImplementation(async () => jsonResponse({ source: "/work/rules" }, 201));
    vi.stubGlobal("fetch", fetch);

    await api.addPolicySource("/work/rules");
    await api.removePolicySource("/work/rules");

    expect(fetch.mock.calls[0]?.[0]).toBe("/api/policies/sources");
    expect(fetch.mock.calls[1]?.[0]).toBe("/api/policies/sources?source=%2Fwork%2Frules");
    expect((fetch.mock.calls[1]?.[1] as RequestInit).method).toBe("DELETE");
  });

  it("cancels a run by its own id, because there is no review while it is judging", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse({ run_id: "thread-9", status: "cancelled" }));
    vi.stubGlobal("fetch", fetch);

    const run = await api.cancelRun("thread-9");

    expect(fetch.mock.calls[0]?.[0]).toBe("/api/reviews/runs/thread-9/cancel");
    expect(run.status).toBe("cancelled");
  });

  it("selects embedding models independently from reasoning", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ models: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetch);

    await api.selectEmbedding("ollama", "nomic-embed-text:latest");

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

    await api.updatePolicy("team convention/1", {
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

    await api.directories("/work/payments platform");
    expect(fetch.mock.calls[0]?.[0]).toBe(
      "/api/filesystem/directories?path=%2Fwork%2Fpayments%20platform",
    );

    await api.directories();
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

    await api.indexRepository("/work/repository");

    expect(fetch).toHaveBeenCalledWith(
      "/api/repositories/index",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ root_path: "/work/repository" }),
      }),
    );
  });
});
