/**
 * The NDJSON reader both streaming routes share.
 *
 * Worth its own test because the failure it guards against is invisible in normal use: a
 * network chunk has nothing to do with a line, so a reader that assumed one line per chunk
 * works perfectly against a fast local server and drops or mangles text against a slow one.
 * Every case here splits the bytes somewhere a real transport plausibly would.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, UNREACHABLE_CODE, UNREACHABLE_MESSAGE } from "./api";

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

/** A response carrying whatever body is given, JSON or not, as a real one would. */
function replied(body: string, { ok = true, status = 200 } = {}): Response {
  return {
    ok,
    status,
    statusText: ok ? "OK" : "Internal Server Error",
    json: async () => JSON.parse(body) as unknown,
    text: async () => body,
  } as unknown as Response;
}

const INDEX_HTML = '<!doctype html>\n<html lang="en">\n  <head><title>Arch Compass</title>';

/**
 * What the reader is shown when `archcompass web` is not running.
 *
 * The bug this covers reached the screen intact: with the API down, the request falls through
 * to whatever is still serving the page, that answers any path with `index.html`, and the
 * client reported `Unexpected token '<', "<!doctype "... is not valid JSON` — a sentence about
 * a parser, naming neither what failed nor what to do. The line these tests hold is that the
 * translation happens only where there is nothing to translate away: a server that answered in
 * its own words keeps every one of them.
 */
describe("an unreachable workspace", () => {
  it("reads a page of HTML as the workspace not being there", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => replied(INDEX_HTML)));

    await expect(api.workspace()).rejects.toMatchObject({
      code: UNREACHABLE_CODE,
      message: UNREACHABLE_MESSAGE,
    });
    // Not the parser's complaint, under any wording.
    await expect(api.workspace()).rejects.not.toThrow(/JSON/);
  });

  it("reads a refused connection the same way", async () => {
    // What `fetch` does when nothing accepted the connection at all.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    const failure = await api.reviews().catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ code: UNREACHABLE_CODE, message: UNREACHABLE_MESSAGE });
    // The original is kept as the cause: it is what a bug report needs and what no reader does.
    expect((failure as ApiError).cause).toBeInstanceOf(TypeError);
  });

  it("reads an HTML error page as the workspace not being there, keeping its status", async () => {
    // A proxy in front of a stopped server answers 502 with its own page, not a ProblemDetail.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => replied("<html>502 Bad Gateway</html>", { ok: false, status: 502 })),
    );

    await expect(api.policies()).rejects.toMatchObject({
      code: UNREACHABLE_CODE,
      status: 502,
    });
  });

  it("passes a real refusal through verbatim", async () => {
    // The whole point of the change is that this one is untouched. A validator naming the
    // field it rejected tells the reader more than any sentence written here could.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        replied(
          JSON.stringify({
            code: "invalid_case",
            message: "case.title must not be empty",
          }),
          { ok: false, status: 422 },
        ),
      ),
    );

    await expect(api.reviews()).rejects.toMatchObject({
      code: "invalid_case",
      message: "case.title must not be empty",
      status: 422,
    });
  });

  it("passes a real refusal through verbatim on the routes that do not use `request`", async () => {
    // `deleteReview` reads its own response — a 204 has no body to parse — and still has
    // to report the server's own words when the answer is a refusal instead.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        replied(
          JSON.stringify({ code: "review_running", message: "that review is still running" }),
          { ok: false, status: 409 },
        ),
      ),
    );

    await expect(api.deleteReview("rev-1")).rejects.toMatchObject({
      code: "review_running",
      message: "that review is still running",
    });
  });

  it("reads a 204 as the success it is", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 204 }) as Response));

    await expect(api.deleteReview("rev-1")).resolves.toBeUndefined();
  });
});
