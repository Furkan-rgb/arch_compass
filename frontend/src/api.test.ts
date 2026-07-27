/**
 * The NDJSON reader both streaming routes share.
 *
 * Worth its own test because the failure it guards against is invisible in normal use: a
 * network chunk has nothing to do with a line, so a reader that assumed one line per chunk
 * works perfectly against a fast local server and drops or mangles text against a slow one.
 * Every case here splits the bytes somewhere a real transport plausibly would.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "./api";

/** A response whose body arrives in exactly the chunks given, lines or not. */
function streamed(chunks: string[], ok = true, status = 200): Response {
  const encoder = new TextEncoder();
  return {
    ok,
    status,
    body: new ReadableStream<Uint8Array>({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }),
    json: async () => ({ message: "not used", code: "unused" }),
    statusText: "OK",
  } as unknown as Response;
}

function line(value: unknown): string {
  return `${JSON.stringify(value)}\n`;
}

const ANSWERED = {
  event: "answered",
  message: {
    message_id: "msg-1",
    ordinal: 1,
    question: "What about the Formatter?",
    answer: {
      answer: "The Formatter boundary absorbs nothing the case says is coming.",
      supporting_references: ["BR-001"],
      grounded: true,
    },
    failure: null,
  },
};

afterEach(() => vi.unstubAllGlobals());

describe("streamReviewQuestion", () => {
  it("reassembles a line split across chunks", async () => {
    const whole = line({ event: "prose", text: "The Formatter " }) + line(ANSWERED);
    // Cut mid-object, mid-string: the reader must hold the fragment until the rest arrives.
    const cut = Math.floor(whole.length / 3);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => streamed([whole.slice(0, cut), whole.slice(cut)])),
    );
    const seen: string[] = [];

    const message = await api.streamReviewQuestion("conv-1", "Formatter?", (fragment) =>
      seen.push(fragment),
    );

    expect(seen).toEqual(["The Formatter "]);
    expect(message.message_id).toBe("msg-1");
  });

  it("appends fragments in order and returns the message as the record", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        streamed([
          line({ event: "prose", text: "The Formatter" }),
          line({ event: "prose", text: " boundary" }),
          line(ANSWERED),
        ]),
      ),
    );
    const seen: string[] = [];

    const message = await api.streamReviewQuestion("conv-1", "Formatter?", (fragment) =>
      seen.push(fragment),
    );

    expect(seen.join("")).toBe("The Formatter boundary");
    // The record is the message, not what the fragments built — they may differ when a reply
    // needed the repair round, and only one of the two is what the thread will show.
    expect(message.answer?.answer).toContain("absorbs nothing");
    expect(message.answer?.supporting_references).toEqual(["BR-001"]);
  });

  it("turns a failed line into an error rather than an empty answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        streamed([
          line({ event: "prose", text: "Half an ans" }),
          line({
            event: "failed",
            problem: { code: "provider_unavailable", message: "the model was unreachable" },
          }),
        ]),
      ),
    );

    await expect(
      api.streamReviewQuestion("conv-1", "Formatter?", () => {}),
    ).rejects.toThrow(/unreachable/);
  });

  it("reports a stream that ended without an answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => streamed([line({ event: "prose", text: "Only prose." })])),
    );

    await expect(
      api.streamReviewQuestion("conv-1", "Formatter?", () => {}),
    ).rejects.toThrow(ApiError);
  });

  it("keeps a refusal before the stream opens as its problem detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 404,
        json: async () => ({ code: "not_found", message: "no such conversation" }),
        statusText: "Not Found",
      })),
    );

    await expect(
      api.streamReviewQuestion("conv-gone", "Formatter?", () => {}),
    ).rejects.toMatchObject({ status: 404, code: "not_found" });
  });
});
