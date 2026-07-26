import { render, screen } from "@testing-library/react";

import { RunProgress } from "./HomePage";

const BOUNDARIES = ["ports.TaskFormatter", "ports.Clock", "ports.TaskStore"];

describe("RunProgress", () => {
  it("counts nothing before detection has said how much there is", () => {
    render(<RunProgress progress={null} />);

    expect(screen.getByRole("status")).toHaveTextContent("Sweeping the atlas");
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("names the boundary under judgement and its position in the sequence", () => {
    render(
      <RunProgress progress={{ total: 3, boundaries: BOUNDARIES, judged: 1 }} />,
    );

    // One verdict has landed, so the second boundary is the one being judged.
    expect(screen.getByRole("status")).toHaveTextContent("Judging boundary 2 of 3");
    expect(screen.getByRole("status")).toHaveTextContent("ports.Clock");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
  });

  it("says the judging is over rather than counting past the end", () => {
    render(
      <RunProgress progress={{ total: 3, boundaries: BOUNDARIES, judged: 3 }} />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("All 3 boundaries judged");
    expect(screen.getByRole("status")).not.toHaveTextContent("4 of 3");
  });

  it("reports an empty sweep as a result rather than as a stalled run", () => {
    render(<RunProgress progress={{ total: 0, boundaries: [], judged: 0 }} />);

    expect(screen.getByRole("status")).toHaveTextContent("No boundaries to judge");
  });
});
