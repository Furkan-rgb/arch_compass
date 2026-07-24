import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElapsedTime } from "./RunDetailPage";

afterEach(() => {
  vi.useRealTimers();
});

describe("consultation elapsed time", () => {
  it("updates every second while active and stops at completion", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-24T12:00:05Z"));

    const view = render(
      <ElapsedTime active start="2026-07-24T12:00:00Z" />,
    );
    expect(screen.getByText("5.0s")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(screen.getByText("7.0s")).toBeInTheDocument();

    view.rerender(
      <ElapsedTime
        active={false}
        start="2026-07-24T12:00:00Z"
        end="2026-07-24T12:00:08Z"
      />,
    );
    expect(screen.getByText("8.0s")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(screen.getByText("8.0s")).toBeInTheDocument();
  });

  it("shows a waiting state until the job has started", () => {
    render(<ElapsedTime active />);
    expect(screen.getByText("Waiting")).toBeInTheDocument();
  });
});
