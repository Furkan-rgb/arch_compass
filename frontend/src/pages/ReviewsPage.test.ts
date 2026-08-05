import { anyRunning, groupIntoChains, groupByRepository } from "./ReviewsPage";
import type { BoundaryReviewSummary } from "../types";

function review(fields: Partial<BoundaryReviewSummary>): BoundaryReviewSummary {
  return {
    review_id: "rev_1",
    case_id: "case_a",
    case_revision: 1,
    atlas_version_id: "atlas_1",
    status: "succeeded",
    boundaries_reviewed: 6,
    boundaries_material: 2,
    created_at: "2026-07-26T10:00:00Z",
    updated_at: "2026-07-26T10:00:00Z",
    boundaries_detected: 6,
    case_title: "Task scheduler",
    elicited_from: null,
    ...fields,
  };
}

describe("groupIntoChains", () => {
  it("folds a first pass behind the second pass that answered it", () => {
    // One run, one row. The first pass would otherwise sit in the listing "waiting on
    // your answers" for ever, over questions that were answered minutes later.
    const chains = groupIntoChains([
      review({ review_id: "rev_2", case_revision: 2, elicited_from: "rev_1" }),
      review({ review_id: "rev_1", status: "awaiting_answers" }),
    ]);

    expect(chains).toHaveLength(1);
    expect(chains[0].tip.review_id).toBe("rev_2");
    expect(chains[0].passes.map((item) => item.review_id)).toEqual(["rev_2", "rev_1"]);
  });

  it("keeps a first pass with no second pass as its own row", () => {
    // Still waiting on answers is exactly what this row should say.
    const chains = groupIntoChains([review({ status: "awaiting_answers" })]);

    expect(chains).toHaveLength(1);
    expect(chains[0].passes).toHaveLength(1);
  });

  it("takes the title from whichever pass recorded one", () => {
    // A second pass still running has no title yet; the first pass's is a better answer
    // than a placeholder.
    const chains = groupIntoChains([
      review({ review_id: "rev_2", case_title: null, elicited_from: "rev_1" }),
      review({ review_id: "rev_1", case_title: "Task scheduler" }),
    ]);

    expect(chains[0].title).toBe("Task scheduler");
  });

  it("keeps arrival order between runs", () => {
    // The listing arrives newest first, and each run keeps the position of its tip.
    const chains = groupIntoChains([
      review({ review_id: "rev_b", case_id: "case_b" }),
      review({ review_id: "rev_a2", elicited_from: "rev_a1" }),
      review({ review_id: "rev_a1", status: "awaiting_answers" }),
    ]);

    expect(chains.map((chain) => chain.tip.review_id)).toEqual(["rev_b", "rev_a2"]);
  });

  it("lists a pass whose predecessor was deleted", () => {
    // The walk ends where the record does; the chain is whatever survives.
    const chains = groupIntoChains([
      review({ review_id: "rev_2", elicited_from: "rev_gone" }),
    ]);

    expect(chains).toHaveLength(1);
    expect(chains[0].passes.map((item) => item.review_id)).toEqual(["rev_2"]);
  });
});

describe("anyRunning", () => {
  it("is true only while something is still being produced", () => {
    // What decides whether the page polls at all. A listing of finished reviews cannot
    // change, so asking again would keep a local model's machine busy for nothing.
    expect(anyRunning([review({ status: "succeeded" })])).toBe(false);
    expect(anyRunning([review({ status: "failed" })])).toBe(false);
    expect(
      anyRunning([review({ status: "succeeded" }), review({ status: "running" })]),
    ).toBe(true);
    expect(anyRunning([])).toBe(false);
  });

  it("does not poll for a review that is waiting on a person", () => {
    // Nothing is executing. The row moves when someone answers, and answering produces a
    // *different* review — so polling this one would ask a question with no answer coming,
    // for as long as the page is open.
    expect(anyRunning([review({ status: "awaiting_answers" })])).toBe(false);
  });
});

describe("groupByRepository", () => {
  const repository = (repoId: string, root: string, branch: string) => ({
    version_id: `atlas_${repoId}`,
    repository_identity: `repo_${repoId}`,
    root_path: root,
    repo_id: repoId,
    branch_name: branch,
    created_at: "2026-08-04T10:00:00Z",
  });

  it("sections by repository, names it by its directory, and keeps arrival order inside", () => {
    const grouped = groupByRepository(
      [
        review({ review_id: "rev_3", repo_id: "repoid_x" }),
        review({ review_id: "rev_2", repo_id: "repoid_x", case_revision: 2 }),
        review({ review_id: "rev_1", repo_id: "repoid_y", case_id: "case_b" }),
      ],
      [
        repository("repoid_x", "/home/demo/warehouse-sync", "main"),
        repository("repoid_y", "/home/demo/audiobook-studio", "master"),
      ],
    );

    expect(grouped.map((section) => section.name)).toEqual([
      "warehouse-sync",
      "audiobook-studio",
    ]);
    expect(grouped[0].branchName).toBe("main");
    expect(grouped[0].chains.map((chain) => chain.tip.review_id)).toEqual([
      "rev_3",
      "rev_2",
    ]);
  });

  it("gathers reviews from before repository identity at the end, honestly unnamed", () => {
    // A review stored before lineages existed carries no repo_id. It is not guessed into
    // a section — it is history, listed last under its own heading.
    const grouped = groupByRepository(
      [
        review({ review_id: "rev_old", repo_id: null }),
        review({ review_id: "rev_new", repo_id: "repoid_x" }),
      ],
      [repository("repoid_x", "/home/demo/warehouse-sync", "main")],
    );

    expect(grouped.map((section) => section.repoId)).toEqual(["repoid_x", null]);
    expect(grouped[1].name).toBeNull();
  });

  it("keeps a section for a repository whose atlas is no longer indexed", () => {
    // The reviews still know their repo_id; only the display name is gone. The hashed id
    // is a worse name than the directory's but a better one than pretending the section
    // is pre-identity history.
    const grouped = groupByRepository([review({ repo_id: "repoid_gone" })], []);
    expect(grouped[0].repoId).toBe("repoid_gone");
    expect(grouped[0].name).toBeNull();
  });

  it("widens colliding folder names until they say which project they are", () => {
    // Every bundled example's root is a directory called "repository"; two of them in
    // one listing must not wear the same name. Unique names stay short.
    const grouped = groupByRepository(
      [
        review({ review_id: "rev_1", repo_id: "repoid_a" }),
        review({ review_id: "rev_2", repo_id: "repoid_b", case_id: "case_b" }),
        review({ review_id: "rev_3", repo_id: "repoid_c", case_id: "case_c" }),
      ],
      [
        repository("repoid_a", "/x/eval/cases/warehouse-sync/repository", "main"),
        repository("repoid_b", "/x/eval/cases/audiobook-studio/repository", "main"),
        repository("repoid_c", "/home/demo/billing-service", "main"),
      ],
    );

    expect(grouped.map((section) => section.name)).toEqual([
      "warehouse-sync/repository",
      "audiobook-studio/repository",
      "billing-service",
    ]);
  });
});
