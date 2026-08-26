import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ReviewRun } from "../api";
import { runFixture } from "../test-fixtures";
import { runPollInterval, useRecordToFollow } from "./runs";

describe("how often to ask what is running", () => {
  it("keeps asking when nothing is running, slowly", () => {
    // It used to answer `false` for an empty list, and `false` is a trap: once the poll is
    // off, nothing turns it back on while the reader stays where they are.
    // `refetchOnWindowFocus` is off, and a run started in another tab, from the CLI or in CI
    // invalidates nothing here. So a person sitting on `/reviews` when a run began never saw
    // it — and because it never appeared it never left, so `useRunsBecomeReviews` never fired
    // and the review it produced was not on the page until a reload.
    expect(runPollInterval([])).toBe(30_000);
    expect(runPollInterval(undefined)).toBe(30_000);
  });

  it("asks at the working cadence while something is", () => {
    expect(runPollInterval([runFixture()])).toBe(4_000);
  });
});

/**
 * Answering a round and then being left on the record the answer superseded.
 *
 * The page stays put on submit, which is right — it used to jump to a progress list for a
 * review the reader was already looking at. But the waiting snapshot becomes an *earlier
 * record* the moment its successor is filed, so the reader who answered was left on a page
 * announcing itself as out of date, holding their own question and the verdicts from before
 * their answer, with a link they had to notice and press.
 */
describe("following the record your own answer produced", () => {
  type Props = {
    run: ReviewRun | null;
    listed: ReviewRun[] | undefined;
    value: { id: string; superseded_by: string | null };
  };
  const follow = ({ run, listed, value }: Props) => useRecordToFollow(value, run, listed);
  const running = runFixture({ run_id: "run-1", status: "running", sequence: 1 });
  const review: Props["value"] = { id: "review-1", superseded_by: "review-2" };
  const waiting: Props["value"] = { id: "review-1", superseded_by: null };

  it("follows once the run it watched has ended and the successor exists", () => {
    const { result, rerender } = renderHook(follow, {
      initialProps: { run: running, listed: [running], value: waiting } as Props,
    });

    // While it runs there is nowhere to go, and the successor does not exist yet.
    expect(result.current).toBeNull();
    // The run leaves the listing, which is the only signal that means "genuinely done".
    rerender({ run: null, listed: [], value: waiting });
    // Still nothing: the review has not come back carrying its successor. Following here
    // would be following to nowhere.
    expect(result.current).toBeNull();
    rerender({ run: null, listed: [], value: review });
    expect(result.current).toBe("review-2");
  });

  it("does not carry a reader off an old record they opened deliberately", () => {
    // Nothing was watched, so nothing is followed. This is the rail: a superseded record is
    // a legitimate thing to sit and read, and hijacking it would make the older revisions
    // unreachable.
    const { result } = renderHook(follow, {
      initialProps: { run: null, listed: [], value: review } as Props,
    });

    expect(result.current).toBeNull();
  });

  it("waits for the listing to answer rather than reading silence as an ending", () => {
    // `undefined` is the poll not having replied yet. Read as an absence it would follow
    // before anything had run.
    const { result, rerender } = renderHook(follow, {
      initialProps: { run: running, listed: [running], value: review } as Props,
    });

    rerender({ run: null, listed: undefined, value: review });
    expect(result.current).toBeNull();
  });

  it("never follows a record to itself", () => {
    // A successor that is this record is not a successor, and going there is a loop with no
    // way out of it.
    const itself: Props["value"] = { id: "review-1", superseded_by: "review-1" };
    const { result, rerender } = renderHook(follow, {
      initialProps: { run: running, listed: [running], value: itself } as Props,
    });

    rerender({ run: null, listed: [], value: itself });
    expect(result.current).toBeNull();
  });

  it("watches the next rejudgement after following the last one", () => {
    // The review page is not remounted when the reader walks to another review — the route
    // carries no key — so a hook that latched would follow once per tab and never again.
    const { result, rerender } = renderHook(follow, {
      initialProps: { run: running, listed: [running], value: waiting } as Props,
    });
    rerender({ run: null, listed: [], value: review });
    expect(result.current).toBe("review-2");

    const second = runFixture({ run_id: "run-2", status: "running", sequence: 2 });
    rerender({ run: second, listed: [second], value: { id: "review-2", superseded_by: null } });
    expect(result.current).toBeNull();
    rerender({ run: null, listed: [], value: { id: "review-2", superseded_by: "review-3" } });
    expect(result.current).toBe("review-3");
  });
});
