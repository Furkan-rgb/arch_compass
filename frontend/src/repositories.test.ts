import { latestPerRepository } from "./repositories";
import type { RepositorySummary } from "./types";

function version(rootPath: string, versionId: string): RepositorySummary {
  return {
    version_id: versionId,
    repository_identity: rootPath,
    root_path: rootPath,
    created_at: "2026-07-26T10:00:00Z",
    node_count: 1,
    edge_count: 0,
    signal_count: 0,
  };
}

describe("latestPerRepository", () => {
  it("keeps one entry per repository, the newest first in the listing", () => {
    const chosen = latestPerRepository([
      version("/repos/scheduler", "atlas_3"),
      version("/repos/scheduler", "atlas_2"),
      version("/repos/parser", "atlas_1"),
    ]);

    expect(chosen.map((item) => item.version_id)).toEqual(["atlas_3", "atlas_1"]);
  });

  it("is empty for an empty listing rather than undefined", () => {
    expect(latestPerRepository([])).toEqual([]);
  });
});
