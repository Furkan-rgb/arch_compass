import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { runFixture } from "../../test-fixtures";
import { useRejudgementNotice } from "./run-progress";

const bodies: string[] = [];

function stubNotification(permission: NotificationPermission) {
  class FakeNotification {
    static requestPermission = vi.fn(async () => permission);
    constructor(_title: string, options?: { body?: string }) {
      bodies.push(options?.body ?? "");
    }
  }
  vi.stubGlobal("Notification", FakeNotification);
}

afterEach(() => {
  bodies.length = 0;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/**
 * The promise a control makes has to be keepable from where the control lives.
 *
 * `NotifyWhenDone` works on the run's own page because the query there keeps answering with
 * the run after it has finished. On the review page the same component sat inside the round's
 * card, and `/api/reviews/runs` lists only what is still running — so the moment the work
 * finished the run left the list, the card unmounted, and the effect that owed somebody a
 * notification went with it. Somebody who pressed the button, granted permission and read
 * "You will be told when it is done" was never told.
 */
describe("the rejudgement notice", () => {
  it("fires when the run it was armed for leaves the listing", async () => {
    stubNotification("granted");
    const running = runFixture({ sequence: 4 });
    const { result, rerender } = renderHook(
      ({ run, inFlight }: { run: typeof running | null; inFlight: typeof running[] }) =>
        useRejudgementNotice(run, inFlight),
      { initialProps: { run: running as typeof running | null, inFlight: [running] } },
    );

    await act(async () => {
      await result.current.arm();
    });
    expect(result.current.armed).toBe(true);
    expect(bodies).toEqual([]);

    // A finished run is not reported as finished — it is simply not reported. Disappearing is
    // the only signal there is, which is why the arming cannot live in something that
    // disappears with it.
    rerender({ run: null, inFlight: [] });

    expect(bodies).toEqual(["Review 4 has finished running"]);
    // Once, and disarmed: a second poll answering empty must not say it again.
    rerender({ run: null, inFlight: [] });
    expect(bodies).toEqual(["Review 4 has finished running"]);
    expect(result.current.armed).toBe(false);
  });

  it("says nothing while the run is still listed and the page is merely between reviews", async () => {
    // The run being narrowed away is not the run ending. `rejudging` is scoped to one
    // review's own rejudgement, and it goes null for a second reason: opening another
    // revision leaves the review query with no data for a render. Read as completion, that
    // announced a review had finished judging while it was half way through — and disarmed,
    // so the real ending was never announced at all.
    stubNotification("granted");
    const running = runFixture({ sequence: 4 });
    const { result, rerender } = renderHook(
      ({ run, inFlight }: { run: typeof running | null; inFlight: typeof running[] }) =>
        useRejudgementNotice(run, inFlight),
      { initialProps: { run: running as typeof running | null, inFlight: [running] } },
    );

    await act(async () => {
      await result.current.arm();
    });

    // Walking to another review: the narrowed run is gone, the work is not.
    rerender({ run: null, inFlight: [running] });
    expect(bodies).toEqual([]);
    expect(result.current.armed).toBe(true);

    // And the promise is still kept when the work actually ends.
    rerender({ run: null, inFlight: [] });
    expect(bodies).toEqual(["Review 4 has finished running"]);
  });

  it("keeps the promise on the run it was made for, not the one now on screen", async () => {
    // The review page is not remounted when a reader walks to another review — the route
    // carries no key — so arming here and then opening a second rejudgement used to rewrite
    // what was being watched. The notification went to whichever run finished first, named
    // the wrong review, and consumed the arming, so the one somebody actually asked about was
    // never announced at all.
    stubNotification("granted");
    const mine = runFixture({ run_id: "run-mine", sequence: 4 });
    const other = runFixture({ run_id: "run-other", sequence: 9 });
    const { result, rerender } = renderHook(
      ({ run, inFlight }: { run: typeof mine | null; inFlight: typeof mine[] }) =>
        useRejudgementNotice(run, inFlight),
      { initialProps: { run: mine as typeof mine | null, inFlight: [mine, other] } },
    );

    await act(async () => {
      await result.current.arm();
    });

    // Walk to the other review, whose own rejudgement is running.
    rerender({ run: other, inFlight: [mine, other] });
    // The other one finishes first, and says nothing: nobody asked about it.
    rerender({ run: other, inFlight: [mine] });
    expect(bodies).toEqual([]);
    expect(result.current.armed).toBe(true);

    // And the one that was armed for is still announced when it ends.
    rerender({ run: null, inFlight: [] });
    expect(bodies).toEqual(["Review 4 has finished running"]);
  });

  it("waits for the listing to answer rather than reading silence as an ending", async () => {
    stubNotification("granted");
    const running = runFixture({ sequence: 4 });
    const { result, rerender } = renderHook(
      ({ run, inFlight }: { run: typeof running | null; inFlight?: typeof running[] }) =>
        useRejudgementNotice(run, inFlight),
      {
        initialProps: {
          run: running as typeof running | null,
          inFlight: [running] as typeof running[] | undefined,
        },
      },
    );

    await act(async () => {
      await result.current.arm();
    });

    // `undefined` is the query not having answered, which is not an empty list.
    rerender({ run: null, inFlight: undefined });
    expect(bodies).toEqual([]);
    expect(result.current.armed).toBe(true);
  });

  it("says nothing at all when nobody asked to be told", () => {
    stubNotification("granted");
    const running = runFixture({ sequence: 4 });
    const { rerender } = renderHook(
      ({ run, inFlight }: { run: typeof running | null; inFlight: typeof running[] }) =>
        useRejudgementNotice(run, inFlight),
      { initialProps: { run: running as typeof running | null, inFlight: [running] } },
    );

    rerender({ run: null, inFlight: [] });

    expect(bodies).toEqual([]);
  });

  it("stays unarmed when the browser refuses, so the control can say so", async () => {
    stubNotification("denied");
    const run = runFixture();
    const { result } = renderHook(() => useRejudgementNotice(run, [run]));

    let granted = true;
    await act(async () => {
      granted = await result.current.arm();
    });

    expect(granted).toBe(false);
    expect(result.current.armed).toBe(false);
  });
});
