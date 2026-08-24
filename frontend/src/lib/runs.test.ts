import { describe, expect, it } from "vitest";

import { runPollInterval } from "./runs";
import { runFixture } from "../test-fixtures";

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
